"""OpenID Connect single sign-on against the hospital identity provider.

Authorization code flow with PKCE (S256), state and nonce bound to a short-lived signed cookie.
The ID token is verified against the provider's JWKS (signature, issuer, audience, expiry, nonce,
and at_hash when present). Roles come from a configured claim (e.g. directory groups) through
OIDC_ROLE_MAP; users without a mapped group are refused. MFA is expected to be enforced by the
identity provider; OIDC_REQUIRE_MFA_CLAIM additionally checks the `amr` claim.
"""
import base64
import hashlib
import secrets
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional, Tuple
from urllib.parse import urlencode

import httpx
from jose import jwt
from jose.exceptions import JOSEError

from src.config import settings

STATE_COOKIE = "medchain_oidc"
_STATE_TTL_SECONDS = 600
_CACHE_TTL_SECONDS = 3600
_discovery_cache: Dict[str, Any] = {"value": None, "at": 0.0}
_jwks_cache: Dict[str, Any] = {"value": None, "at": 0.0}


class OIDCError(Exception):
    pass


async def _http_get_json(url: str) -> Dict[str, Any]:
    async with httpx.AsyncClient(timeout=10) as client:
        response = await client.get(url)
        response.raise_for_status()
        return response.json()


async def _http_post_form(url: str, data: Dict[str, str]) -> Dict[str, Any]:
    async with httpx.AsyncClient(timeout=10) as client:
        response = await client.post(url, data=data, headers={"Accept": "application/json"})
        if response.status_code >= 400:
            raise OIDCError(f"Token endpoint returned {response.status_code}.")
        return response.json()


def reset_caches() -> None:
    _discovery_cache.update(value=None, at=0.0)
    _jwks_cache.update(value=None, at=0.0)


async def discovery() -> Dict[str, Any]:
    if _discovery_cache["value"] and time.time() - _discovery_cache["at"] < _CACHE_TTL_SECONDS:
        return _discovery_cache["value"]
    issuer = settings.OIDC_ISSUER.rstrip("/")
    document = await _http_get_json(f"{issuer}/.well-known/openid-configuration")
    if document.get("issuer", "").rstrip("/") != issuer:
        raise OIDCError("Discovery document issuer does not match OIDC_ISSUER.")
    _discovery_cache.update(value=document, at=time.time())
    return document


async def _jwks(force_refresh: bool = False) -> Dict[str, Any]:
    if not force_refresh and _jwks_cache["value"] and time.time() - _jwks_cache["at"] < _CACHE_TTL_SECONDS:
        return _jwks_cache["value"]
    keys = await _http_get_json((await discovery())["jwks_uri"])
    _jwks_cache.update(value=keys, at=time.time())
    return keys


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


async def authorization_request() -> Tuple[str, str]:
    """Return (redirect URL, signed state cookie value)."""
    config = await discovery()
    state, nonce = secrets.token_urlsafe(24), secrets.token_urlsafe(24)
    verifier = secrets.token_urlsafe(48)
    challenge = _b64url(hashlib.sha256(verifier.encode("ascii")).digest())
    params = {
        "response_type": "code",
        "client_id": settings.OIDC_CLIENT_ID,
        "redirect_uri": settings.OIDC_REDIRECT_URI,
        "scope": settings.OIDC_SCOPES,
        "state": state,
        "nonce": nonce,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
    }
    cookie = jwt.encode(
        {"state": state, "nonce": nonce, "verifier": verifier, "purpose": "oidc_state",
         "exp": datetime.now(timezone.utc) + timedelta(seconds=_STATE_TTL_SECONDS)},
        settings.SECRET_KEY, algorithm="HS256",
    )
    return f"{config['authorization_endpoint']}?{urlencode(params)}", cookie


def _read_state_cookie(cookie: Optional[str], state: str) -> Dict[str, Any]:
    if not cookie:
        raise OIDCError("Sign-in session expired; start again.")
    try:
        data = jwt.decode(cookie, settings.SECRET_KEY, algorithms=["HS256"])
    except JOSEError as exc:
        raise OIDCError("Sign-in session expired; start again.") from exc
    if data.get("purpose") != "oidc_state" or not secrets.compare_digest(str(data.get("state")), state or ""):
        raise OIDCError("Sign-in state mismatch.")
    return data


async def complete_login(code: str, state: str, state_cookie: Optional[str]) -> Dict[str, Any]:
    """Exchange the code and return verified ID-token claims."""
    saved = _read_state_cookie(state_cookie, state)
    config = await discovery()
    form = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": settings.OIDC_REDIRECT_URI,
        "client_id": settings.OIDC_CLIENT_ID,
        "code_verifier": saved["verifier"],
    }
    if settings.OIDC_CLIENT_SECRET:
        form["client_secret"] = settings.OIDC_CLIENT_SECRET
    tokens = await _http_post_form(config["token_endpoint"], form)
    id_token = tokens.get("id_token")
    if not id_token:
        raise OIDCError("Identity provider did not return an ID token.")

    algorithms = config.get("id_token_signing_alg_values_supported") or ["RS256"]
    algorithms = [alg for alg in algorithms if alg != "none" and not alg.startswith("HS")] or ["RS256"]
    decode_args = dict(
        algorithms=algorithms, audience=settings.OIDC_CLIENT_ID, issuer=config["issuer"],
        access_token=tokens.get("access_token"),
    )
    try:
        claims = jwt.decode(id_token, await _jwks(), **decode_args)
    except JOSEError:
        try:  # the provider may have rotated its signing keys
            claims = jwt.decode(id_token, await _jwks(force_refresh=True), **decode_args)
        except JOSEError as exc:
            raise OIDCError("ID token validation failed.") from exc
    if not secrets.compare_digest(str(claims.get("nonce", "")), saved["nonce"]):
        raise OIDCError("ID token nonce mismatch.")
    if settings.OIDC_REQUIRE_MFA_CLAIM and "mfa" not in (claims.get("amr") or []):
        raise OIDCError("The identity provider did not report multi-factor authentication.")
    return claims


def role_from_claims(claims: Dict[str, Any]) -> Optional[str]:
    """First OIDC_ROLE_MAP entry (in configured order) whose group appears in the role claim."""
    raw = claims.get(settings.OIDC_ROLE_CLAIM) or []
    groups = {raw} if isinstance(raw, str) else set(raw)
    for group, role in settings.oidc_role_map.items():
        if group in groups:
            return role
    return None


def subject_key(claims: Dict[str, Any]) -> str:
    return f"{claims['iss']}|{claims['sub']}"[:255]
