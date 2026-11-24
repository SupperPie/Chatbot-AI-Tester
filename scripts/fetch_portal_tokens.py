#!/usr/bin/env python3
"""批量获取 Portal IM token 并写回 api_config.json。

背景：Portal IM 一个账号只持有一个有效 token（新登录会踢掉旧 token），
所以 token 池只能靠多个不同账号凑出来。本脚本读入账号 CSV 逐个拿 token，
校验 JWT exp 未过期后，用 `|` 拼成 token 池，写回 data/api_config.json 里
对应的 Portal IM (PROD)/(UAT) 配置，供并发轮转使用。

两种模式（--mode）：
  register  会籍激活码注册链路（UAT 新建账号）：sendMailCode →
            verifyMailCode → EC public-key → activation。CSV 表头需含
            email + code（激活码）列，验证码自动取 Asia/Shanghai 当天 ddMMyy。
  login     已有账号三步登录（PROD 已有测试账号）：rsa/public-key(EC) →
            pre-unifiedV2 →（needOtp=true 时）unifiedV2。CSV 表头需含
            email + password 列（可选 deviceId，用于信任设备免 OTP）。

依赖：cryptography（P-256 ECDH 加密密码），已同目录附带 password_crypto.py /
ec_password_crypto.py。主应用 chat_client.py 不需要这些依赖，只有本脚本需要。

用法示例：
  # UAT 激活码注册
  python3 scripts/fetch_portal_tokens.py --mode register --codes-csv uat-code.csv --env uat
  # PROD 已有账号登录
  python3 scripts/fetch_portal_tokens.py --mode login --codes-csv prod-accounts.csv --env prod

注意：
  - register 模式验证码是 Asia/Shanghai 当天的 ddMMyy，发码/校验带 X-Loadtest-Token
    跳过真实发信（缺失该头会退化成真实发信，请务必传入 --loadtest-token）。
  - UAT 发信限流约 3 次/10 秒/IP，脚本默认串行发码（--mail-interval）。
"""

from __future__ import annotations

import argparse
import base64
import csv
import json
import random
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import List, Optional
from zoneinfo import ZoneInfo

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))

from password_crypto import encrypt_password_ec, public_key_request_body  # noqa: E402

LOADTEST_TOKEN_HEADER = "X-Loadtest-Token"
DEFAULT_LOADTEST_TOKEN = "2c4f3c7456a1420b8a201ef5ae6a5bfd"
MEMBERSHIP_BIZ_TYPE = "MEMBERSHIP_ACTIVATION"
SHANGHAI = ZoneInfo("Asia/Shanghai")
DEFAULT_APP_ID = "JUPITA"
DEFAULT_PASSWORD = "DP12345678@"
DEFAULT_USERNAME = "DP&&DC"
MOBILE_USER_AGENT = "ElevaBeyond/1.0.0 (ReactNative)"

SEND_PATH = "/customer/membership/redemption/sendMailCode"
VERIFY_PATH = "/customer/membership/redemption/verifyMailCode"
PUBLIC_KEY_PATH = "/customer/user/login/rsa/public-key"
ACTIVATION_PATH = "/customer/membership/redemption/activation"
PRE_UNIFIED_PATH = "/customer/user/login/pre-unifiedV2"
UNIFIED_PATH = "/customer/user/login/unifiedV2"

# --env 快捷预设（PROD 的注册 host 可能不同，先用配置里的 host 兜底，可被 --base-url 覆盖）
ENV_PRESETS = {
    "uat": {
        "base_url": "https://dc-portal-api-uk-uat.dragonpass.com/api",
        "config_key": "Portal IM (UAT)",
    },
    "prod": {
        "base_url": "https://digital-concierge.dragonpass.com/api",
        "config_key": "Portal IM (PROD)",
    },
}


class FetchError(RuntimeError):
    pass


def create_login_uuid() -> str:
    return f"mobile-{int(time.time() * 1000)}-{random.randbytes(4).hex()}"


def today_verify_code(now: Optional[datetime] = None) -> str:
    """会籍激活码验证码：Asia/Shanghai 当天的 ddMMyy（与压测脚本保持一致）。"""
    current = now or datetime.now(SHANGHAI)
    if current.tzinfo is None:
        current = current.replace(tzinfo=SHANGHAI)
    else:
        current = current.astimezone(SHANGHAI)
    return current.strftime("%d%m%y")


def jwt_expiry_ts(token: str) -> Optional[int]:
    """解析 JWT exp；解析失败/缺失返回 None。"""
    try:
        payload = token.split(".")[1]
        payload += "=" * (4 - len(payload) % 4)
        claims = json.loads(base64.urlsafe_b64decode(payload))
        return claims.get("exp")
    except Exception:
        return None


def load_codes(path: Path) -> List[dict]:
    """读取 email+激活码 CSV，返回 [{email, code}, ...]（跳过 registered/done、去重 email）。"""
    with path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames:
            raise FetchError(f"CSV 没有表头: {path}")
        fields = {name.strip().lower(): name for name in reader.fieldnames}
        email_key = fields.get("email") or fields.get("mail") or fields.get("mailaddress")
        code_key = fields.get("code") or fields.get("activationcode") or fields.get("redemptioncode")
        status_key = fields.get("status")
        if not email_key:
            raise FetchError(f"CSV 需要 email 列，实际表头: {reader.fieldnames}")
        rows: List[dict] = []
        seen: set = set()
        for raw in reader:
            status = str(raw.get(status_key) or "").strip().lower() if status_key else ""
            if status in {"registered", "done"}:
                continue
            email = str(raw.get(email_key) or "").strip().lower()
            code = ""
            if code_key:
                code = "".join(str(raw.get(code_key) or "").split()).replace("-", "").upper()
            if not email:
                continue
            if email in seen:
                continue
            seen.add(email)
            rows.append({"email": email, "code": code})
    if not rows:
        raise FetchError(f"CSV 没有可用数据: {path}")
    return rows


def load_login_accounts(path: Path) -> List[dict]:
    """读取 email+password(+deviceId) CSV，返回 [{email, password, device_id}, ...]。

    跳过 registered/done、去重 email；deviceId 可选，用于信任设备免 OTP。
    """
    with path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames:
            raise FetchError(f"CSV 没有表头: {path}")
        fields = {name.strip().lower(): name for name in reader.fieldnames}
        email_key = fields.get("email") or fields.get("mail") or fields.get("mailaddress")
        password_key = fields.get("password") or fields.get("pwd")
        device_key = fields.get("deviceid") or fields.get("device_id") or fields.get("device")
        status_key = fields.get("status")
        if not email_key:
            raise FetchError(f"CSV 需要 email 列，实际表头: {reader.fieldnames}")
        rows: List[dict] = []
        seen: set = set()
        for raw in reader:
            status = str(raw.get(status_key) or "").strip().lower() if status_key else ""
            if status in {"registered", "done"}:
                continue
            email = str(raw.get(email_key) or "").strip().lower()
            password = str(raw.get(password_key) or "").strip() if password_key else ""
            device_id = str(raw.get(device_key) or "").strip() if device_key else ""
            if not email:
                continue
            if email in seen:
                continue
            seen.add(email)
            rows.append({"email": email, "password": password, "device_id": device_id})
    if not rows:
        raise FetchError(f"CSV 没有可用数据: {path}")
    return rows


class TokenClient:
    def __init__(self, base_url: str, app_id: str, password: str, loadtest_token: str,
                 timeout_sec: float, mail_interval: float) -> None:
        self.base_url = base_url.rstrip("/")
        self.app_id = app_id
        self.password = password
        self.loadtest_token = loadtest_token
        self.mail_interval = max(0.0, mail_interval)
        self.last_mail_at = 0.0
        self.session = requests.Session()
        self.session.headers.update({
            "Accept": "application/json",
            "Content-Type": "application/json",
            "User-Agent": MOBILE_USER_AGENT,
            "lang": "en-US",
        })

    def _post(self, path: str, body: dict, loadtest: bool) -> dict:
        headers = {}
        if loadtest:
            if not self.loadtest_token:
                raise FetchError("缺少 X-Loadtest-Token，已中止以免真实发信")
            headers[LOADTEST_TOKEN_HEADER] = self.loadtest_token
        url = f"{self.base_url}{path}"
        resp = self.session.post(url, json=body, headers=headers, timeout=60)
        text = resp.text
        try:
            payload = json.loads(text)
        except json.JSONDecodeError as exc:
            raise FetchError(f"非 JSON 响应 HTTP {resp.status_code}: {text[:180]}") from exc
        if not isinstance(payload, dict):
            raise FetchError(f"响应不是对象: {text[:180]}")
        code = str(payload.get("code", ""))
        success = payload.get("success")
        if code != "200" or success is False:
            msg = payload.get("msg") or payload.get("message") or "request failed"
            raise FetchError(f"[{path}] 业务失败 code={code}: {msg}")
        return payload.get("data")

    def _wait_mail_gate(self) -> None:
        if self.mail_interval <= 0:
            return
        now = time.monotonic()
        delay = self.last_mail_at + self.mail_interval - now
        if delay > 0:
            time.sleep(delay)
        self.last_mail_at = time.monotonic()

    def register_one(self, email: str, code: str) -> str:
        """会籍激活码注册链路：sendMailCode → verifyMailCode → EC public-key → activation。"""
        if not email:
            raise FetchError("CSV 缺少 email")
        if not code:
            raise FetchError(f"CSV 缺少激活码: {email}")

        verify_code = today_verify_code()

        self._wait_mail_gate()
        mail_data = self._post(
            SEND_PATH,
            {
                "mailAddress": email,
                "bizType": MEMBERSHIP_BIZ_TYPE,
                "redemptionCode": code,
            },
            loadtest=True,
        )
        serial_code = ""
        if isinstance(mail_data, dict):
            serial_code = str(mail_data.get("serialCode") or "").strip()
        if not serial_code:
            raise FetchError(f"sendMailCode 未返回 serialCode: {email}")

        verified = self._post(
            VERIFY_PATH,
            {
                "mailAddress": email,
                "verifyCode": verify_code,
                "serialCode": serial_code,
                "bizType": MEMBERSHIP_BIZ_TYPE,
            },
            loadtest=True,
        )
        if verified is not True:
            raise FetchError(f"verifyMailCode 校验未通过: {email}")

        req_uuid = create_login_uuid()
        public_key = self._post(
            PUBLIC_KEY_PATH,
            public_key_request_body(req_uuid, "EC"),
            loadtest=False,
        )
        if not isinstance(public_key, str) or not public_key.strip():
            raise FetchError(f"缺少 EC 公钥: {email}")
        encrypted_password = encrypt_password_ec(self.password, public_key, req_uuid)

        activation_data = self._post(
            ACTIVATION_PATH,
            {
                "redemptionCode": code,
                "verifyCode": verify_code,
                "serialCode": serial_code,
                "password": encrypted_password,
                "uuid": req_uuid,
                "isPace": False,
                "appId": self.app_id,
            },
            loadtest=False,
        )
        if not isinstance(activation_data, dict) or activation_data.get("success") is not True:
            raise FetchError(f"activation 未返回 success=true: {email}")
        token = str(activation_data.get("token") or "").strip()
        if not token:
            raise FetchError(f"activation 未返回 token: {email}")
        return token

    def login_one(self, email: str, password: str, verify_code: str,
                  device_id: Optional[str]) -> str:
        """三步登录拿 token：public-key(EC) → pre-unifiedV2 →（needOtp=true 时）unifiedV2。"""
        if not email:
            raise FetchError("CSV 缺少 email")
        if not password:
            raise FetchError(f"CSV 缺少密码: {email}")

        req_uuid = create_login_uuid()
        public_key = self._post(
            PUBLIC_KEY_PATH,
            public_key_request_body(req_uuid, "EC"),
            loadtest=False,
        )
        if not isinstance(public_key, str) or not public_key.strip():
            raise FetchError(f"缺少 EC 公钥: {email}")
        encrypted_password = encrypt_password_ec(password, public_key, req_uuid)

        pre_body = {
            "appId": self.app_id,
            "mailAddress": email,
            "password": encrypted_password,
            "uuid": req_uuid,
            "clientType": "app",
        }
        if device_id:
            pre_body["deviceId"] = device_id
        pre_result = self._post(PRE_UNIFIED_PATH, pre_body, loadtest=False)
        if not isinstance(pre_result, dict):
            raise FetchError(f"pre-unifiedV2 响应异常: {email}")
        need_otp = pre_result.get("needOtp")
        if need_otp is False:
            token = str((pre_result.get("loginResult") or {}).get("token") or "").strip()
            if token:
                return token
            raise FetchError(f"pre-unifiedV2 needOtp=false 但缺少 token: {email}")

        serial_code = str(pre_result.get("serialCode") or "").strip()
        if not serial_code:
            raise FetchError(f"pre-unifiedV2 needOtp=true 但缺少 serialCode: {email}")

        unified_body = {
            "appId": self.app_id,
            "mailAddress": email,
            "verifyCode": verify_code,
            "serialCode": serial_code,
            "bizType": "LOGIN",
        }
        if device_id:
            unified_body["deviceId"] = device_id
        login_result = self._post(UNIFIED_PATH, unified_body, loadtest=False)
        if not isinstance(login_result, dict):
            raise FetchError(f"unifiedV2 响应异常: {email}")
        token = str(login_result.get("token") or "").strip()
        if not token:
            raise FetchError(f"unifiedV2 缺少 token: {email}")
        return token


def load_config(path: Path) -> dict:
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def save_config(path: Path, config: dict) -> None:
    with path.open("w", encoding="utf-8") as handle:
        json.dump(config, handle, ensure_ascii=False, indent=4)
        handle.write("\n")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="批量获取 Portal IM token 并写回 data/api_config.json（token 池）"
    )
    parser.add_argument("--codes-csv", required=True, help="账号 CSV 路径（register: email+code；login: email+password）")
    parser.add_argument("--mode", choices=["register", "login"], default="register",
                        help="register=激活码注册拿 token；login=已有账号三步登录拿 token")
    parser.add_argument("--verify-code", default="888888",
                        help="login 模式 needOtp=true 时 unifiedV2 的校验码（默认 888888）")
    parser.add_argument("--device-id", default="",
                        help="login 模式的设备 ID（空则新建，可复用已信任设备）")
    parser.add_argument("--env", choices=list(ENV_PRESETS), help="环境预设 uat/prod（自动填 base-url 和 config-key）")
    parser.add_argument("--base-url", default="", help="注册 API 地址，需含 /api，例如 https://host/api")
    parser.add_argument("--config-key", default="", help="写回 api_config.json 的配置名，例如 'Portal IM (UAT)'")
    parser.add_argument("--config-path", default="", help="api_config.json 路径，默认项目 data/api_config.json")
    parser.add_argument("--app-id", default=DEFAULT_APP_ID)
    parser.add_argument("--password", default=DEFAULT_PASSWORD)
    parser.add_argument("--loadtest-token", default=DEFAULT_LOADTEST_TOKEN,
                        help="发码/校验请求头 X-Loadtest-Token，置空会中止")
    parser.add_argument("--max-tokens", type=int, default=10, help="最多取多少个 token（默认 10）")
    parser.add_argument("--min-tokens", type=int, default=2, help="低于该数量则报错不写回（默认 2）")
    parser.add_argument("--mail-interval", type=float, default=4.0,
                        help="两次 sendMailCode 最小间隔（秒），UAT 限流约 3 次/10 秒")
    parser.add_argument("--timeout-sec", type=float, default=60)
    parser.add_argument("--lang", default="en-US")
    parser.add_argument("--dry-run", action="store_true", help="只拿 token 不写回配置文件")
    args = parser.parse_args()

    if args.env:
        preset = ENV_PRESETS[args.env]
        base_url = args.base_url or preset["base_url"]
        config_key = args.config_key or preset["config_key"]
    else:
        base_url = args.base_url
        config_key = args.config_key
    if not base_url:
        raise SystemExit("需要 --base-url 或 --env")
    if not config_key and not args.dry_run:
        raise SystemExit("需要 --config-key 或 --env（写回目标配置名）")

    config_path = Path(args.config_path) if args.config_path else (
        Path(__file__).resolve().parents[1] / "data" / "api_config.json"
    )

    if args.mode == "login":
        rows = load_login_accounts(Path(args.codes_csv))[: max(1, args.max_tokens)]
    else:
        rows = load_codes(Path(args.codes_csv))[: max(1, args.max_tokens)]
    print(f"base_url={base_url} mode={args.mode} rows={len(rows)} max_tokens={args.max_tokens} "
          f"mail_interval={args.mail_interval}s")

    client = TokenClient(base_url, args.app_id, args.password, args.loadtest_token,
                         args.timeout_sec, args.mail_interval)

    tokens: List[str] = []
    for row in rows:
        email = row["email"]
        try:
            if args.mode == "login":
                device_id = row.get("device_id") or args.device_id or None
                token = client.login_one(email, row["password"], args.verify_code,
                                         device_id)
            else:
                token = client.register_one(email, row["code"])
        except FetchError as exc:
            print(f"[FAIL] {email} {exc}", flush=True)
            continue
        exp = jwt_expiry_ts(token)
        now = time.time()
        if exp is not None and exp < now:
            print(f"[FAIL] {email} token 已过期 exp={exp}", flush=True)
            continue
        tokens.append(token)
        exp_str = datetime.fromtimestamp(exp, SHANGHAI).strftime("%Y-%m-%d %H:%M") if exp else "?"
        print(f"[OK] {email} -> token exp={exp_str}", flush=True)
        if len(tokens) >= args.max_tokens:
            break

    print(f"\n拿到 {len(tokens)} 个有效 token（min={args.min_tokens} max={args.max_tokens}）")
    if len(tokens) < args.min_tokens:
        raise SystemExit("有效 token 数量不足，未写回配置。请检查邮箱/激活码/限流参数。")

    pool = "|".join(tokens)
    print(f"token 池（前 120 字符预览）:\n{pool[:120]}...\n")

    if args.dry_run:
        print("dry-run：未写回配置文件")
        return 0

    if not config_path.exists():
        raise SystemExit(f"配置文件不存在: {config_path}")
    config = load_config(config_path)
    if config_key not in config:
        available = ", ".join(config)
        raise SystemExit(f"配置里找不到 '{config_key}'，现有: {available}")
    entry = config[config_key]
    if entry.get("type") != "portal_im":
        print(f"⚠️  '{config_key}' 的 type 是 {entry.get('type')!r}，并非 portal_im，仍会写入 token。")
    entry["token"] = pool
    save_config(config_path, config)
    print(f"已写回 {len(tokens)} 个 token 到 [{config_key}] 的 token 字段: {config_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())