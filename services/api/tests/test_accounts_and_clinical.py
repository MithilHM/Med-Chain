"""Sign-up (patient portal, staff activation, password reset), user administration,
patient administration (care team, demographics, allergies), and clinical data entry."""
import uuid

import pytest


async def _headers(client, role):
    auth = (await client.post(f"/api/v1/auth/demo-switch?role={role}")).json()
    return {"Authorization": f"Bearer {auth['access_token']}"}


async def _register(client, admin, **extra):
    hospitals = (await client.get("/api/v1/admin/hospitals", headers=admin)).json()
    res = await client.post("/api/v1/patients", headers=admin, json={
        "display_code": f"PT-{uuid.uuid4().hex[:8].upper()}", "date_of_birth": "1984-03-09", "sex": "F",
        "given_name": "Asha", "family_name": "Rao", "hospital_id": hospitals[0]["id"], **extra})
    assert res.status_code == 200, res.text
    return res.json()


# ---------------------------------------------------------------- Patient portal sign-up

@pytest.mark.asyncio
async def test_patient_portal_signup_with_activation_code(client):
    admin = await _headers(client, "admin")
    patient = await _register(client, admin, issue_portal_invitation=True)
    code = patient["portal_activation_code"]
    assert code and patient["portal_activation_expires_at"]

    preview = (await client.get(f"/api/v1/auth/invitations/{code}")).json()
    assert preview["purpose"] == "PATIENT_PORTAL" and preview["requires_date_of_birth"] is True

    email = f"asha-{uuid.uuid4().hex[:6]}@mail.test"
    wrong_dob = await client.post("/api/v1/auth/signup", json={
        "token": code, "email": email, "date_of_birth": "1990-01-01", "password": "Strong-passw0rd-2026"})
    assert wrong_dob.status_code == 400 and "do not match" in wrong_dob.json()["detail"]
    weak = await client.post("/api/v1/auth/signup", json={
        "token": code, "email": email, "date_of_birth": "1984-03-09", "password": "short1"})
    assert weak.status_code == 422

    done = await client.post("/api/v1/auth/signup", json={
        "token": code.lower().replace("-", " "),  # codes are case/spacing tolerant
        "email": email, "date_of_birth": "1984-03-09", "password": "Strong-passw0rd-2026"})
    assert done.status_code == 200, done.text
    assert done.json()["user"]["role"] == "patient" and done.json()["user"]["patient_id"] == patient["id"]

    # The portal account sees exactly its own record, and the code cannot be reused.
    login = (await client.post("/api/v1/auth/login", json={"email": email, "password": "Strong-passw0rd-2026"})).json()
    mine = (await client.get("/api/v1/patients", headers={"Authorization": f"Bearer {login['access_token']}"})).json()
    assert [p["id"] for p in mine] == [patient["id"]]
    assert (await client.post("/api/v1/auth/signup", json={
        "token": code, "email": "x" + email, "date_of_birth": "1984-03-09", "password": "Strong-passw0rd-2026"})).status_code == 400
    assert (await client.post(f"/api/v1/patients/{patient['id']}/portal-invitation", headers=admin)).status_code == 409


@pytest.mark.asyncio
async def test_activation_code_locks_after_repeated_wrong_birth_dates(client):
    admin = await _headers(client, "admin")
    patient = await _register(client, admin)
    code = (await client.post(f"/api/v1/patients/{patient['id']}/portal-invitation", headers=admin)).json()["portal_activation_code"]
    for _ in range(5):
        await client.post("/api/v1/auth/signup", json={
            "token": code, "email": "guess@mail.test", "date_of_birth": "2000-01-01", "password": "Strong-passw0rd-2026"})
    correct = await client.post("/api/v1/auth/signup", json={
        "token": code, "email": "guess@mail.test", "date_of_birth": "1984-03-09", "password": "Strong-passw0rd-2026"})
    assert correct.status_code == 400  # locked: a new code must be issued at the desk


# ---------------------------------------------------------------- Staff accounts

@pytest.mark.asyncio
async def test_staff_account_creation_activation_reset_and_deactivation(client):
    admin = await _headers(client, "admin")
    hospitals = (await client.get("/api/v1/admin/hospitals", headers=admin)).json()
    email = f"dr-{uuid.uuid4().hex[:6]}@hospital.test"
    created = await client.post("/api/v1/admin/users", headers=admin, json={
        "email": email, "role": "doctor", "display_name": "Dr. Meera Iyer", "specialty": "Nephrology",
        "hospital_id": hospitals[0]["id"], "external_provider_id": f"PRV-{uuid.uuid4().hex[:5]}"})
    assert created.status_code == 200, created.text
    body = created.json()
    assert body["user"]["activation_pending"] is True and body["activation_link"].startswith("/signup?token=")
    user_id, token = body["user"]["id"], body["activation_token"]

    # No password exists until activation.
    assert (await client.post("/api/v1/auth/login", json={"email": email, "password": "anything-12345"})).status_code == 401
    preview = (await client.get(f"/api/v1/auth/invitations/{token}")).json()
    assert preview["purpose"] == "STAFF_ACTIVATION" and preview["role"] == "doctor" and "***" in preview["email"]
    activated = await client.post("/api/v1/auth/signup", json={"token": token, "password": "Nephro-clinic-2026"})
    assert activated.status_code == 200 and activated.json()["user"]["doctor_id"]
    assert any(d["display_name"] == "Dr. Meera Iyer" for d in (await client.get("/api/v1/doctors", headers=admin)).json())

    reset = (await client.post(f"/api/v1/admin/users/{user_id}/password-reset", headers=admin)).json()
    assert reset["purpose"] == "PASSWORD_RESET"
    assert (await client.post("/api/v1/auth/signup", json={"token": reset["activation_token"], "password": "Nephro-ward-2027"})).status_code == 200
    assert (await client.post("/api/v1/auth/login", json={"email": email, "password": "Nephro-clinic-2026"})).status_code == 401
    assert (await client.post("/api/v1/auth/login", json={"email": email, "password": "Nephro-ward-2027"})).status_code == 200

    deactivated = await client.patch(f"/api/v1/admin/users/{user_id}", headers=admin, json={"is_active": False})
    assert deactivated.status_code == 200 and deactivated.json()["is_active"] is False
    assert (await client.post("/api/v1/auth/login", json={"email": email, "password": "Nephro-ward-2027"})).status_code == 401

    me = (await client.get("/api/v1/auth/me", headers=admin)).json()
    assert (await client.patch(f"/api/v1/admin/users/{me['id']}", headers=admin, json={"is_active": False})).status_code == 409
    # A self-reset would revoke the admin's own sessions mid-task.
    assert (await client.post(f"/api/v1/admin/users/{me['id']}/password-reset", headers=admin)).status_code == 409
    assert (await client.get("/api/v1/auth/me", headers=admin)).status_code == 200
    doctor = await _headers(client, "doctor")
    assert (await client.get("/api/v1/admin/users", headers=doctor)).status_code == 403


@pytest.mark.asyncio
async def test_staff_role_rules_and_hospital_directory(client):
    admin = await _headers(client, "admin")
    missing_profile = await client.post("/api/v1/admin/users", headers=admin, json={
        "email": f"doc-{uuid.uuid4().hex[:6]}@hospital.test", "role": "doctor"})
    assert missing_profile.status_code == 422
    researcher = (await client.post("/api/v1/admin/users", headers=admin, json={
        "email": f"res-{uuid.uuid4().hex[:6]}@hospital.test", "role": "researcher"})).json()["user"]
    assert (await client.patch(f"/api/v1/admin/users/{researcher['id']}", headers=admin, json={"role": "doctor"})).status_code == 422
    assert (await client.patch(f"/api/v1/admin/users/{researcher['id']}", headers=admin, json={"role": "admin"})).status_code == 200

    code = f"HOSP{uuid.uuid4().hex[:4].upper()}"
    assert (await client.post("/api/v1/admin/hospitals", headers=admin, json={
        "name": "Riverside Community Hospital", "region": "East", "facility_code": code})).status_code == 200
    assert (await client.post("/api/v1/admin/hospitals", headers=admin, json={
        "name": "Duplicate", "region": "East", "facility_code": code})).status_code == 409


@pytest.mark.asyncio
async def test_change_password(client):
    admin = await _headers(client, "admin")
    email = f"res-{uuid.uuid4().hex[:6]}@hospital.test"
    token = (await client.post("/api/v1/admin/users", headers=admin, json={"email": email, "role": "researcher"})).json()["activation_token"]
    session = (await client.post("/api/v1/auth/signup", json={"token": token, "password": "First-passw0rd-2026"})).json()
    headers = {"Authorization": f"Bearer {session['access_token']}"}
    wrong = await client.post("/api/v1/auth/password", headers=headers,
                              json={"current_password": "nope", "new_password": "Second-passw0rd-2026"})
    assert wrong.status_code == 400
    ok = await client.post("/api/v1/auth/password", headers=headers,
                           json={"current_password": "First-passw0rd-2026", "new_password": "Second-passw0rd-2026"})
    assert ok.status_code == 200
    assert (await client.get("/api/v1/auth/me", headers=headers)).status_code == 401  # old session signed out
    assert (await client.post("/api/v1/auth/login", json={"email": email, "password": "Second-passw0rd-2026"})).status_code == 200


# ---------------------------------------------------------------- Patient administration

@pytest.mark.asyncio
async def test_care_team_assignment_controls_doctor_access(client):
    admin, doctor = await _headers(client, "admin"), await _headers(client, "doctor")
    patient = await _register(client, admin)
    assert (await client.get(f"/api/v1/patients/{patient['id']}", headers=doctor)).status_code == 403

    doctor_id = (await client.get("/api/v1/doctors", headers=admin)).json()[0]["id"]
    added = await client.post(f"/api/v1/patients/{patient['id']}/care-team", headers=admin,
                              json={"doctor_id": doctor_id, "relationship_type": "CONSULTING"})
    assert added.status_code == 200
    assert (await client.get(f"/api/v1/patients/{patient['id']}", headers=doctor)).status_code == 200
    assert (await client.post(f"/api/v1/patients/{patient['id']}/care-team", headers=doctor,
                              json={"doctor_id": doctor_id})).status_code == 403  # admins manage care teams

    ended = await client.delete(f"/api/v1/patients/{patient['id']}/care-team/{added.json()['id']}", headers=admin)
    assert ended.status_code == 200
    assert (await client.get(f"/api/v1/patients/{patient['id']}", headers=doctor)).status_code == 403


@pytest.mark.asyncio
async def test_demographic_corrections_are_admin_only(client):
    admin, doctor = await _headers(client, "admin"), await _headers(client, "doctor")
    doctor_id = (await client.get("/api/v1/doctors", headers=admin)).json()[0]["id"]
    patient = await _register(client, admin, primary_doctor_id=doctor_id)
    assert (await client.patch(f"/api/v1/patients/{patient['id']}", headers=doctor, json={"family_name": "X"})).status_code == 403
    fixed = await client.patch(f"/api/v1/patients/{patient['id']}", headers=admin,
                               json={"family_name": "Rao-Menon", "date_of_birth": "1984-03-10"})
    assert fixed.status_code == 200
    assert fixed.json()["display_name"] == "RAO-MENON, Asha" and fixed.json()["date_of_birth"] == "1984-03-10"


# ---------------------------------------------------------------- Clinical data entry

@pytest.mark.asyncio
async def test_clinical_entry_for_a_newly_registered_patient(client):
    admin, doctor = await _headers(client, "admin"), await _headers(client, "doctor")
    doctor_id = (await client.get("/api/v1/doctors", headers=admin)).json()[0]["id"]
    patient = await _register(client, admin, primary_doctor_id=doctor_id)

    # Previously impossible: the UI sent placeholder doctor/hospital IDs for patients without visits.
    visit = await client.post("/api/v1/visits", headers=doctor, json={
        "patient_id": patient["id"], "visit_type": "Outpatient Consultation", "summary_code": "NEW-PT"})
    assert visit.status_code == 200, visit.text
    visit_id = visit.json()["id"]
    assert visit.json()["hospital_name"]
    assert (await client.post("/api/v1/visits", headers=admin, json={
        "patient_id": patient["id"], "visit_type": "Outpatient Consultation"})).status_code == 422  # admin must pick doctor

    assert (await client.post(f"/api/v1/visits/{visit_id}/diagnoses", headers=doctor,
                              json={"disease_code": "E11.9", "severity": "Moderate"})).status_code == 200
    assert (await client.post(f"/api/v1/visits/{visit_id}/diagnoses", headers=doctor,
                              json={"disease_code": "NOT-A-CODE", "severity": "Mild"})).status_code == 422
    assert (await client.post(f"/api/v1/visits/{visit_id}/prescriptions", headers=doctor, json={
        "medication_code": "RX-860975", "dose_text": "500 mg", "frequency_text": "twice daily"})).status_code == 200
    lab = await client.post(f"/api/v1/visits/{visit_id}/lab-results", headers=doctor,
                            json={"lab_test_code": "LOINC-4548-4", "result_value": 8.1})
    assert lab.status_code == 200 and lab.json()["is_abnormal"] is True  # 8.1 is outside 4.0 - 5.6
    normal = await client.post(f"/api/v1/visits/{visit_id}/lab-results", headers=doctor,
                               json={"lab_test_code": "LOINC-4548-4", "result_value": 5.2})
    assert normal.json()["is_abnormal"] is False

    allergy = await client.post(f"/api/v1/patients/{patient['id']}/allergies", headers=doctor,
                                json={"substance": "Penicillin", "reaction": "Hives", "severity": "SEVERE"})
    assert allergy.status_code == 200
    researcher = await _headers(client, "researcher")
    assert (await client.get(f"/api/v1/patients/{patient['id']}/allergies", headers=researcher)).status_code == 403

    assert (await client.post(f"/api/v1/visits/{visit_id}/discharge", headers=doctor)).status_code == 200
    assert (await client.post(f"/api/v1/visits/{visit_id}/discharge", headers=doctor)).status_code == 409

    timeline = (await client.get(f"/api/v1/patients/{patient['id']}/timeline", headers=doctor)).json()
    recorded = timeline["visits"][0]
    assert recorded["diagnoses"][0]["disease_code"] == "E11.9"
    assert recorded["prescriptions"][0]["medication_code"] == "RX-860975"
    assert len(recorded["lab_results"]) == 2 and recorded["discharged_at"]
    assert recorded["lab_results"][0]["reference_range_text"] == "4.0 - 5.6"
    assert timeline["allergies"][0]["substance"] == "Penicillin" and timeline["facilities"]


@pytest.mark.asyncio
async def test_prescribing_a_drug_the_patient_is_allergic_to_needs_an_override(client):
    admin, doctor = await _headers(client, "admin"), await _headers(client, "doctor")
    doctor_id = (await client.get("/api/v1/doctors", headers=admin)).json()[0]["id"]
    patient = await _register(client, admin, primary_doctor_id=doctor_id)
    visit_id = (await client.post("/api/v1/visits", headers=doctor, json={
        "patient_id": patient["id"], "visit_type": "Outpatient Consultation"})).json()["id"]
    assert (await client.post(f"/api/v1/patients/{patient['id']}/allergies", headers=doctor,
                              json={"substance": "metformin", "reaction": "Lactic acidosis", "severity": "SEVERE"})).status_code == 200
    rx = {"medication_code": "RX-860975", "dose_text": "500 mg", "frequency_text": "twice daily"}  # Metformin

    blocked = await client.post(f"/api/v1/visits/{visit_id}/prescriptions", headers=doctor, json=rx)
    assert blocked.status_code == 409 and blocked.json()["detail"]["code"] == "ALLERGY_CONFLICT"
    assert blocked.json()["detail"]["allergies"][0]["substance"] == "metformin"
    assert (await client.post(f"/api/v1/visits/{visit_id}/prescriptions", headers=doctor,
                              json={**rx, "allergy_override_reason": "too short"})).status_code == 409
    # A drug that does not match the allergy is unaffected.
    assert (await client.post(f"/api/v1/visits/{visit_id}/prescriptions", headers=doctor, json={
        "medication_code": "RX-197361", "dose_text": "5 mg", "frequency_text": "daily"})).status_code == 200

    reason = "Historic reaction disputed by nephrology; benefit outweighs risk"
    given = await client.post(f"/api/v1/visits/{visit_id}/prescriptions", headers=doctor, json={**rx, "allergy_override_reason": reason})
    assert given.status_code == 200 and given.json()["allergy_override_reason"] == reason
    timeline = (await client.get(f"/api/v1/patients/{patient['id']}/timeline", headers=doctor)).json()
    by_code = {p["medication_code"]: p for p in timeline["visits"][0]["prescriptions"]}
    assert by_code["RX-860975"]["allergy_override_reason"] == reason and by_code["RX-197361"]["allergy_override_reason"] is None
    audit = (await client.get(f"/api/v1/audit/events?patient_id={patient['id']}", headers=admin)).json()
    assert any(e["reason_code"] == "ALLERGY_OVERRIDE:RX-860975" for e in audit)


@pytest.mark.asyncio
async def test_session_refresh_keeps_active_users_signed_in_up_to_the_shift_limit(client):
    from datetime import datetime, timedelta, timezone
    from src import database
    from src.config import settings
    from src.models import AppUser, UserSession
    from src.services.auth import create_access_token, decode_access_token, register_user_session
    from sqlalchemy import select

    doctor = await _headers(client, "doctor")
    refreshed = await client.post("/api/v1/auth/refresh", headers=doctor)
    assert refreshed.status_code == 200 and refreshed.json()["idle_timeout_seconds"] == settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60
    new_token = refreshed.cookies.get("medchain_session")
    assert new_token and new_token != doctor["Authorization"][7:]
    assert (await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {new_token}"})).status_code == 200
    # The old token survives only a short grace period for requests already in flight.
    assert (await client.get("/api/v1/auth/me", headers=doctor)).status_code == 200
    async with database.AsyncSessionLocal() as db:
        old = (await db.execute(select(UserSession).where(
            UserSession.token_jti == decode_access_token(doctor["Authorization"][7:])["jti"]))).scalar_one()
        expires = old.expires_at if old.expires_at.tzinfo else old.expires_at.replace(tzinfo=timezone.utc)
        assert expires <= datetime.now(timezone.utc) + timedelta(seconds=31)

        # A session signed in longer ago than SESSION_MAX_HOURS is not extended.
        user = (await db.execute(select(AppUser).where(AppUser.email == "doctor@medchain.local"))).scalar_one()
        signed_in = (datetime.now(timezone.utc) - timedelta(hours=settings.SESSION_MAX_HOURS, minutes=1)).timestamp()
        token, jti, exp = create_access_token({"sub": user.id, "role": user.role, "auth_time": signed_in})
        await register_user_session(db, user.id, jti, exp)
        await db.commit()
    capped = await client.post("/api/v1/auth/refresh", headers={"Authorization": f"Bearer {token}"})
    assert capped.status_code == 401 and "limit" in capped.json()["detail"]
    assert (await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})).status_code == 401
