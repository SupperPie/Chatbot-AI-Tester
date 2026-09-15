
"""
飞书 API 客户端 - 用于导出测试报告到飞书表格
"""
import os
import json
import requests
from typing import List, Dict, Any, Optional
from datetime import datetime

# 飞书配置文件路径（与 api_config.json 同目录）
FEISHU_CONFIG_FILE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "data", "feishu_config.json"
)


def _load_feishu_config() -> Dict[str, str]:
    """读取飞书凭证，优先级：配置文件(页面可配) > 环境变量

    配置文件优先是为了支持在 Settings 页面直接配置服务器凭证，
    无需重启容器/修改环境变量。
    """
    # 1. 配置文件（Settings 页面保存的）
    if os.path.exists(FEISHU_CONFIG_FILE):
        try:
            with open(FEISHU_CONFIG_FILE, "r", encoding="utf-8") as f:
                cfg = json.load(f)
            app_id = (cfg.get("app_id") or "").strip().strip('"').strip("'")
            app_secret = (cfg.get("app_secret") or "").strip().strip('"').strip("'")
            if app_id and app_secret:
                return {"app_id": app_id, "app_secret": app_secret}
        except Exception:
            pass
    # 2. 环境变量兜底
    app_id = os.getenv("FEISHU_APP_ID", "").strip().strip('"').strip("'")
    app_secret = os.getenv("FEISHU_APP_SECRET", "").strip().strip('"').strip("'")
    if app_id and app_secret:
        return {"app_id": app_id, "app_secret": app_secret}
    return {"app_id": "", "app_secret": ""}


def save_feishu_config(app_id: str, app_secret: str) -> bool:
    """保存飞书凭证到配置文件"""
    try:
        os.makedirs(os.path.dirname(FEISHU_CONFIG_FILE), exist_ok=True)
        with open(FEISHU_CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump({"app_id": app_id.strip(), "app_secret": app_secret.strip()}, f, indent=2, ensure_ascii=False)
        return True
    except Exception as e:
        print(f"[feishu] save config failed: {e}")
        return False


def _json_escaped_bytes(val: str) -> int:
    """计算字符串按 JSON 转义（ensure_ascii=False）后的 UTF-8 字节数。
    飞书对单元格的 50000 bytes 限制是按 JSON payload 中该字段的实际字节计算的，
    因此需要按 json.dumps 后的字节数判断，而不是原文 UTF-8 字节数。
    """
    if val is None:
        return 2  # "" 两个引号
    return len(json.dumps(val, ensure_ascii=False).encode("utf-8"))

class FeishuClient:
    """飞书开放平台 API 客户端"""
    
    def __init__(self):
        cfg = _load_feishu_config()
        self.app_id = cfg["app_id"]
        self.app_secret = cfg["app_secret"]
        self.base_url = "https://open.feishu.cn/open-apis"
        self._tenant_access_token = None
        self._token_expires_at = 0
    
    def _get_tenant_access_token(self) -> str:
        """获取 tenant_access_token"""
        import time
        
        # 检查缓存的 token 是否有效
        if self._tenant_access_token and time.time() < self._token_expires_at - 60:
            return self._tenant_access_token

        # 校验并清理 app_id / app_secret
        app_id = (self.app_id or "").strip().strip('"').strip("'")
        app_secret = (self.app_secret or "").strip().strip('"').strip("'")
        if not app_id or not app_secret:
            raise Exception(
                "获取飞书 token 失败: FEISHU_APP_ID 或 FEISHU_APP_SECRET 未配置。"
                "请在 Settings 页面或 .env 文件中设置飞书应用凭证。"
            )
        
        url = f"{self.base_url}/auth/v3/tenant_access_token/internal"
        payload = {
            "app_id": app_id,
            "app_secret": app_secret
        }
        
        try:
            resp = requests.post(url, json=payload, timeout=10)
            resp.raise_for_status()
        except requests.RequestException as e:
            raise Exception(f"获取飞书 token 失败: 网络请求错误 - {e}")

        data = resp.json()
        
        if data.get("code") != 0:
            raise Exception(
                f"获取飞书 token 失败: {data.get('msg')} "
                f"(code={data.get('code')}, 请检查 FEISHU_APP_ID/FEISHU_APP_SECRET 是否正确)"
            )
        
        self._tenant_access_token = data["tenant_access_token"]
        self._token_expires_at = time.time() + data.get("expire", 7200)
        
        return self._tenant_access_token
    
    def _headers(self) -> Dict[str, str]:
        """获取请求头"""
        return {
            "Authorization": f"Bearer {self._get_tenant_access_token()}",
            "Content-Type": "application/json"
        }
    
    def get_wiki_node_info(self, token: str) -> Dict[str, Any]:
        """获取知识库节点信息，用于获取实际的 spreadsheet token"""
        url = f"{self.base_url}/wiki/v2/spaces/get_node"
        params = {"token": token}
        
        resp = requests.get(url, headers=self._headers(), params=params)
        data = resp.json()
        
        if data.get("code") != 0:
            raise Exception(f"获取知识库节点失败: {data.get('msg')}")
        
        return data.get("data", {}).get("node", {})
    
    def append_rows_to_sheet(
        self, 
        spreadsheet_token: str, 
        sheet_id: str, 
        rows: List[List[Any]]
    ) -> Dict[str, Any]:
        """向表格追加数据行（自动分批，避免 request too large）
        
        Args:
            spreadsheet_token: 电子表格 token
            sheet_id: 工作表 ID
            rows: 要追加的数据行，每行是一个列表
        
        Returns:
            最后一批 API 响应（批量时返回汇总信息）
        """
        import time as _time

        # 飞书单次请求体限制约 20MB，这里保守控制在 ~2MB（含 headers/JSON 结构开销）
        # 每行 thinking/raw 等文本可能很大（经 _truncate_cell 后单格 ≤49500 bytes），
        # 17 列 × ~50KB ≈ 850KB 为单行理论上限，因此每批按 20 行上限 + 2MB 字节上限双控
        MAX_BATCH_BYTES = 2 * 1024 * 1024
        # 同时限制每批最多行数（保守值，避免大文本行叠加超限）
        MAX_BATCH_ROWS = 20
        # 批次间间隔（秒），避免触发飞书频率限制（QPS 约 5）
        BATCH_INTERVAL = 0.3
        # 首次写入前的间隔（避免 create_sheet 后立即写入的时序问题）
        FIRST_BATCH_DELAY = 0.8

        url = f"{self.base_url}/sheets/v2/spreadsheets/{spreadsheet_token}/values_append"
        range_str = f"{sheet_id}!A:Z"

        if not rows:
            return {"code": 0, "msg": "no data", "data": {}}

        def _build_payload(batch):
            return {
                "valueRange": {
                    "range": range_str,
                    "values": batch
                }
            }

        def _payload_bytes(batch):
            return len(json.dumps(_build_payload(batch), ensure_ascii=False).encode("utf-8"))

        # 按字节数和行数双重限制切分批次
        batches = []
        current_batch = []
        current_bytes = 0
        for row in rows:
            row_bytes = len(json.dumps(row, ensure_ascii=False).encode("utf-8")) + 50  # 逗号等结构开销
            if current_batch and (
                len(current_batch) >= MAX_BATCH_ROWS
                or current_bytes + row_bytes > MAX_BATCH_BYTES
            ):
                batches.append(current_batch)
                current_batch = []
                current_bytes = 0
            current_batch.append(row)
            current_bytes += row_bytes
        if current_batch:
            batches.append(current_batch)

        total_written = 0
        last_result = None
        for i, batch in enumerate(batches):
            if i == 0:
                _time.sleep(FIRST_BATCH_DELAY)
            payload = _build_payload(batch)
            batch_bytes = len(json.dumps(payload, ensure_ascii=False).encode("utf-8"))
            print(f"[feishu] appending batch {i+1}/{len(batches)}: {len(batch)} rows, ~{batch_bytes/1024:.1f} KB")

            resp = requests.post(url, headers=self._headers(), json=payload, timeout=60)
            data = resp.json()
            last_result = data

            if data.get("code") != 0:
                raise Exception(
                    f"写入飞书表格失败 (batch {i+1}/{len(batches)}, rows={len(batch)}, "
                    f"~{batch_bytes/1024:.1f} KB): {data.get('msg')}"
                )
            total_written += len(batch)

            if i < len(batches) - 1:
                _time.sleep(BATCH_INTERVAL)

        print(f"[feishu] append done: total {total_written} rows in {len(batches)} batches")
        return {
            "code": 0,
            "msg": f"success ({total_written} rows in {len(batches)} batches)",
            "data": {"total_rows": total_written, "batches": len(batches)},
            "last_response": last_result,
        }
    
    def get_sheet_meta(self, spreadsheet_token: str) -> Dict[str, Any]:
        """获取电子表格元信息"""
        url = f"{self.base_url}/sheets/v3/spreadsheets/{spreadsheet_token}/sheets/query"
        
        resp = requests.get(url, headers=self._headers())
        data = resp.json()
        
        if data.get("code") != 0:
            raise Exception(f"获取表格元信息失败: {data.get('msg')}")
        
        return data.get("data", {})
    
    def create_sheet(self, spreadsheet_token: str, title: str) -> str:
        """创建新的工作表
        
        Args:
            spreadsheet_token: 电子表格 token
            title: 工作表名称
        
        Returns:
            新创建的 sheet_id
        """
        url = f"{self.base_url}/sheets/v2/spreadsheets/{spreadsheet_token}/sheets_batch_update"
        
        payload = {
            "requests": [
                {
                    "addSheet": {
                        "properties": {
                            "title": title,
                            "index": 0  # 放在最前面
                        }
                    }
                }
            ]
        }
        
        resp = requests.post(url, headers=self._headers(), json=payload)
        data = resp.json()
        
        if data.get("code") != 0:
            raise Exception(f"创建工作表失败: {data.get('msg')}")
        
        # 从响应中获取新创建的 sheet_id
        replies = data.get("data", {}).get("replies", [])
        if replies and replies[0].get("addSheet"):
            return replies[0]["addSheet"]["properties"]["sheetId"]
        
        raise Exception("创建工作表成功但无法获取 sheet_id")


def export_report_to_feishu(
    report_data: List[Dict[str, Any]], 
    spreadsheet_token: str = None,
    sheet_id: str = None,
    wiki_token: str = None,
    api_name: str = "Test",
    create_new_sheet: bool = True,
    progress_callback = None,
) -> Dict[str, Any]:
    """导出测试报告到飞书表格
    
    Args:
        report_data: 测试报告数据列表
        spreadsheet_token: 电子表格 token（如果是独立表格）
        sheet_id: 工作表 ID
        wiki_token: 知识库文档 token（如果表格在 wiki 中）
        api_name: API 名称，用于生成新 sheet 名称
        create_new_sheet: 是否创建新的工作表（默认 True）
        progress_callback: 可选回调 fn(stage: str, current: int, total: int, detail: str)
    
    Returns:
        导出结果
    """
    def _report(stage, cur, tot, detail=""):
        if progress_callback:
            try:
                progress_callback(stage, cur, tot, detail)
            except Exception:
                pass

    client = FeishuClient()
    
    # 如果是 wiki 中的表格，需要先获取实际的 spreadsheet token
    if wiki_token:
        _report("wiki", 0, 1, "解析 wiki 链接...")
        node_info = client.get_wiki_node_info(wiki_token)
        spreadsheet_token = node_info.get("obj_token")
        if not spreadsheet_token:
            raise Exception("无法获取 wiki 中表格的 token")
    
    # 创建新的工作表，名称为 "API名称_日期"
    if create_new_sheet:
        _report("create_sheet", 0, 1, "创建新 sheet...")
        sheet_title = f"{api_name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        sheet_id = client.create_sheet(spreadsheet_token, sheet_title)
    elif not sheet_id:
        # 如果不创建新 sheet 且没有指定 sheet_id，获取第一个工作表
        _report("meta", 0, 1, "读取表格元信息...")
        meta = client.get_sheet_meta(spreadsheet_token)
        sheets = meta.get("sheets", [])
        if sheets:
            sheet_id = sheets[0].get("sheet_id")
        else:
            raise Exception("表格中没有工作表")
    
    # 转换报告数据为行格式（与 report 页面列一致）
    # 飞书单元格限制 50000 bytes（按 JSON 转义后的字节数计），超长字段做截断
    MAX_CELL_BYTES = 49500  # 留 buffer

    def _truncate_cell(val: str) -> str:
        """截断超长单元格内容（按 JSON 转义后的字节数判断），避免飞书写入失败。

        飞书对 cell 的字节限制是按 JSON payload 中该字段的字节计算的，
        普通英文单字符在 JSON 中可能占 1 字节，但引号/反斜杠/控制字符
        经过 JSON 转义后会膨胀为 \\" \\\\ \\n \\uXXXX 等，导致同一原文的
        JSON 字节数远大于原文 UTF-8 字节数。这里使用二分收缩，
        保证 json.dumps(result, ensure_ascii=False) 的字节数 <= MAX_CELL_BYTES。
        """
        if not val:
            return val
        suffix = " [...truncated]"
        if _json_escaped_bytes(val) <= MAX_CELL_BYTES:
            return val

        # 二分查找最大可保留的原文字符数（按字符数，避免 UTF-8 半字符）
        lo, hi = 0, len(val)
        best = ""
        while lo <= hi:
            mid = (lo + hi) // 2
            candidate = val[:mid] + suffix
            if _json_escaped_bytes(candidate) <= MAX_CELL_BYTES:
                best = candidate
                lo = mid + 1
            else:
                hi = mid - 1
        return best if best else (val[:1] + suffix)

    def _tags_str(tags_val):
        if not tags_val:
            return ""
        if isinstance(tags_val, list):
            return ", ".join(str(x) for x in tags_val)
        return str(tags_val)

    rows = []
    for item in report_data:
        # 格式化 assertion_detail
        assertion_detail = item.get("assertion_detail")
        assertion_result_str = ""
        if assertion_detail and isinstance(assertion_detail, dict):
            results = assertion_detail.get("results", [])
            if not results:
                assertion_result_str = "✅" if assertion_detail.get("passed") else "❌"
            else:
                parts = []
                for r in results:
                    icon = "✅" if r.get("passed") else "❌"
                    parts.append(f"{icon} {r.get('component_name', '?')}: {r.get('message', '')}")
                assertion_result_str = " | ".join(parts)

        # 处理多轮对话的情况
        if item.get("type") == "multi_turn" and item.get("turns"):
            for turn in item["turns"]:
                score_val = turn.get("score") if turn.get("score") is not None else item.get("score", 0)
                row = [
                    item.get("case_id", ""),
                    _truncate_cell(str(turn.get("user", ""))),
                    _truncate_cell(str(item.get("input_cn", ""))),
                    _truncate_cell(str(turn.get("expected", ""))),
                    _truncate_cell(str(item.get("expected_output_cn", ""))),
                    _truncate_cell(str(item.get("description", ""))),
                    _truncate_cell(str(turn.get("actual", ""))),
                    _truncate_cell(str(turn.get("actual_cn", ""))),
                    item.get("priority", ""),
                    _tags_str(item.get("tags")),
                    item.get("module", ""),
                    item.get("type", ""),
                    turn.get("turn", ""),
                    turn.get("ttft", 0),
                    turn.get("latency", 0),
                    _truncate_cell(assertion_result_str),
                    _truncate_cell(str(item.get("validation", ""))),
                    _truncate_cell(str(item.get("overall_criteria", ""))),
                    _truncate_cell(str(turn.get("retrieval_context", ""))),
                    "Pass" if item.get("passed") else "Fail",
                    score_val,
                    _truncate_cell(str(item.get("reason", ""))),
                    _truncate_cell(str(item.get("review_comment", ""))),
                    _truncate_cell(str(turn.get("thinking", ""))),
                    _truncate_cell(str(turn.get("inform_base", ""))),
                    _truncate_cell(str(turn.get("raw", "")))
                ]
                rows.append(row)
        else:
            # 单轮对话
            retrieval_context = item.get("retrieval_context", "")
            if isinstance(retrieval_context, list):
                retrieval_context = ", ".join(str(x) for x in retrieval_context)
            
            row = [
                item.get("case_id", ""),
                _truncate_cell(str(item.get("input", ""))),
                _truncate_cell(str(item.get("input_cn", ""))),
                _truncate_cell(str(item.get("expected_output", ""))),
                _truncate_cell(str(item.get("expected_output_cn", ""))),
                _truncate_cell(str(item.get("description", ""))),
                _truncate_cell(str(item.get("actual_output", ""))),
                _truncate_cell(str(item.get("actual_output_cn", ""))),
                item.get("priority", ""),
                _tags_str(item.get("tags")),
                item.get("module", ""),
                item.get("type", ""),
                "",  # turn_index
                item.get("ttft", 0),
                item.get("latency", 0),
                _truncate_cell(assertion_result_str),
                _truncate_cell(str(item.get("validation", ""))),
                _truncate_cell(str(item.get("overall_criteria", ""))),
                _truncate_cell(str(retrieval_context)),
                "Pass" if item.get("passed") else "Fail",
                item.get("score", 0),
                _truncate_cell(str(item.get("reason", ""))),
                _truncate_cell(str(item.get("review_comment", ""))),
                _truncate_cell(str(item.get("thinking", ""))),
                _truncate_cell(str(item.get("inform_base", ""))),
                _truncate_cell(str(item.get("raw", "")))
            ]
            rows.append(row)
    
    if not rows:
        return {"success": False, "message": "没有数据可导出"}
    
    # 先写入表头（与 report 页面一致）
    headers = [[
        "ID", "Input", "Input_CN", "Expected_Output", "Expected_Output_CN", "Description",
        "Actual_Output", "Actual_Output_CN",
        "Priority", "Tags", "Module", "Type", "Turn_Index",
        "TTFT", "Latency",
        "Assertions", "Validation", "Overall_Criteria", "Retrieval_Context",
        "Passed", "Score", "Reason", "Human Review Comment",
        "Thinking", "Inform Base", "RAW"
    ]]

    # 导出前预检：定位超出飞书单元格 50000 bytes（按 JSON 转义后计算）的具体列
    MAX_CELL_BYTES = 50000
    oversized_cells = []
    for row_idx, row in enumerate(rows):
        case_id = str(row[0]) if len(row) > 0 else ""
        turn = str(row[12]) if len(row) > 12 else ""  # Turn_Index 在 index 12
        for col_idx, cell in enumerate(row):
            txt = "" if cell is None else str(cell)
            b = _json_escaped_bytes(txt)
            if b > MAX_CELL_BYTES:
                col_name = headers[0][col_idx] if col_idx < len(headers[0]) else f"col_{col_idx}"
                oversized_cells.append({
                    "row_index": row_idx,
                    "case_id": case_id,
                    "turn": turn,
                    "column": col_name,
                    "bytes": b
                })

    if oversized_cells:
        top = sorted(oversized_cells, key=lambda x: x["bytes"], reverse=True)[:10]
        detail = "\n".join(
            [f"case_id={x['case_id']}, turn={x['turn']}, column={x['column']}, bytes={x['bytes']}" for x in top]
        )

        # 终端日志
        print("[feishu-export-precheck] oversized cells detected:\n" + detail)

        # 文件日志
        try:
            from pathlib import Path
            log_path = Path(__file__).resolve().parents[1] / "data" / "export_debug.log"
            log_path.parent.mkdir(parents=True, exist_ok=True)
            with open(log_path, "a", encoding="utf-8") as f:
                f.write(f"\n=== {datetime.now().isoformat()} ===\n")
                f.write("[feishu-export-precheck] oversized cells detected:\n")
                f.write(detail + "\n")
        except Exception as log_err:
            print(f"[feishu-export-precheck] write log failed: {log_err}")

        raise Exception(
            "导出前预检发现超长单元格（>50000 bytes），请先处理对应字段：\n" + detail
        )

    client.append_rows_to_sheet(spreadsheet_token, sheet_id, headers)
    
    # 追加数据行
    result = client.append_rows_to_sheet(spreadsheet_token, sheet_id, rows)
    
    return {
        "success": True,
        "message": f"成功导出 {len(rows)} 条记录到飞书表格",
        "rows_count": len(rows),
        "detail": result
    }


def parse_feishu_url(url: str) -> Dict[str, str]:
    """解析飞书表格 URL，提取 token 和 sheet_id
    
    支持格式：
    - https://xxx.feishu.cn/wiki/xxx?sheet=yyy (wiki 中的表格)
    - https://xxx.feishu.cn/sheets/xxx?sheet=yyy (独立表格)
    """
    import re
    from urllib.parse import urlparse, parse_qs
    
    parsed = urlparse(url)
    query = parse_qs(parsed.query)
    
    result = {
        "wiki_token": None,
        "spreadsheet_token": None,
        "sheet_id": query.get("sheet", [None])[0]
    }
    
    # 检查是 wiki 还是 sheets
    if "/wiki/" in parsed.path:
        # wiki 格式: /wiki/{wiki_token}
        match = re.search(r'/wiki/([^/?]+)', parsed.path)
        if match:
            result["wiki_token"] = match.group(1)
    elif "/sheets/" in parsed.path:
        # sheets 格式: /sheets/{spreadsheet_token}
        match = re.search(r'/sheets/([^/?]+)', parsed.path)
        if match:
            result["spreadsheet_token"] = match.group(1)
    
    return result
