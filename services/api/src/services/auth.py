import uuid
import bcrypt
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Any, Tuple
from jose import JWTError, jwt
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from src.config import settings
from src.models.users import UserSession
from src.models.base import get_utc_now

ALGORITHM = "HS256"

def hash_password(password: str) -> str:
    salt = bcrypt.gensalt(rounds=12)
    return bcrypt.hashpw(password.encode("utf-8"), salt).decode("utf-8")

def verify_password(plain_password: str, hashed_password: str) -> bool:
    try:
        return bcrypt.checkpw(plain_password.encode("utf-8"), hashed_password.encode("utf-8"))
    except Exception:
        return False

def create_access_token(
    data: Dict[str, Any],
    expires_delta: Optional[timedelta] = None,
    jti: Optional[str] = None
) -> Tuple[str, str, datetime]:
    """
    Creates a signed JWT with a unique jti (token identifier) and expiration.
    Returns (token_string, jti, expire_datetime).
    """
    to_encode = data.copy()
    token_jti = jti or str(uuid.uuid4())
    issued_at = datetime.now(timezone.utc)
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"iat": issued_at.timestamp(), "exp": expire, "jti": token_jti})
    encoded_jwt = jwt.encode(to_encode, settings.SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt, token_jti, expire

def decode_access_token(token: str) -> Optional[Dict[str, Any]]:
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except JWTError:
        return None

async def register_user_session(
    db: AsyncSession,
    user_id: str,
    token_jti: str,
    expires_at: datetime,
    user_agent: Optional[str] = None,
    ip_address: Optional[str] = None
) -> UserSession:
    """Registers an active session record in the database."""
    session = UserSession(
        user_id=user_id,
        token_jti=token_jti,
        is_revoked=False,
        expires_at=expires_at,
        user_agent=user_agent,
        ip_address=ip_address
    )
    db.add(session)
    await db.flush()
    return session

async def revoke_session_by_jti(db: AsyncSession, token_jti: str) -> bool:
    """Revokes a single active session by its jti identifier."""
    result = await db.execute(
        select(UserSession).where(UserSession.token_jti == token_jti)
    )
    session = result.scalar_one_or_none()
    if session:
        session.is_revoked = True
        session.revoked_at = get_utc_now()
        await db.flush()
        return True
    return False

async def get_active_session(db: AsyncSession, token_jti: str) -> Optional[UserSession]:
    """Return the session only if it exists, is unrevoked, and has not expired (fail closed)."""
    session = (await db.execute(
        select(UserSession).where(UserSession.token_jti == token_jti)
    )).scalar_one_or_none()
    if not session or session.is_revoked:
        return None
    expires_at = session.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if expires_at <= datetime.now(timezone.utc):
        return None
    return session


async def is_session_revoked(db: AsyncSession, token_jti: str) -> bool:
    """True unless the jti maps to a registered, active session. Unknown sessions count as revoked."""
    return await get_active_session(db, token_jti) is None


# A real bcrypt hash used to equalize timing when the account does not exist.
_DUMMY_PASSWORD_HASH = bcrypt.hashpw(b"medchain-timing-equalizer", bcrypt.gensalt(rounds=12)).decode("utf-8")


def verify_password_or_dummy(plain_password: str, hashed_password: Optional[str]) -> bool:
    """Always performs one bcrypt comparison so response time does not reveal valid emails."""
    if hashed_password is None:
        verify_password(plain_password, _DUMMY_PASSWORD_HASH)
        return False
    return verify_password(plain_password, hashed_password)


def account_locked_until(user) -> Optional[datetime]:
    locked_until = user.locked_until
    if locked_until is None:
        return None
    if locked_until.tzinfo is None:
        locked_until = locked_until.replace(tzinfo=timezone.utc)
    return locked_until if locked_until > datetime.now(timezone.utc) else None


def register_failed_login(user) -> None:
    user.failed_login_count = (user.failed_login_count or 0) + 1
    if user.failed_login_count >= settings.LOGIN_MAX_FAILED_ATTEMPTS:
        user.locked_until = datetime.now(timezone.utc) + timedelta(minutes=settings.LOGIN_LOCKOUT_MINUTES)
        user.failed_login_count = 0


def register_successful_login(user) -> None:
    user.failed_login_count = 0
    user.locked_until = None
    user.last_login_at = datetime.now(timezone.utc)

async def revoke_all_user_sessions(db: AsyncSession, user_id: str) -> int:
    """Revokes all active sessions for a given user."""
    now = get_utc_now()
    result = await db.execute(
        update(UserSession)
        .where(UserSession.user_id == user_id, UserSession.is_revoked == False)
        .values(is_revoked=True, revoked_at=now)
    )
    await db.flush()
    return result.rowcount
