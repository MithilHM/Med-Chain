"""Hospital identity (MFA, SSO, SCIM, rate limiting), encrypted names, ADT lifecycle, merges,
key rotation, graph integrity, and operational alerting."""
import hashlib
import time
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from httpx import ASGITransport, AsyncClient
from jose import jwk, jwt
from sqlalchemy import select

from hl7_helpers import adt, oru, post_hl7, ts
from src import database
from src.config import settings
from src.main import app
from src.models import AppUser, CareTeamAssignment, OutboxEvent, Patient, Visit
from src.services import key_rotation, mfa, monitoring, oidc
from src.services.auth import create_access_token, hash_password, register_user_session
from src.services.events import ClinicalEvent
from src.services.neo4j_sync import GraphSyncService


async def _admin(client):
    auth = (await client.post("/api/v1/auth/demo-switch?role=admin")).json()
    return {"Authorization": f"Bearer {auth['access_token']}"}


async def _doctor(client):
    auth = (await client.post("/api/v1/auth/demo-switch?role=doctor")).json()
    return {"Authorization": f"Bearer {auth['access_token']}"}


async def _new_user(role: str, password: str = "Correct-Horse-Battery-9") -> str:
    email = f"{role}-{uuid.uuid4().hex[:8]}@hospital.test"
    async with database.AsyncSessionLocal() as db:
        db.add(AppUser(email=email, password_hash=hash_password(password), role=role))
        await db.commit()
    return email


# ---------------------------------------------------------------- MFA

@pytest.mark.asyncio
async def test_totp_enrollment_two_step_login_replay_and_recovery(client):
    email = await _new_user("researcher")
    login = (await client.post("/api/v1/auth/login", json={"email": email, "password": "Correct-Horse-Battery-9"})).json()
    headers = {"Authorization": f"Bearer {login['access_token']}"}

    enrolled = (await client.post("/api/v1/auth/mfa/enroll", headers=headers)).json()
    secret = enrolled["secret"]
    assert enrolled["otpauth_uri"].startswith("otpauth://totp/")
    step0 = int(time.time() // 30)
    activated = await client.post("/api/v1/auth/mfa/activate", json={"code": mfa._hotp(secret, step0)}, headers=headers)
    assert activated.status_code == 200, activated.text
    recovery_codes = activated.json()["recovery_codes"]
    assert len(recovery_codes) == mfa.RECOVERY_CODE_COUNT

    challenge = (await client.post("/api/v1/auth/login", json={"email": email, "password": "Correct-Horse-Battery-9"})).json()
    assert challenge["mfa_required"] is True and "user" not in challenge  # no session before the second factor

    replay = await client.post("/api/v1/auth/mfa/verify", json={"mfa_token": challenge["mfa_token"], "code": mfa._hotp(secret, step0)})
    assert replay.status_code == 401  # the activation code cannot be reused

    ok = await client.post("/api/v1/auth/mfa/verify", json={"mfa_token": challenge["mfa_token"], "code": mfa._hotp(secret, step0 + 1)})
    assert ok.status_code == 200 and ok.json()["user"]["mfa_enabled"] is True

    for expected in (200, 401):  # recovery codes are single use
        challenge = (await client.post("/api/v1/auth/login", json={"email": email, "password": "Correct-Horse-Battery-9"})).json()
        res = await client.post("/api/v1/auth/mfa/verify", json={"mfa_token": challenge["mfa_token"], "code": recovery_codes[0]})
        assert res.status_code == expected


@pytest.mark.asyncio
async def test_mfa_required_role_cannot_sign_in_without_enrollment(client, monkeypatch):
    monkeypatch.setattr(settings, "MFA_REQUIRED_ROLES", "insurance_analyst")
    email = await _new_user("insurance_analyst")
    res = await client.post("/api/v1/auth/login", json={"email": email, "password": "Correct-Horse-Battery-9"})
    assert res.status_code == 403


@pytest.mark.asyncio
async def test_login_rate_limit_is_shared_in_the_database(monkeypatch):
    monkeypatch.setattr(settings, "LOGIN_RATE_LIMIT_PER_MINUTE", 3)
    transport = ASGITransport(app=app, client=(f"10.{uuid.uuid4().int % 250}.7.7", 4321))
    async with AsyncClient(transport=transport, base_url="http://test") as other_client:
        codes = [
            (await other_client.post("/api/v1/auth/login", json={"email": "nobody@hospital.test", "password": "x"})).status_code
            for _ in range(4)
        ]
    assert codes == [401, 401, 401, 429]


# ---------------------------------------------------------------- SSO (OIDC)

def _mock_identity_provider(monkeypatch, issuer="https://idp.test"):
    private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_pem = private.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                        serialization.NoEncryption()).decode()
    public_pem = private.public_key().public_bytes(serialization.Encoding.PEM,
                                                   serialization.PublicFormat.SubjectPublicKeyInfo).decode()
    public_jwk = {**jwk.construct(public_pem, "RS256").to_dict(), "kid": "test-key", "use": "sig"}
    discovery = {
        "issuer": issuer, "authorization_endpoint": f"{issuer}/authorize", "token_endpoint": f"{issuer}/token",
        "jwks_uri": f"{issuer}/jwks", "id_token_signing_alg_values_supported": ["RS256"],
    }
    state = {"claims": {}}

    async def fake_get(url):
        return discovery if url.endswith("/.well-known/openid-configuration") else {"keys": [public_jwk]}

    async def fake_post(url, data):
        assert data["code_verifier"] and data["grant_type"] == "authorization_code"
        token = jwt.encode(state["claims"], private_pem, algorithm="RS256", headers={"kid": "test-key"})
        return {"id_token": token, "token_type": "Bearer"}

    for name, value in {
        "OIDC_ENABLED": True, "OIDC_ISSUER": issuer, "OIDC_CLIENT_ID": "medchain",
        "OIDC_REDIRECT_URI": "http://test/api/v1/auth/oidc/callback", "OIDC_ROLE_MAP": "MC-Doctors:doctor",
        "OIDC_ALLOW_JIT_PROVISIONING": True,
    }.items():
        monkeypatch.setattr(settings, name, value)
    monkeypatch.setattr(oidc, "_http_get_json", fake_get)
    monkeypatch.setattr(oidc, "_http_post_form", fake_post)
    oidc.reset_caches()
    return state


async def _start_sso(client):
    start = await client.get("/api/v1/auth/oidc/login")
    assert start.status_code == 302
    assert "code_challenge_method=S256" in start.headers["location"]
    saved = jwt.decode(start.cookies[oidc.STATE_COOKIE], settings.SECRET_KEY, algorithms=["HS256"])
    return saved


def _claims(saved, **overrides):
    now = int(time.time())
    claims = {"iss": "https://idp.test", "aud": "medchain", "sub": f"user-{uuid.uuid4().hex[:6]}", "iat": now,
              "exp": now + 300, "nonce": saved["nonce"], "email": f"sso-{uuid.uuid4().hex[:6]}@hospital.test",
              "email_verified": True, "groups": ["MC-Doctors"]}
    claims.update(overrides)
    return claims


@pytest.mark.asyncio
async def test_oidc_sso_login_provisions_mapped_role(client, monkeypatch):
    idp = _mock_identity_provider(monkeypatch)
    saved = await _start_sso(client)
    idp["claims"] = _claims(saved)
    callback = await client.get(f"/api/v1/auth/oidc/callback?code=abc&state={saved['state']}")
    assert callback.status_code == 302, callback.text
    me = await client.get("/api/v1/auth/me")  # authenticated by the HttpOnly session cookie
    assert me.status_code == 200
    assert me.json()["role"] == "doctor" and me.json()["auth_source"] == "OIDC"


@pytest.mark.asyncio
async def test_oidc_rejects_bad_nonce_bad_state_and_unmapped_groups(client, monkeypatch):
    idp = _mock_identity_provider(monkeypatch)
    saved = await _start_sso(client)
    idp["claims"] = _claims(saved, nonce="attacker-nonce")
    assert (await client.get(f"/api/v1/auth/oidc/callback?code=abc&state={saved['state']}")).status_code == 401

    saved = await _start_sso(client)
    idp["claims"] = _claims(saved)
    assert (await client.get("/api/v1/auth/oidc/callback?code=abc&state=forged-state")).status_code == 401

    saved = await _start_sso(client)
    idp["claims"] = _claims(saved, groups=["Facilities-Staff"])
    assert (await client.get(f"/api/v1/auth/oidc/callback?code=abc&state={saved['state']}")).status_code == 403

    saved = await _start_sso(client)
    idp["claims"] = _claims(saved, aud="some-other-app")
    assert (await client.get(f"/api/v1/auth/oidc/callback?code=abc&state={saved['state']}")).status_code == 401


# ---------------------------------------------------------------- SCIM

@pytest.mark.asyncio
async def test_scim_provisioning_and_deprovisioning_revokes_sessions(client, monkeypatch):
    token = "scim-token-for-tests-0123456789"
    monkeypatch.setattr(settings, "SCIM_BEARER_TOKEN_HASH", hashlib.sha256(token.encode()).hexdigest())
    scim = {"Authorization": f"Bearer {token}"}
    assert (await client.get("/api/v1/scim/v2/Users")).status_code == 401

    email = f"nurse-{uuid.uuid4().hex[:6]}@hospital.test"
    created = await client.post("/api/v1/scim/v2/Users", headers=scim,
                                json={"userName": email, "active": True, "roles": [{"value": "doctor"}]})
    assert created.status_code == 201, created.text
    user_id = created.json()["id"]
    listed = (await client.get(f'/api/v1/scim/v2/Users?filter=userName eq "{email}"', headers=scim)).json()
    assert listed["totalResults"] == 1

    async with database.AsyncSessionLocal() as db:
        session_token, jti, expires = create_access_token({"sub": user_id, "role": "doctor"})
        await register_user_session(db, user_id, jti, expires)
        await db.commit()
    user_headers = {"Authorization": f"Bearer {session_token}"}
    assert (await client.get("/api/v1/auth/me", headers=user_headers)).status_code == 200

    patched = await client.patch(f"/api/v1/scim/v2/Users/{user_id}", headers=scim, json={
        "schemas": ["urn:ietf:params:scim:api:messages:2.0:PatchOp"],
        "Operations": [{"op": "replace", "path": "active", "value": False}],
    })
    assert patched.status_code == 200 and patched.json()["active"] is False
    assert (await client.get("/api/v1/auth/me", headers=user_headers)).status_code == 401  # revoked at once


# ---------------------------------------------------------------- Encrypted names

@pytest.mark.asyncio
async def test_patient_names_are_encrypted_searchable_and_care_role_only(client):
    headers = await _admin(client)
    created = await client.post("/api/v1/patients", headers=headers, json={
        "display_code": f"PT-NAME-{uuid.uuid4().hex[:5]}", "date_of_birth": "1990-03-03", "sex": "F",
        "given_name": "Jane", "family_name": "Doé",
    })
    assert created.status_code == 200, created.text
    patient_id = created.json()["id"]
    assert created.json()["display_name"] == "DOÉ, Jane"

    found = (await client.get("/api/v1/patients?family_name=doe", headers=headers)).json()
    assert any(p["id"] == patient_id for p in found)  # accent- and case-insensitive exact match

    async with database.AsyncSessionLocal() as db:
        patient = await db.get(Patient, patient_id)
        assert patient.name_encrypted.startswith("v2:") and "Jane" not in patient.name_encrypted

    graph = (await client.get("/api/v1/graph/overview", headers=headers)).json()
    for node in graph["nodes"]:
        if node["label"] == "Patient":
            assert set(node["properties"]) <= {"pseudonym", "sex"}  # no MRNs or names in the graph


# ---------------------------------------------------------------- ADT lifecycle

@pytest.mark.asyncio
async def test_adt_transfer_discharge_access_expiry_and_cancellations(client):
    headers, doctor_headers = await _admin(client), await _doctor(client)
    mrn, visit_number = f"MRN-LC-{uuid.uuid4().hex[:5]}", f"V-LC-{uuid.uuid4().hex[:5]}"

    admitted = await post_hl7(client, headers, adt("A01", mrn, visit_number, name="ROE^MARY"))
    assert admitted["status"] == "PROCESSED", admitted
    patient_id = admitted["patient_id"]
    profile = (await client.get(f"/api/v1/patients/{patient_id}", headers=headers)).json()
    assert profile["display_name"] == "ROE, MARY"

    moved = await post_hl7(client, headers, adt("A02", mrn, visit_number, location="WARD7^12^B^MAMC"))
    assert moved["status"] == "PROCESSED", moved

    long_ago = ts(datetime.now(timezone.utc) - timedelta(days=60))
    discharged = await post_hl7(client, headers, adt("A03", mrn, visit_number, extra_pv1={45: long_ago}))
    assert discharged["status"] == "PROCESSED", discharged
    # Discharged 60 days ago with a 30-day window: admission-based access has ended.
    assert (await client.get(f"/api/v1/patients/{patient_id}", headers=doctor_headers)).status_code == 403

    reopened = await post_hl7(client, headers, adt("A13", mrn, visit_number))
    assert reopened["status"] == "PROCESSED", reopened
    assert (await client.get(f"/api/v1/patients/{patient_id}", headers=doctor_headers)).status_code == 200

    # A11 is refused once results are attached ...
    assert (await post_hl7(client, headers, oru(mrn, visit_number)))["status"] == "PROCESSED"
    refused = await post_hl7(client, headers, adt("A11", mrn, visit_number))
    assert refused["status"] == "NEEDS_REVIEW" and "attached" in refused["detail"]
    # ... and applied to an empty visit entered in error.
    second_visit = f"V-LC2-{uuid.uuid4().hex[:5]}"
    assert (await post_hl7(client, headers, adt("A01", mrn, second_visit)))["status"] == "PROCESSED"
    cancelled = await post_hl7(client, headers, adt("A11", mrn, second_visit))
    assert cancelled["status"] == "PROCESSED", cancelled

    async with database.AsyncSessionLocal() as db:
        first = (await db.execute(select(Visit).where(Visit.external_visit_number == visit_number))).scalar_one()
        second = (await db.execute(select(Visit).where(Visit.external_visit_number == second_visit))).scalar_one()
        assert first.summary_code == "WARD7" and first.discharged_at is None and first.status == "ACTIVE"
        assert second.status == "CANCELLED"
    timeline = (await client.get(f"/api/v1/patients/{patient_id}/timeline", headers=headers)).json()
    assert [v["id"] for v in timeline["visits"]] == [first.id]  # cancelled visits are hidden by default


@pytest.mark.asyncio
async def test_facility_allow_list_rejects_other_hospitals(client, monkeypatch):
    monkeypatch.setattr(settings, "HOSPITAL_FACILITY_CODES", "SJRH")
    headers = await _admin(client)
    res = await post_hl7(client, headers, adt("A01", f"MRN-{uuid.uuid4().hex[:5]}", f"V-{uuid.uuid4().hex[:5]}"))
    assert res["ack_code"] == "AR" and "not served" in res["detail"]


# ---------------------------------------------------------------- Merges

@pytest.mark.asyncio
async def test_a40_merge_requires_approval_and_moves_records(client):
    headers = await _admin(client)
    keep_mrn, dup_mrn = f"MRN-KEEP-{uuid.uuid4().hex[:4]}", f"MRN-DUP-{uuid.uuid4().hex[:4]}"
    dup_visit = f"V-DUP-{uuid.uuid4().hex[:4]}"
    keep = await post_hl7(client, headers, adt("A04", keep_mrn, f"V-K-{uuid.uuid4().hex[:4]}", dob="19850505"))
    dup = await post_hl7(client, headers, adt("A04", dup_mrn, dup_visit, dob="19850505"))
    survivor_id, retiring_id = keep["patient_id"], dup["patient_id"]

    merge = await post_hl7(client, headers, adt("A40", keep_mrn, "", dob="19850505",
                                                extra_segments=[f"MRG|{dup_mrn}^^^MAMC^MR"]))
    assert merge["status"] == "NEEDS_REVIEW" and merge["ack_code"] == "AA"
    async with database.AsyncSessionLocal() as db:
        assert (await db.get(Patient, retiring_id)).record_status == "ACTIVE"  # nothing merged yet

    pending = (await client.get("/api/v1/integration/merges", headers=headers)).json()
    request = next(r for r in pending if r["retiring_patient_id"] == retiring_id)
    approved = await client.post(f"/api/v1/integration/merges/{request['id']}/approve", json={"note": "Same person"}, headers=headers)
    assert approved.status_code == 200, approved.text
    assert approved.json()["moved_counts"]["visits"] == 1 and approved.json()["moved_counts"]["identifiers"] >= 1

    retired = (await client.get(f"/api/v1/patients/{retiring_id}", headers=headers)).json()
    assert retired["record_status"] == "MERGED" and retired["merged_into_id"] == survivor_id
    blocked = await client.post("/api/v1/documents", headers=headers, json={
        "patient_id": retiring_id, "document_type": "Progress Note", "title": "x", "content": "y"})
    assert blocked.status_code == 409
    # The duplicate's MRN and visit now resolve to the surviving record.
    result = await post_hl7(client, headers, oru(dup_mrn, dup_visit))
    assert result["status"] == "PROCESSED" and result["patient_id"] == survivor_id


@pytest.mark.asyncio
async def test_operator_merge_needs_a_second_administrator(client):
    headers = await _admin(client)
    a = await post_hl7(client, headers, adt("A04", f"MRN-A-{uuid.uuid4().hex[:4]}", f"V-A-{uuid.uuid4().hex[:4]}", dob="19770707"))
    b = await post_hl7(client, headers, adt("A04", f"MRN-B-{uuid.uuid4().hex[:4]}", f"V-B-{uuid.uuid4().hex[:4]}", dob="19770707"))
    proposal = (await client.post("/api/v1/integration/merges", headers=headers, json={
        "surviving_patient_id": a["patient_id"], "retiring_patient_id": b["patient_id"], "reason": "Duplicate registration"})).json()
    self_approval = await client.post(f"/api/v1/integration/merges/{proposal['id']}/approve", json={}, headers=headers)
    assert self_approval.status_code == 409


# ---------------------------------------------------------------- Key rotation

@pytest.mark.asyncio
async def test_key_rotation_reencrypts_everything_and_data_stays_readable(client, monkeypatch):
    headers = await _admin(client)
    doc = (await client.post("/api/v1/documents", headers=headers, json={
        "patient_id": "PT-100201", "document_type": "Progress Note", "title": "Rotation", "content": "Key rotation check"})).json()
    ring = f"k1:{'0' * 64},k2:{'ab' * 32}"
    monkeypatch.setattr(settings, "DOCUMENT_ENCRYPTION_KEYS", ring)
    try:
        monkeypatch.setattr(settings, "DOCUMENT_ENCRYPTION_ACTIVE_KEY_ID", "k2")
        await key_rotation.rotate()
        report = await key_rotation.status()
        assert all(set(counts) <= {"k2"} for counts in report.values()), report
        detail = await client.get(f"/api/v1/documents/{doc['id']}", headers=headers)
        assert detail.status_code == 200 and detail.json()["content"] == "Key rotation check"
    finally:
        # Rotate back so the rest of the suite runs with the default key ring.
        monkeypatch.setattr(settings, "DOCUMENT_ENCRYPTION_ACTIVE_KEY_ID", "k1")
        await key_rotation.rotate()
    assert all(set(counts) <= {"k1"} for counts in (await key_rotation.status()).values())


# ---------------------------------------------------------------- Graph

@pytest.mark.asyncio
async def test_graph_rebuild_never_invents_side_effect_data(client):
    headers = await _admin(client)
    assert (await client.post("/api/v1/admin/graph/rebuild", headers=headers)).status_code == 200
    assert await GraphSyncService.find_side_effect_profiles("NO-SUCH-CODE") == []
    for profile in await GraphSyncService.find_side_effect_profiles("E11"):
        assert isinstance(profile["patient_count"], int) and profile["patient_count"] >= 1


# ---------------------------------------------------------------- Alerts and metrics

@pytest.mark.asyncio
async def test_alerts_open_notify_and_resolve(client, monkeypatch):
    sent = []

    async def capture(alert, transition):
        sent.append((alert.alert_key, transition))
        return True

    monkeypatch.setattr(monitoring, "_notify", capture)
    async with database.AsyncSessionLocal() as db:
        event = OutboxEvent(event_type="BLOCKCHAIN_ACCESS_EVENT", aggregate_id="alert-test", payload_json={},
                            status="FAILED", attempt_count=12, max_retries=12, last_error="test")
        db.add(event)
        await db.commit()
        event_id = event.id

    await monitoring.run_evaluation()
    assert ("outbox.failed", "OPENED") in sent
    headers = await _admin(client)
    open_alerts = (await client.get("/api/v1/admin/alerts", headers=headers)).json()
    assert any(a["alert_key"] == "outbox.failed" and a["notified_at"] for a in open_alerts)

    async with database.AsyncSessionLocal() as db:
        (await db.get(OutboxEvent, event_id)).status = "COMPLETED"
        await db.commit()
    await monitoring.run_evaluation()
    assert ("outbox.failed", "RESOLVED") in sent


@pytest.mark.asyncio
async def test_prometheus_metrics_require_token_or_admin(client, monkeypatch):
    assert (await client.get("/metrics")).status_code == 401
    token = "metrics-scrape-token-0123456789"
    monkeypatch.setattr(settings, "METRICS_BEARER_TOKEN_HASH", hashlib.sha256(token.encode()).hexdigest())
    scraped = await client.get("/metrics", headers={"Authorization": f"Bearer {token}"})
    assert scraped.status_code == 200
    assert "medchain_outbox_events" in scraped.text and "medchain_inbound_messages" in scraped.text


def test_clinical_event_wire_round_trip():
    event = ClinicalEvent("lab_result.created", "P1", {"critical": True}, admin_only=False)
    again = ClinicalEvent.from_wire(event.to_wire())
    assert again.as_payload() == event.as_payload() and again.admin_only is False
