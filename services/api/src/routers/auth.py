import logging
import secrets
from datetime import date, datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.responses import RedirectResponse
from fastapi.security import HTTPAuthorizationCredentials
from jose import jwt
from jose.exceptions import JOSEError
from pydantic import BaseModel, Field
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.config import settings
from src.database import get_db
from src.models import AppUser, Doctor, LoginAttempt, Patient, UserSession
from src.routers.deps import get_current_user, record_access_event, security
from src.schemas.auth import LoginRequest, UserOut
from src.services import accounts
from src.services import mfa as totp
from src.services import oidc
from src.services.auth import (
    account_locked_until,
    create_access_token,
    decode_access_token,
    hash_password,
    register_failed_login,
    register_successful_login,
    register_user_session,
    revoke_all_user_sessions,
    revoke_session_by_jti,
    verify_password_or_dummy,
)

router = APIRouter(prefix="/auth", tags=["Authentication"])
logger = logging.getLogger("medchain.auth")

_SSO_ROLES = {"doctor", "researcher", "insurance_analyst", "admin"}
_MFA_CHALLENGE_MINUTES = 5


class MfaVerifyRequest(BaseModel):
    mfa_token: str
    code: str = Field(..., min_length=6, max_length=20)


class MfaCodeRequest(BaseModel):
    code: str = Field(..., min_length=6, max_length=20)


def _set_session_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        key="medchain_session",
        value=token,
        max_age=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        httponly=True,
        secure=not settings.is_development,
        samesite="strict",
        path="/api/v1",
    )


def _clear_session_cookie(response: Response) -> None:
    response.delete_cookie(
        key="medchain_session",
        httponly=True,
        secure=not settings.is_development,
        samesite="strict",
        path="/api/v1",
    )


def _client_key(request: Request) -> str:
    return (request.client.host if request.client else "unknown")[:100]


async def _enforce_login_rate_limit(db: AsyncSession, client_key: str) -> None:
    """Shared across API replicas: attempts are counted in the database."""
    now = datetime.now(timezone.utc)
    recent = (await db.execute(
        select(func.count(LoginAttempt.id)).where(
            LoginAttempt.client_key == client_key, LoginAttempt.attempted_at > now - timedelta(seconds=60)
        )
    )).scalar() or 0
    if recent >= settings.LOGIN_RATE_LIMIT_PER_MINUTE:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many sign-in attempts. Wait a minute and try again.",
            headers={"Retry-After": "60"},
        )
    db.add(LoginAttempt(client_key=client_key, attempted_at=now, succeeded=False))
    if secrets.randbelow(50) == 0:  # opportunistic pruning keeps the table small
        await db.execute(delete(LoginAttempt).where(LoginAttempt.attempted_at < now - timedelta(days=1)))
    await db.flush()


async def _issue_session(user: AppUser, request: Request, response: Response, db: AsyncSession,
                         auth_time: Optional[float] = None) -> str:
    # auth_time = when the user actually signed in; refreshes carry it forward so SESSION_MAX_HOURS holds.
    token, token_jti, expires_at = create_access_token(
        data={"sub": user.id, "role": user.role, "email": user.email,
              "auth_time": auth_time or datetime.now(timezone.utc).timestamp()}
    )
    await register_user_session(
        db, user.id, token_jti, expires_at,
        user_agent=request.headers.get("user-agent", "")[:255],
        ip_address=request.client.host if request.client else None,
    )
    await db.commit()
    _set_session_cookie(response, token)
    return token


async def _linked_user_context(db: AsyncSession, user: AppUser) -> dict:
    patient_id = None
    doctor_id = None
    if user.role == "patient":
        patient = (await db.execute(select(Patient).where(Patient.user_id == user.id))).scalar_one_or_none()
        patient_id = patient.id if patient else None
    elif user.role == "doctor":
        doctor = (await db.execute(select(Doctor).where(Doctor.user_id == user.id))).scalar_one_or_none()
        doctor_id = doctor.id if doctor else None

    return {
        "id": user.id,
        "email": user.email,
        "role": user.role,
        "is_active": user.is_active,
        "demo_mode": settings.DEMO_MODE,
        "patient_id": patient_id,
        "doctor_id": doctor_id,
        "mfa_enabled": bool(user.mfa_enabled),
        "auth_source": user.auth_source,
    }


async def _session_response(user: AppUser, request: Request, response: Response, db: AsyncSession) -> dict:
    register_successful_login(user)
    token = await _issue_session(user, request, response, db)
    body = {"user": await _linked_user_context(db, user)}
    if settings.is_development:
        # Synthetic local API examples use bearer auth. Production only receives the HttpOnly cookie.
        body.update({"access_token": token, "token_type": "bearer"})
    return body


@router.get("/config")
async def auth_config():
    """Public: which sign-in methods the login page should offer."""
    return {
        "password_login": True,
        "oidc_enabled": settings.OIDC_ENABLED,
        "oidc_login_url": "/api/v1/auth/oidc/login" if settings.OIDC_ENABLED else None,
        "demo_mode": settings.DEMO_MODE and settings.is_development,
    }


@router.post("/login")
async def login(
    credentials: LoginRequest,
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
):
    await _enforce_login_rate_limit(db, _client_key(request))
    login_id = credentials.user_email.strip().lower()
    user = (await db.execute(select(AppUser).where(AppUser.email == login_id))).scalar_one_or_none()
    invalid = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Incorrect email or password.",
        headers={"WWW-Authenticate": "Bearer"},
    )
    if user and account_locked_until(user):
        # Same message as a bad password so the lock does not confirm the account exists.
        verify_password_or_dummy(credentials.password, None)
        await record_access_event(db, user.id, None, "AUTHENTICATION", user.id, "LOGIN", "DENIED", "ACCOUNT_LOCKED")
        raise invalid
    if not verify_password_or_dummy(credentials.password, user.password_hash if user else None):
        if user:
            register_failed_login(user)
            await record_access_event(db, user.id, None, "AUTHENTICATION", user.id, "LOGIN", "DENIED", "BAD_CREDENTIALS")
        else:
            await db.commit()
        raise invalid
    if not user.is_active:
        await db.commit()
        raise invalid

    if user.mfa_enabled:
        challenge = jwt.encode(
            {"sub": user.id, "purpose": "mfa_challenge",
             "exp": datetime.now(timezone.utc) + timedelta(minutes=_MFA_CHALLENGE_MINUTES)},
            settings.SECRET_KEY, algorithm="HS256",
        )
        await db.commit()
        return {"mfa_required": True, "mfa_token": challenge}
    if user.role in settings.mfa_required_roles:
        await record_access_event(db, user.id, None, "AUTHENTICATION", user.id, "LOGIN", "DENIED", "MFA_ENROLLMENT_REQUIRED")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Multi-factor authentication is required for this account. Ask an administrator to enroll it.",
        )
    return await _session_response(user, request, response, db)


@router.post("/mfa/verify")
async def verify_mfa(body: MfaVerifyRequest, request: Request, response: Response, db: AsyncSession = Depends(get_db)):
    """Second step of password sign-in: a TOTP code or a one-time recovery code."""
    await _enforce_login_rate_limit(db, _client_key(request))
    try:
        claims = jwt.decode(body.mfa_token, settings.SECRET_KEY, algorithms=["HS256"])
    except JOSEError:
        await db.commit()
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Sign-in expired; enter your password again.")
    user = await db.get(AppUser, claims.get("sub")) if claims.get("purpose") == "mfa_challenge" else None
    if not user or not user.is_active or not user.mfa_enabled or account_locked_until(user):
        await db.commit()
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid verification code.")

    step = totp.verify_code(totp.decrypt_secret(user.id, user.mfa_secret_encrypted), body.code, user.mfa_last_timestep)
    if step is not None:
        user.mfa_last_timestep = step
        reason = "MFA_TOTP"
    else:
        remaining = totp.consume_recovery_code(user.mfa_recovery_hashes, body.code)
        if remaining is None:
            register_failed_login(user)
            await record_access_event(db, user.id, None, "AUTHENTICATION", user.id, "MFA_VERIFY", "DENIED", "BAD_MFA_CODE")
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid verification code.")
        user.mfa_recovery_hashes = remaining
        reason = "MFA_RECOVERY_CODE"
    await record_access_event(db, user.id, None, "AUTHENTICATION", user.id, "MFA_VERIFY", "GRANTED", reason, commit=False)
    return await _session_response(user, request, response, db)


@router.post("/mfa/enroll")
async def enroll_mfa(current_user: AppUser = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """Start enrollment: returns the secret and otpauth:// URI for an authenticator app."""
    if current_user.auth_source != "LOCAL":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="MFA for SSO accounts is enforced by the hospital identity provider.")
    if current_user.mfa_enabled:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="MFA is already enabled.")
    secret = totp.generate_secret()
    current_user.mfa_secret_encrypted = totp.encrypt_secret(current_user.id, secret)
    current_user.mfa_last_timestep = None
    await db.commit()
    return {"secret": secret, "otpauth_uri": totp.provisioning_uri(secret, current_user.email),
            "next_step": "Enter a code from the app at POST /auth/mfa/activate."}


@router.post("/mfa/activate")
async def activate_mfa(body: MfaCodeRequest, current_user: AppUser = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    if current_user.mfa_enabled or not current_user.mfa_secret_encrypted:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Start enrollment first.")
    step = totp.verify_code(totp.decrypt_secret(current_user.id, current_user.mfa_secret_encrypted), body.code, None)
    if step is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid verification code.")
    codes, hashes = totp.generate_recovery_codes()
    current_user.mfa_enabled = True
    current_user.mfa_last_timestep = step
    current_user.mfa_recovery_hashes = hashes
    await record_access_event(db, current_user.id, None, "AUTHENTICATION", current_user.id, "MFA_ENROLL", "GRANTED", "MFA_ENABLED")
    return {"status": "MFA_ENABLED", "recovery_codes": codes,
            "note": "Store these one-time recovery codes securely. They are shown only once."}


@router.post("/mfa/disable")
async def disable_mfa(body: MfaCodeRequest, response: Response, current_user: AppUser = Depends(get_current_user),
                      db: AsyncSession = Depends(get_db)):
    if not current_user.mfa_enabled:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="MFA is not enabled.")
    if current_user.role in settings.mfa_required_roles:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="MFA is mandatory for this role.")
    if totp.verify_code(totp.decrypt_secret(current_user.id, current_user.mfa_secret_encrypted), body.code,
                        current_user.mfa_last_timestep) is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid verification code.")
    current_user.mfa_enabled = False
    current_user.mfa_secret_encrypted = None
    current_user.mfa_recovery_hashes = None
    await revoke_all_user_sessions(db, current_user.id)
    await record_access_event(db, current_user.id, None, "AUTHENTICATION", current_user.id, "MFA_DISABLE", "GRANTED", "MFA_DISABLED")
    _clear_session_cookie(response)
    return {"status": "MFA_DISABLED", "note": "All sessions were signed out."}


@router.get("/oidc/login")
async def oidc_login():
    if not settings.OIDC_ENABLED:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Single sign-on is not configured.")
    try:
        url, state_cookie = await oidc.authorization_request()
    except Exception:
        logger.exception("OIDC discovery failed")
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="The hospital identity provider is unavailable.")
    redirect = RedirectResponse(url, status_code=status.HTTP_302_FOUND)
    # SameSite=Lax: the identity provider redirects back with a top-level GET.
    redirect.set_cookie(oidc.STATE_COOKIE, state_cookie, max_age=600, httponly=True,
                        secure=not settings.is_development, samesite="lax", path="/api/v1/auth/oidc")
    return redirect


@router.get("/oidc/callback")
async def oidc_callback(request: Request, code: str = "", state: str = "", error: str = "",
                        db: AsyncSession = Depends(get_db)):
    if not settings.OIDC_ENABLED:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Single sign-on is not configured.")
    if error or not code:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Single sign-on was cancelled or refused.")
    try:
        claims = await oidc.complete_login(code, state, request.cookies.get(oidc.STATE_COOKIE))
    except oidc.OIDCError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc))
    except Exception:
        logger.exception("OIDC callback failed")
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="The hospital identity provider is unavailable.")

    subject = oidc.subject_key(claims)
    role = oidc.role_from_claims(claims)
    email = str(claims.get("email") or "").strip().lower()
    user = (await db.execute(select(AppUser).where(AppUser.external_subject == subject))).scalar_one_or_none()
    if user is None and email and claims.get("email_verified", False):
        user = (await db.execute(select(AppUser).where(AppUser.email == email))).scalar_one_or_none()
        if user is not None and user.external_subject is None:
            user.external_subject = subject  # link the existing staff account to its directory identity
    if role is None or role not in _SSO_ROLES:
        if user:
            await record_access_event(db, user.id, None, "AUTHENTICATION", user.id, "SSO_LOGIN", "DENIED", "NO_MAPPED_ROLE")
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Your directory groups do not grant MedChain access.")
    if user is None:
        if not settings.OIDC_ALLOW_JIT_PROVISIONING or not email:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="No MedChain account is provisioned for this identity.")
        user = AppUser(email=email, password_hash="!sso-only:" + secrets.token_hex(16), role=role,
                       auth_source="OIDC", external_subject=subject)
        db.add(user)
        await db.flush()
    if not user.is_active:
        await record_access_event(db, user.id, None, "AUTHENTICATION", user.id, "SSO_LOGIN", "DENIED", "ACCOUNT_INACTIVE")
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="This account is disabled.")
    if user.role != role:
        logger.info("SSO role for user %s changed from %s to %s by directory groups", user.id, user.role, role)
        user.role = role  # the directory is authoritative for staff roles
    if user.auth_source == "LOCAL":
        user.auth_source = "OIDC"
    await record_access_event(db, user.id, None, "AUTHENTICATION", user.id, "SSO_LOGIN", "GRANTED", "OIDC", commit=False)

    redirect = RedirectResponse(settings.OIDC_POST_LOGIN_REDIRECT, status_code=status.HTTP_302_FOUND)
    register_successful_login(user)
    await _issue_session(user, request, redirect, db)
    redirect.delete_cookie(oidc.STATE_COOKIE, path="/api/v1/auth/oidc")
    return redirect


class SignupRequest(BaseModel):
    token: str = Field(..., min_length=8, max_length=40)
    password: str = Field(..., max_length=128)
    email: Optional[str] = Field(default=None, max_length=255)          # patient portal only
    date_of_birth: Optional[date] = None                                # patient portal only


class PasswordChangeRequest(BaseModel):
    current_password: str = Field(..., max_length=128)
    new_password: str = Field(..., max_length=128)


def _mask_email(email: str) -> str:
    local, _, domain = email.partition("@")
    return (local[:2] + "***@" + domain) if domain else "***"


@router.get("/invitations/{token}")
async def preview_invitation(token: str, request: Request, db: AsyncSession = Depends(get_db)):
    """Public: what the sign-up form must ask for. Reveals no patient data."""
    await _enforce_login_rate_limit(db, _client_key(request))
    invitation = await accounts.find_usable(db, token)
    await db.commit()
    if invitation is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="This link or code is invalid, expired, or already used.")
    body = {"purpose": invitation.purpose, "expires_at": invitation.expires_at}
    if invitation.purpose == "PATIENT_PORTAL":
        body.update(requires_email=True, requires_date_of_birth=True)
    else:
        user = await db.get(AppUser, invitation.user_id)
        body.update(requires_email=False, requires_date_of_birth=False, email=_mask_email(user.email), role=user.role)
    return body


@router.post("/signup")
async def signup(body: SignupRequest, request: Request, response: Response, db: AsyncSession = Depends(get_db)):
    """Complete a patient-portal sign-up, a staff activation, or a password reset."""
    await _enforce_login_rate_limit(db, _client_key(request))
    invitation = await accounts.find_usable(db, body.token, for_update=True)
    invalid = HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail="This link or code is invalid, expired, or already used.")
    if invitation is None:
        await db.commit()
        raise invalid

    if invitation.purpose == "PATIENT_PORTAL":
        patient = await db.get(Patient, invitation.patient_id)
        email = (body.email or "").strip().lower()
        if patient is None or patient.record_status != "ACTIVE":
            await db.commit()
            raise invalid
        if not body.date_of_birth or body.date_of_birth != patient.date_of_birth:
            invitation.failed_attempts += 1  # repeated wrong birth dates lock the code
            await db.commit()
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                                detail="The details you entered do not match our records.")
        if patient.user_id:
            await db.commit()
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="A portal account already exists for this record.")
        if "@" not in email or (await db.execute(select(AppUser.id).where(AppUser.email == email))).scalar_one_or_none():
            await db.commit()
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Use a different email address.")
        try:
            accounts.validate_password(body.password, email)
        except accounts.PasswordPolicyError as exc:
            await db.commit()
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))
        user = AppUser(email=email, password_hash=hash_password(body.password), role="patient", auth_source="LOCAL")
        db.add(user)
        await db.flush()
        patient.user_id = user.id
        action = "PATIENT_PORTAL_SIGNUP"
    else:
        user = await db.get(AppUser, invitation.user_id)
        if user is None or not user.is_active:
            await db.commit()
            raise invalid
        try:
            accounts.validate_password(body.password, user.email)
        except accounts.PasswordPolicyError as exc:
            await db.commit()
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))
        user.password_hash = hash_password(body.password)
        user.failed_login_count, user.locked_until = 0, None
        await revoke_all_user_sessions(db, user.id)
        action = "STAFF_ACTIVATION" if invitation.purpose == "STAFF_ACTIVATION" else "PASSWORD_RESET"

    invitation.used_at = datetime.now(timezone.utc)
    await record_access_event(db, user.id, invitation.patient_id, "AUTHENTICATION", user.id, action, "GRANTED",
                              "ONE_TIME_CREDENTIAL", commit=False)
    if user.mfa_enabled:
        await db.commit()
        return {"status": "PASSWORD_SET", "sign_in_required": True}
    result = await _session_response(user, request, response, db)
    result["mfa_enrollment_required"] = user.role in settings.mfa_required_roles
    return result


@router.post("/password")
async def change_password(body: PasswordChangeRequest, request: Request, response: Response,
                          current_user: AppUser = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    if current_user.auth_source != "LOCAL":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="SSO account passwords are managed by the hospital identity provider.")
    if not verify_password_or_dummy(body.current_password, current_user.password_hash):
        register_failed_login(current_user)
        await record_access_event(db, current_user.id, None, "AUTHENTICATION", current_user.id, "PASSWORD_CHANGE",
                                  "DENIED", "BAD_CREDENTIALS")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Current password is incorrect.")
    try:
        accounts.validate_password(body.new_password, current_user.email)
    except accounts.PasswordPolicyError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))
    current_user.password_hash = hash_password(body.new_password)
    await revoke_all_user_sessions(db, current_user.id)  # sign out every other device
    await record_access_event(db, current_user.id, None, "AUTHENTICATION", current_user.id, "PASSWORD_CHANGE",
                              "GRANTED", "PASSWORD_CHANGED", commit=False)
    await _issue_session(current_user, request, response, db)
    return {"status": "PASSWORD_CHANGED", "note": "Other sessions were signed out."}


@router.get("/me", response_model=UserOut)
async def get_me(
    current_user: AppUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await _linked_user_context(db, current_user)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    request: Request,
    response: Response,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
    current_user: AppUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    token = credentials.credentials if credentials else request.cookies.get("medchain_session")
    payload = decode_access_token(token) if token else None
    if payload and payload.get("jti"):
        await revoke_session_by_jti(db, payload["jti"])
        await db.commit()
    _clear_session_cookie(response)


_REFRESH_GRACE_SECONDS = 30


@router.post("/refresh")
async def refresh_session(
    request: Request,
    response: Response,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
    current_user: AppUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Extend an active user's session (the web app calls this while the user is working).

    Idle users are not refreshed, so their session ends after ACCESS_TOKEN_EXPIRE_MINUTES. No session
    is extended past SESSION_MAX_HOURS from the original sign-in.
    """
    token = credentials.credentials if credentials else request.cookies.get("medchain_session")
    payload = decode_access_token(token) or {}
    old = (await db.execute(select(UserSession).where(UserSession.token_jti == payload.get("jti")))).scalar_one()
    now = datetime.now(timezone.utc)
    auth_time = float(payload.get("auth_time") or payload.get("iat") or now.timestamp())
    if now.timestamp() - auth_time >= settings.SESSION_MAX_HOURS * 3600:
        await revoke_session_by_jti(db, old.token_jti)
        await db.commit()
        _clear_session_cookie(response)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Your session reached the {settings.SESSION_MAX_HOURS}-hour limit. Please sign in again.",
        )
    # shortcut: each refresh adds a user_session row (about one per 5 minutes per active user) and nothing
    # prunes expired rows yet; add a nightly cleanup of rows expired for 30+ days once the table grows.
    # Requests already in flight still carry the old cookie: let it live briefly instead of revoking it.
    old.expires_at = min(old.expires_at if old.expires_at.tzinfo else old.expires_at.replace(tzinfo=timezone.utc),
                         now + timedelta(seconds=_REFRESH_GRACE_SECONDS))
    await _issue_session(current_user, request, response, db, auth_time=auth_time)
    return {"status": "REFRESHED", "idle_timeout_seconds": settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60}


@router.post("/demo-switch")
async def demo_switch(
    role: str,
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
):
    if not settings.DEMO_MODE or not settings.is_development:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Demo switching is disabled.")

    role_email_map = {
        "patient": "patient@medchain.local",
        "doctor": "doctor@medchain.local",
        "researcher": "researcher@medchain.local",
        "insurance_analyst": "analyst@medchain.local",
        "admin": "admin@medchain.local",
    }
    email = role_email_map.get(role)
    if not email:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Invalid demo role: {role}")

    user = (await db.execute(select(AppUser).where(AppUser.email == email))).scalar_one_or_none()
    if not user or not user.is_active:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Demo user for role {role} not found.")

    token = await _issue_session(user, request, response, db)
    return {
        "access_token": token,
        "token_type": "bearer",
        "user": {**(await _linked_user_context(db, user)), "demo_mode": True},
    }


@router.get("/sessions")
async def list_user_sessions(
    current_user: AppUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    sessions = (await db.execute(
        select(UserSession)
        .where(UserSession.user_id == current_user.id)
        .order_by(UserSession.created_at.desc())
        .limit(20)
    )).scalars().all()
    return [
        {
            "id": session.id,
            "is_revoked": session.is_revoked,
            "expires_at": session.expires_at,
            "created_at": session.created_at,
            "revoked_at": session.revoked_at,
            "user_agent": session.user_agent,
            "ip_address": session.ip_address,
        }
        for session in sessions
    ]


@router.post("/sessions/revoke-all")
async def revoke_all_sessions(
    response: Response,
    current_user: AppUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    count = await revoke_all_user_sessions(db, current_user.id)
    await db.commit()
    _clear_session_cookie(response)
    return {"status": "success", "revoked_count": count}
