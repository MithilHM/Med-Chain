"""TOTP multi-factor authentication (RFC 6238: HMAC-SHA1, 30-second steps, 6 digits).

Compatible with standard authenticator apps. Secrets are encrypted at rest, accepted codes
cannot be replayed (the last accepted time step is stored), and one-time recovery codes are
stored only as SHA-256 hashes.
"""
import base64
import hashlib
import hmac
import secrets
import struct
import time
from typing import List, Optional, Tuple
from urllib.parse import quote

from src.config import settings
from src.services.crypto import decrypt_text, encrypt_text, sha256_hex

STEP_SECONDS = 30
DIGITS = 6
ALLOWED_DRIFT_STEPS = 1
RECOVERY_CODE_COUNT = 8


def generate_secret() -> str:
    return base64.b32encode(secrets.token_bytes(20)).decode("ascii").rstrip("=")


def _hotp(secret_b32: str, counter: int) -> str:
    padded = secret_b32 + "=" * (-len(secret_b32) % 8)
    key = base64.b32decode(padded, casefold=True)
    digest = hmac.new(key, struct.pack(">Q", counter), hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    code = (struct.unpack(">I", digest[offset:offset + 4])[0] & 0x7FFFFFFF) % (10 ** DIGITS)
    return str(code).zfill(DIGITS)


def current_code(secret_b32: str, at: Optional[float] = None) -> str:
    return _hotp(secret_b32, int((at or time.time()) // STEP_SECONDS))


def verify_code(secret_b32: str, code: str, last_timestep: Optional[int], at: Optional[float] = None) -> Optional[int]:
    """Return the matched time step, or None. Steps at or before last_timestep are rejected (no replay)."""
    code = (code or "").strip().replace(" ", "")
    if len(code) != DIGITS or not code.isdigit():
        return None
    now_step = int((at or time.time()) // STEP_SECONDS)
    for step in range(now_step - ALLOWED_DRIFT_STEPS, now_step + ALLOWED_DRIFT_STEPS + 1):
        if last_timestep is not None and step <= last_timestep:
            continue
        if hmac.compare_digest(_hotp(secret_b32, step), code):
            return step
    return None


def provisioning_uri(secret_b32: str, account_name: str) -> str:
    issuer = settings.MFA_ISSUER
    return (f"otpauth://totp/{quote(issuer)}:{quote(account_name)}"
            f"?secret={secret_b32}&issuer={quote(issuer)}&algorithm=SHA1&digits={DIGITS}&period={STEP_SECONDS}")


def encrypt_secret(user_id: str, secret_b32: str) -> str:
    return encrypt_text(secret_b32, f"mfa:{user_id}")


def decrypt_secret(user_id: str, token: str) -> str:
    return decrypt_text(token, f"mfa:{user_id}")


def generate_recovery_codes() -> Tuple[List[str], List[str]]:
    """Return (plaintext codes shown once, hashes to store)."""
    codes = [f"{secrets.token_hex(2)}-{secrets.token_hex(2)}-{secrets.token_hex(2)}" for _ in range(RECOVERY_CODE_COUNT)]
    return codes, [sha256_hex(code) for code in codes]


def consume_recovery_code(stored_hashes: Optional[List[str]], code: str) -> Optional[List[str]]:
    """Return the remaining hashes if the code matched (single use), else None."""
    if not stored_hashes or not code:
        return None
    candidate = sha256_hex(code.strip().lower())
    remaining = [h for h in stored_hashes if not hmac.compare_digest(h, candidate)]
    return remaining if len(remaining) < len(stored_hashes) else None
