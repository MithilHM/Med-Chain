"""Account invitations (sign-up, activation, password reset) and the password policy.

There is deliberately no open self-registration: an account is always bound to an identity the
hospital has verified. Patients sign up with an activation code handed out at registration plus
their date of birth; staff accounts are created by an administrator (or SSO/SCIM) and activated
through a one-time link. Tokens are 80 random bits, stored only as SHA-256 hashes, single use,
time limited, and locked after repeated failed attempts.
"""
import base64
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional, Tuple

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.models import AccountInvitation
from src.services.crypto import sha256_hex

TTL_HOURS = {"PATIENT_PORTAL": 24 * 7, "STAFF_ACTIVATION": 72, "PASSWORD_RESET": 24}
MAX_FAILED_ATTEMPTS = 5
MIN_PASSWORD_LENGTH = 12
_COMMON_PASSWORDS = {
    "password1234", "password12345", "123456789012", "qwertyuiop12", "welcome12345",
    "medchain1234", "hospital1234", "changeme1234", "letmein12345", "iloveyou1234",
}


class PasswordPolicyError(ValueError):
    pass


def validate_password(password: str, email: Optional[str] = None) -> None:
    if len(password) < MIN_PASSWORD_LENGTH:
        raise PasswordPolicyError(f"Password must be at least {MIN_PASSWORD_LENGTH} characters.")
    if len(password) > 128:
        raise PasswordPolicyError("Password must be at most 128 characters.")
    if not any(c.isalpha() for c in password) or not any(c.isdigit() for c in password):
        raise PasswordPolicyError("Password must contain both letters and numbers.")
    if password.lower() in _COMMON_PASSWORDS:
        raise PasswordPolicyError("That password is too common.")
    local_part = (email or "").split("@")[0].lower()
    if len(local_part) >= 4 and local_part in password.lower():
        raise PasswordPolicyError("Password must not contain your email name.")


def generate_token() -> str:
    raw = base64.b32encode(secrets.token_bytes(10)).decode("ascii")  # 16 chars, 80 bits
    return "-".join(raw[i:i + 4] for i in range(0, 16, 4))


def normalize_token(token: str) -> str:
    return "".join(ch for ch in (token or "").upper() if ch.isalnum())


def token_hash(token: str) -> str:
    return sha256_hex(normalize_token(token))


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


async def issue_invitation(
    db: AsyncSession, purpose: str, *, created_by: Optional[str],
    user_id: Optional[str] = None, patient_id: Optional[str] = None,
) -> Tuple[AccountInvitation, str]:
    """Create a new invitation (revoking any earlier unused one for the same target). Returns (row, token)."""
    now = datetime.now(timezone.utc)
    target = AccountInvitation.patient_id == patient_id if purpose == "PATIENT_PORTAL" else AccountInvitation.user_id == user_id
    await db.execute(
        update(AccountInvitation)
        .where(AccountInvitation.purpose == purpose, target,
               AccountInvitation.used_at.is_(None), AccountInvitation.revoked_at.is_(None))
        .values(revoked_at=now)
    )
    token = generate_token()
    row = AccountInvitation(
        purpose=purpose, token_hash=token_hash(token), user_id=user_id, patient_id=patient_id,
        expires_at=now + timedelta(hours=TTL_HOURS[purpose]), created_by=created_by,
    )
    db.add(row)
    await db.flush()
    return row, token


async def find_usable(db: AsyncSession, token: str, for_update: bool = False) -> Optional[AccountInvitation]:
    query = select(AccountInvitation).where(AccountInvitation.token_hash == token_hash(token))
    if for_update:
        query = query.with_for_update()
    row = (await db.execute(query)).scalar_one_or_none()
    if row is None or row.used_at or row.revoked_at or row.failed_attempts >= MAX_FAILED_ATTEMPTS:
        return None
    if _aware(row.expires_at) <= datetime.now(timezone.utc):
        return None
    return row
