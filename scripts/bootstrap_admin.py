"""Create (or re-enroll MFA for) a local break-glass administrator in a fresh installation.

usage: python scripts/bootstrap_admin.py admin@hospital.org [--reset-mfa]

Prints a generated password, the TOTP enrollment URI, and one-time recovery codes exactly once.
Day-to-day staff should sign in through hospital SSO; keep this account for emergencies, store
its credentials in the hospital's privileged-access vault, and review every use.
"""
import asyncio
import secrets
import sys
from pathlib import Path

project_root = Path(__file__).resolve().parent.parent
api_root = project_root / "services" / "api"
sys.path.insert(0, str(api_root if api_root.is_dir() else project_root))

from sqlalchemy import select  # noqa: E402

from src import database  # noqa: E402
from src.models import AppUser  # noqa: E402
from src.services import mfa  # noqa: E402
from src.services.auth import hash_password, revoke_all_user_sessions  # noqa: E402


async def main(email: str, reset_mfa: bool) -> None:
    if not await database.check_connection():
        raise SystemExit("Database unavailable.")
    email = email.strip().lower()
    password = None
    async with database.AsyncSessionLocal() as db:
        user = (await db.execute(select(AppUser).where(AppUser.email == email))).scalar_one_or_none()
        if user is None:
            password = secrets.token_urlsafe(18)
            user = AppUser(email=email, password_hash=hash_password(password), role="admin", auth_source="LOCAL")
            db.add(user)
            await db.flush()
        elif user.role != "admin":
            raise SystemExit("That account exists and is not an administrator.")
        elif user.mfa_enabled and not reset_mfa:
            raise SystemExit("MFA is already enabled; pass --reset-mfa to re-enroll.")
        secret = mfa.generate_secret()
        codes, hashes = mfa.generate_recovery_codes()
        user.mfa_secret_encrypted = mfa.encrypt_secret(user.id, secret)
        user.mfa_enabled, user.mfa_last_timestep, user.mfa_recovery_hashes = True, None, hashes
        await revoke_all_user_sessions(db, user.id)
        await db.commit()

    print(f"Administrator: {email}")
    if password:
        print(f"Password (shown once): {password}")
    print(f"Authenticator enrollment URI: {mfa.provisioning_uri(secret, email)}")
    print(f"Manual entry secret: {secret}")
    print("Recovery codes (single use, shown once):")
    for code in codes:
        print(f"  {code}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        raise SystemExit(__doc__)
    asyncio.run(main(sys.argv[1], "--reset-mfa" in sys.argv))
