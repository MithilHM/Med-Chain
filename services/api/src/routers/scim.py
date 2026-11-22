"""SCIM 2.0 user provisioning (RFC 7643/7644 subset) for the hospital identity provider.

Supports create, read, list/filter by userName, replace, PATCH (active and roles), and DELETE.
DELETE and `active: false` deactivate the account and revoke its sessions; accounts are never
hard-deleted so the audit trail stays intact. Authentication: `Authorization: Bearer <token>`
whose SHA-256 matches SCIM_BEARER_TOKEN_HASH.
"""
import re
import secrets
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.responses import JSONResponse
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.config import settings
from src.database import get_db
from src.models import AppUser
from src.routers.deps import record_access_event
from src.services.auth import revoke_all_user_sessions
from src.services.crypto import constant_time_hash_equals

router = APIRouter(prefix="/scim/v2", tags=["SCIM Provisioning"])

USER_SCHEMA = "urn:ietf:params:scim:schemas:core:2.0:User"
LIST_SCHEMA = "urn:ietf:params:scim:api:messages:2.0:ListResponse"
ERROR_SCHEMA = "urn:ietf:params:scim:api:messages:2.0:Error"
PATCH_SCHEMA = "urn:ietf:params:scim:api:messages:2.0:PatchOp"
STAFF_ROLES = {"doctor", "researcher", "insurance_analyst", "admin"}
SCIM_MEDIA_TYPE = "application/scim+json"


def _error(status_code: int, detail: str, scim_type: Optional[str] = None) -> HTTPException:
    body = {"schemas": [ERROR_SCHEMA], "status": str(status_code), "detail": detail}
    if scim_type:
        body["scimType"] = scim_type
    return HTTPException(status_code=status_code, detail=body)


async def _require_scim_token(request: Request) -> None:
    header = request.headers.get("authorization", "")
    token = header[7:] if header.lower().startswith("bearer ") else ""
    if not settings.SCIM_BEARER_TOKEN_HASH or not token or not constant_time_hash_equals(token, settings.SCIM_BEARER_TOKEN_HASH):
        raise _error(401, "Invalid SCIM credentials.")


def _resource(user: AppUser) -> Dict[str, Any]:
    return {
        "schemas": [USER_SCHEMA],
        "id": user.id,
        "externalId": user.external_subject,
        "userName": user.email,
        "active": bool(user.is_active),
        "emails": [{"value": user.email, "primary": True}],
        "roles": [{"value": user.role, "primary": True}],
        "meta": {
            "resourceType": "User",
            "created": user.created_at.isoformat() if user.created_at else None,
            "lastModified": user.updated_at.isoformat() if user.updated_at else None,
            "location": f"/api/v1/scim/v2/Users/{user.id}",
        },
    }


def _scim(content: Any, status_code: int = 200) -> JSONResponse:
    return JSONResponse(content=content, status_code=status_code, media_type=SCIM_MEDIA_TYPE)


def _role_from(payload: Dict[str, Any]) -> Optional[str]:
    for role in payload.get("roles") or []:
        value = role.get("value") if isinstance(role, dict) else role
        if value in STAFF_ROLES:
            return value
    groups = {g.get("display") or g.get("value") for g in payload.get("groups") or [] if isinstance(g, dict)}
    for group, role in settings.oidc_role_map.items():
        if group in groups and role in STAFF_ROLES:
            return role
    return None


async def _set_active(db: AsyncSession, user: AppUser, active: bool) -> None:
    if user.is_active and not active:
        user.is_active = False
        await revoke_all_user_sessions(db, user.id)
        await record_access_event(db, user.id, None, "PROVISIONING", user.id, "SCIM_DEACTIVATE", "GRANTED",
                                  "BY_IDENTITY_PROVIDER", commit=False)
    elif not user.is_active and active:
        user.is_active = True
        await record_access_event(db, user.id, None, "PROVISIONING", user.id, "SCIM_REACTIVATE", "GRANTED",
                                  "BY_IDENTITY_PROVIDER", commit=False)


async def _get_user(db: AsyncSession, user_id: str) -> AppUser:
    user = await db.get(AppUser, user_id)
    if user is None or user.role == "patient":
        raise _error(404, "User not found.")
    return user


@router.get("/Users", dependencies=[Depends(_require_scim_token)])
async def list_users(filter: Optional[str] = None, startIndex: int = 1, count: int = 100,
                     db: AsyncSession = Depends(get_db)):
    query = select(AppUser).where(AppUser.role != "patient").order_by(AppUser.created_at)
    if filter:
        match = re.fullmatch(r'\s*userName\s+eq\s+"([^"]+)"\s*', filter)
        if not match:
            raise _error(400, "Only 'userName eq \"...\"' filters are supported.", "invalidFilter")
        query = query.where(AppUser.email == match.group(1).strip().lower())
    total = (await db.execute(select(func.count()).select_from(query.subquery()))).scalar() or 0
    users = (await db.execute(query.offset(max(startIndex, 1) - 1).limit(min(max(count, 0), 500)))).scalars().all()
    return _scim({"schemas": [LIST_SCHEMA], "totalResults": total, "startIndex": max(startIndex, 1),
                  "itemsPerPage": len(users), "Resources": [_resource(u) for u in users]})


@router.get("/Users/{user_id}", dependencies=[Depends(_require_scim_token)])
async def get_user(user_id: str, db: AsyncSession = Depends(get_db)):
    return _scim(_resource(await _get_user(db, user_id)))


@router.post("/Users", dependencies=[Depends(_require_scim_token)])
async def create_user(payload: Dict[str, Any], db: AsyncSession = Depends(get_db)):
    email = str(payload.get("userName") or "").strip().lower()
    if not email or "@" not in email:
        raise _error(400, "userName must be the user's email address.", "invalidValue")
    role = _role_from(payload)
    if role is None:
        raise _error(400, "No MedChain staff role in roles or mapped groups.", "invalidValue")
    if (await db.execute(select(AppUser.id).where(AppUser.email == email))).scalar_one_or_none():
        raise _error(409, "A user with this userName already exists.", "uniqueness")
    user = AppUser(
        email=email, role=role, auth_source="SCIM", is_active=bool(payload.get("active", True)),
        password_hash="!sso-only:" + secrets.token_hex(16),
        external_subject=(str(payload["externalId"])[:255] if payload.get("externalId") else None),
    )
    db.add(user)
    await db.flush()
    await record_access_event(db, user.id, None, "PROVISIONING", user.id, "SCIM_CREATE", "GRANTED",
                              "BY_IDENTITY_PROVIDER", commit=False)
    await db.commit()
    return _scim(_resource(user), status_code=201)


@router.put("/Users/{user_id}", dependencies=[Depends(_require_scim_token)])
async def replace_user(user_id: str, payload: Dict[str, Any], db: AsyncSession = Depends(get_db)):
    user = await _get_user(db, user_id)
    role = _role_from(payload)
    if role:
        user.role = role
    if payload.get("userName"):
        user.email = str(payload["userName"]).strip().lower()
    await _set_active(db, user, bool(payload.get("active", True)))
    await db.commit()
    return _scim(_resource(user))


@router.patch("/Users/{user_id}", dependencies=[Depends(_require_scim_token)])
async def patch_user(user_id: str, payload: Dict[str, Any], db: AsyncSession = Depends(get_db)):
    user = await _get_user(db, user_id)
    operations: List[Dict[str, Any]] = payload.get("Operations") or []
    for operation in operations:
        op = str(operation.get("op", "")).lower()
        path = str(operation.get("path") or "")
        value = operation.get("value")
        if op not in ("replace", "add"):
            raise _error(400, f"Unsupported PATCH op '{op}'.", "invalidSyntax")
        updates = value if (not path and isinstance(value, dict)) else {path: value}
        for key, item in updates.items():
            if key == "active":
                await _set_active(db, user, item in (True, "true", "True"))
            elif key == "roles":
                role = _role_from({"roles": item if isinstance(item, list) else [item]})
                if role is None:
                    raise _error(400, "Unknown role.", "invalidValue")
                user.role = role
            elif key == "userName":
                user.email = str(item).strip().lower()
    await db.commit()
    return _scim(_resource(user))


@router.delete("/Users/{user_id}", dependencies=[Depends(_require_scim_token)], status_code=204)
async def delete_user(user_id: str, db: AsyncSession = Depends(get_db)):
    user = await _get_user(db, user_id)
    await _set_active(db, user, False)
    await db.commit()
    return Response(status_code=204)
