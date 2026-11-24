"""EC password encryption compatible with the Mobile client.

The API still exposes the historical ``/rsa/public-key`` endpoint, but the
Mobile client requests an EC key with ``encryptType=EC``.  Keep this module
small and dependency-free apart from ``cryptography`` so both load-test
scripts use exactly the same wire format.
"""

from __future__ import annotations

import asyncio
import base64
import secrets

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF


HKDF_INFO = b"password-encryption"
NONCE_LENGTH = 12
AES_KEY_LENGTH = 32


def _load_server_public_key(public_key: str) -> ec.EllipticCurvePublicKey:
    """Decode the API's base64 SPKI P-256 public key."""
    if "BEGIN PUBLIC KEY" in public_key:
        key = serialization.load_pem_public_key(public_key.encode("utf-8"))
    else:
        der = base64.b64decode("".join(public_key.split()), validate=True)
        key = serialization.load_der_public_key(der)

    if not isinstance(key, ec.EllipticCurvePublicKey):
        raise ValueError("EC public-key response is not an elliptic-curve key")
    if not isinstance(key.curve, ec.SECP256R1):
        raise ValueError(f"unsupported EC curve: {key.curve.name}")
    return key


def encrypt_password_ec(password: str, public_key: str, salt: str) -> str:
    """Encrypt a password using Mobile's P-256 ECDH + HKDF + AES-GCM format.

    Wire format:
      base64(ephemeral_public_key[65] | nonce[12] | ciphertext | tag[16])

    The JavaScript implementation uses HKDF-SHA256 with ``salt=uuid`` and
    ``info=password-encryption``.  ``HKDF`` appends the one-byte block counter
    internally, matching the Mobile implementation's ``info || 0x01``.
    """
    server_public_key = _load_server_public_key(public_key)
    ephemeral_private_key = ec.generate_private_key(ec.SECP256R1())

    shared_secret = ephemeral_private_key.exchange(ec.ECDH(), server_public_key)
    aes_key = HKDF(
        algorithm=hashes.SHA256(),
        length=AES_KEY_LENGTH,
        salt=salt.encode("utf-8"),
        info=HKDF_INFO,
    ).derive(shared_secret)

    nonce = secrets.token_bytes(NONCE_LENGTH)
    ciphertext_with_tag = AESGCM(aes_key).encrypt(
        nonce,
        password.encode("utf-8"),
        None,
    )
    ephemeral_public_key = ephemeral_private_key.public_key().public_bytes(
        serialization.Encoding.X962,
        serialization.PublicFormat.UncompressedPoint,
    )

    return base64.b64encode(
        ephemeral_public_key + nonce + ciphertext_with_tag,
    ).decode("ascii")


async def encrypt_password_ec_async(password: str, public_key: str, salt: str) -> str:
    """Run EC key generation/encryption off the asyncio event loop."""
    return await asyncio.to_thread(encrypt_password_ec, password, public_key, salt)