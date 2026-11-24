"""Password encryption helpers for Mobile load-test scripts.

Supports two wire protocols:
  - EC  (default, matches current Mobile client)
  - RSA (legacy, for backward-compatible comparison only)
"""

from __future__ import annotations

import asyncio
import base64
from pathlib import Path

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding

from ec_password_crypto import encrypt_password_ec, encrypt_password_ec_async

SUPPORTED_ENCRYPT_TYPES = ("EC", "RSA")
DEFAULT_ENCRYPT_TYPE = "EC"


def normalize_encrypt_type(value: str) -> str:
    normalized = str(value or DEFAULT_ENCRYPT_TYPE).strip().upper()
    if normalized not in SUPPORTED_ENCRYPT_TYPES:
        supported = ", ".join(SUPPORTED_ENCRYPT_TYPES)
        raise ValueError(f"unsupported encrypt type: {value!r} (expected one of {supported})")
    return normalized


def report_encrypt_suffix(encrypt_type: str) -> str:
    return normalize_encrypt_type(encrypt_type).lower()


def default_registered_accounts_csv(report_dir: str | Path, encrypt_type: str) -> Path:
    """Ledger file per encryption mode, e.g. registered_accounts-ec.csv."""
    return Path(report_dir) / f"registered_accounts-{report_encrypt_suffix(encrypt_type)}.csv"


def public_key_request_body(uuid: str, encrypt_type: str) -> dict[str, str]:
    body = {"uuid": uuid}
    if normalize_encrypt_type(encrypt_type) == "EC":
        body["encryptType"] = "EC"
    return body


def encryption_mode_label(encrypt_type: str) -> str:
    normalized = normalize_encrypt_type(encrypt_type)
    if normalized == "EC":
        return "EC (P-256 ECDH + HKDF-SHA256 + AES-GCM)"
    return "RSA-OAEP (SHA-256)"


def _to_public_key_pem(public_key: str) -> str:
    if "BEGIN PUBLIC KEY" in public_key:
        return public_key
    normalized = "".join(public_key.split())
    chunks = "\n".join(normalized[i : i + 64] for i in range(0, len(normalized), 64))
    return f"-----BEGIN PUBLIC KEY-----\n{chunks}\n-----END PUBLIC KEY-----"


def encrypt_password_rsa(password: str, public_key: str) -> str:
    pem = _to_public_key_pem(public_key)
    key = serialization.load_pem_public_key(pem.encode("utf-8"))
    encrypted = key.encrypt(
        password.encode("utf-8"),
        padding.OAEP(
            mgf=padding.MGF1(algorithm=hashes.SHA256()),
            algorithm=hashes.SHA256(),
            label=None,
        ),
    )
    return base64.b64encode(encrypted).decode("ascii")


async def encrypt_password_async(
    encrypt_type: str,
    password: str,
    public_key: str,
    uuid: str,
) -> str:
    if normalize_encrypt_type(encrypt_type) == "EC":
        return await encrypt_password_ec_async(password, public_key, uuid)
    return await asyncio.to_thread(encrypt_password_rsa, password, public_key)


def password_encryption_report(encrypt_type: str) -> dict[str, str]:
    normalized = normalize_encrypt_type(encrypt_type)
    if normalized == "EC":
        return {
            "mode": "EC",
            "key_endpoint": "/customer/user/login/rsa/public-key",
            "key_request_field": "encryptType",
            "hkdf_salt": "uuid",
            "wire_format": "ephemeral_public_key[65] | nonce[12] | ciphertext | tag[16]",
        }
    return {
        "mode": "RSA",
        "key_endpoint": "/customer/user/login/rsa/public-key",
        "key_request_field": "",
        "algorithm": "RSA-OAEP-SHA256",
        "wire_format": "base64(RSA ciphertext)",
    }