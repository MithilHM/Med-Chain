import pytest

@pytest.mark.asyncio
async def test_fhir_metadata_capability_statement(client):
    res = await client.get("/api/v1/fhir/metadata")
    assert res.status_code == 200
    data = res.json()
    assert data["resourceType"] == "CapabilityStatement"
    assert data["fhirVersion"] == "4.0.1"
    assert "software" in data

@pytest.mark.asyncio
async def test_fhir_import_and_patient_export(client):
    # Admin switch
    admin_auth = (await client.post("/api/v1/auth/demo-switch?role=admin")).json()
    headers = {"Authorization": f"Bearer {admin_auth['access_token']}"}

    # Standard FHIR R4 Bundle
    sample_bundle = {
        "resourceType": "Bundle",
        "type": "transaction",
        "entry": [
            {
                "fullUrl": "urn:uuid:patient-test-01",
                "resource": {
                    "resourceType": "Patient",
                    "id": "PT-FHIR-9901",
                    "identifier": [{"system": "urn:hospital:mrn", "value": "PT-FHIR-9901"}],
                    "gender": "female",
                    "birthDate": "1988-04-12"
                }
            },
            {
                "fullUrl": "urn:uuid:enc-test-01",
                "resource": {
                    "resourceType": "Encounter",
                    "id": "ENC-001",
                    "identifier": [{"value": "V-FHIR-0001"}],
                    "status": "finished",
                    "class": {"code": "AMB", "display": "Outpatient Consultation"},
                    "period": {"start": "2026-10-01T09:30:00Z", "end": "2026-10-01T10:00:00Z"},
                    "participant": [{"individual": {"identifier": {"value": "PRV-1001"}}}],
                    "serviceProvider": {"identifier": {"value": "MAMC"}}
                }
            },
            {
                "fullUrl": "urn:uuid:cond-test-01",
                "resource": {
                    "resourceType": "Condition",
                    "id": "COND-001",
                    "code": {
                        "coding": [
                            {"system": "http://hl7.org/fhir/sid/icd-10", "code": "E11.9", "display": "Type 2 diabetes mellitus"}
                        ]
                    }
                }
            }
        ]
    }

    import_res = await client.post("/api/v1/fhir/import", json=sample_bundle, headers=headers)
    assert import_res.status_code == 200
    import_data = import_res.json()
    assert import_data["status"] == "RECONCILED"
    target_id = import_data["target_patient_id"]

    # Export back as standard FHIR R4 bundle
    export_res = await client.get(f"/api/v1/fhir/patients/{target_id}/export", headers=headers)
    assert export_res.status_code == 200
    export_bundle = export_res.json()
    assert export_bundle["resourceType"] == "Bundle"
    assert export_bundle["total"] >= 2
    resource_types = [e["resource"]["resourceType"] for e in export_bundle["entry"]]
    assert "Patient" in resource_types
    encounter = next(e["resource"] for e in export_bundle["entry"] if e["resource"]["resourceType"] == "Encounter")
    assert encounter["period"]["start"].startswith("2026-10-01T09:30")  # real encounter time, not import time

    # Re-importing the same encounter must not duplicate the visit.
    again = (await client.post("/api/v1/fhir/import", json=sample_bundle, headers=headers)).json()
    assert again["status"] in ("RECONCILED", "DUPLICATE")
    if again["status"] == "RECONCILED":
        assert again["reconciliation_summary"]["encounters_recorded"] == 0


@pytest.mark.asyncio
async def test_fhir_import_rejects_unsafe_bundles(client):
    admin_auth = (await client.post("/api/v1/auth/demo-switch?role=admin")).json()
    headers = {"Authorization": f"Bearer {admin_auth['access_token']}"}
    encounter = {
        "resourceType": "Encounter", "id": "E-1", "class": {"code": "AMB"},
        "period": {"start": "2026-10-02T09:00:00Z"},
        "participant": [{"individual": {"identifier": {"value": "PRV-1001"}}}],
    }

    # No Patient: data must never be attached to a "default" patient.
    res = await client.post("/api/v1/fhir/import", json={"resourceType": "Bundle", "entry": [{"resource": encounter}]}, headers=headers)
    assert res.status_code == 422

    # New patient without a birth date: demographics are never invented.
    res = await client.post("/api/v1/fhir/import", json={"resourceType": "Bundle", "entry": [
        {"resource": {"resourceType": "Patient", "identifier": [{"system": "urn:test", "value": "NODOB-1"}], "gender": "male"}},
        {"resource": encounter},
    ]}, headers=headers)
    assert res.status_code == 422

    # Known MRN but conflicting date of birth: route to review instead of merging.
    res = await client.post("/api/v1/fhir/import", json={"resourceType": "Bundle", "entry": [
        {"resource": {"resourceType": "Patient", "identifier": [{"system": "MAMC", "value": "PT-100201"}],
                      "gender": "male", "birthDate": "1999-01-01"}},
        {"resource": encounter},
    ]}, headers=headers)
    assert res.status_code == 409

    # Encounter without a start time.
    res = await client.post("/api/v1/fhir/import", json={"resourceType": "Bundle", "entry": [
        {"resource": {"resourceType": "Patient", "identifier": [{"system": "MAMC", "value": "PT-100201"}]}},
        {"resource": {**encounter, "period": {}}},
    ]}, headers=headers)
    assert res.status_code == 422

@pytest.mark.asyncio
async def test_patient_clinical_onboarding_and_break_glass(client):
    admin_auth = (await client.post("/api/v1/auth/demo-switch?role=admin")).json()
    headers = {"Authorization": f"Bearer {admin_auth['access_token']}"}

    # 1. Onboard patient
    pt_res = await client.post("/api/v1/patients", json={
        "display_code": "PT-EMERGENCY-01",
        "date_of_birth": "1992-09-15",
        "sex": "M",
        "identifier_system": "MAMC",
    }, headers=headers)
    assert pt_res.status_code == 200
    pt_id = pt_res.json()["id"]

    # 2. Emergency break-glass override
    bg_res = await client.post(f"/api/v1/patients/{pt_id}/break-glass", json={
        "justification": "Patient unconscious in ER with acute coronary syndrome; urgent history required."
    }, headers=headers)
    assert bg_res.status_code == 200
    bg_data = bg_res.json()
    assert bg_data["status"] == "GRANTED"
    assert bg_data["emergency_window_minutes"] == 240

@pytest.mark.asyncio
async def test_clinical_document_amendment_lifecycle(client):
    admin_auth = (await client.post("/api/v1/auth/demo-switch?role=admin")).json()
    headers = {"Authorization": f"Bearer {admin_auth['access_token']}"}

    # 1. Create clinical document
    doc_res = await client.post("/api/v1/documents", json={
        "patient_id": "PT-100201",
        "document_type": "Progress Note",
        "title": "Initial Cardiology Assessment",
        "content": "Patient presents with chest tightness after exertion."
    }, headers=headers)
    assert doc_res.status_code == 200
    doc_id = doc_res.json()["id"]

    # 2. Append signed clinical addendum / amendment
    amend_res = await client.post(f"/api/v1/documents/{doc_id}/amend", json={
        "amendment_text": "Follow-up Troponin I levels returned normal (0.01 ng/mL). Stress echo scheduled.",
        "reason": "Lab follow-up results arrived post-encounter",
        "author_signature": "Dr. Sarah Chen, MD (Cardiology)"
    }, headers=headers)
    assert amend_res.status_code == 200
    amend_data = amend_res.json()
    assert amend_data["status"] == "AMENDED"
    assert amend_data["new_version"] == 2
    assert amend_data["previous_version_preserved"] is True
    # The recorded author is the authenticated user, not the client-supplied signature text.
    assert "admin@medchain.local" in amend_data["author"]

    # 3. Verify detail reflects amended narrative and incremented version
    detail_res = await client.get(f"/api/v1/documents/{doc_id}", headers=headers)
    assert detail_res.status_code == 200
    detail = detail_res.json()
    assert detail["version"] == 2
    assert "AMENDMENT v2" in detail["content"]

    # 4. The amended version verifies against its new commitment.
    verify = (await client.get(f"/api/v1/integrity/verify/{doc_id}", headers=headers)).json()
    assert verify["is_valid"] is True
    assert verify["record_version"] == 2

    # 5. Tampered content cannot be amended (no building on unverified data).
    tamper = await client.post(f"/api/v1/integrity/tamper-demo/{doc_id}", headers=headers)
    assert tamper.status_code == 200
    blocked = await client.post(f"/api/v1/documents/{doc_id}/amend", json={
        "amendment_text": "Attempt after tampering", "reason": "should be refused",
    }, headers=headers)
    assert blocked.status_code == 409


@pytest.mark.asyncio
async def test_break_glass_grant_is_honored_and_reviewable(client):
    admin_auth = (await client.post("/api/v1/auth/demo-switch?role=admin")).json()
    admin_headers = {"Authorization": f"Bearer {admin_auth['access_token']}"}
    doctor_auth = (await client.post("/api/v1/auth/demo-switch?role=doctor")).json()
    doctor_headers = {"Authorization": f"Bearer {doctor_auth['access_token']}"}

    # A patient with no relationship to the demo doctor.
    pt_id = (await client.post("/api/v1/patients", json={
        "display_code": "PT-ER-UNASSIGNED", "date_of_birth": "1980-02-02", "sex": "F", "identifier_system": "MAMC",
    }, headers=admin_headers)).json()["id"]

    denied = await client.get(f"/api/v1/patients/{pt_id}", headers=doctor_headers)
    assert denied.status_code == 403

    grant = await client.post(f"/api/v1/patients/{pt_id}/break-glass", json={
        "justification": "Unresponsive patient in resuscitation bay; medication history needed now.",
    }, headers=doctor_headers)
    assert grant.status_code == 200
    grant_id = grant.json()["grant_id"]

    # The grant is actually honored by the access check.
    allowed = await client.get(f"/api/v1/patients/{pt_id}", headers=doctor_headers)
    assert allowed.status_code == 200

    # Compliance review: flagging it as inappropriate ends the emergency window.
    queue = (await client.get("/api/v1/admin/break-glass", headers=admin_headers)).json()
    assert any(item["id"] == grant_id for item in queue)
    review = await client.post(f"/api/v1/admin/break-glass/{grant_id}/review",
                               json={"outcome": "INAPPROPRIATE", "note": "No ED encounter on record."},
                               headers=admin_headers)
    assert review.status_code == 200
    assert (await client.get(f"/api/v1/patients/{pt_id}", headers=doctor_headers)).status_code == 403


@pytest.mark.asyncio
async def test_only_admins_register_patients_and_primary_doctor_sees_them(client):
    doctor_auth = (await client.post("/api/v1/auth/demo-switch?role=doctor")).json()
    doctor_headers = {"Authorization": f"Bearer {doctor_auth['access_token']}"}
    admin_auth = (await client.post("/api/v1/auth/demo-switch?role=admin")).json()
    admin_headers = {"Authorization": f"Bearer {admin_auth['access_token']}"}
    payload = {"display_code": "PT-REG-0001", "date_of_birth": "1991-05-05", "sex": "M",
               "given_name": "Ravi", "family_name": "Kumar"}

    assert (await client.post("/api/v1/patients", json=payload, headers=doctor_headers)).status_code == 403
    # Registration needs the issuing hospital (its facility code is the MRN authority).
    assert (await client.post("/api/v1/patients", json=payload, headers=admin_headers)).status_code == 422

    hospitals = (await client.get("/api/v1/admin/hospitals", headers=admin_headers)).json()
    doctors = (await client.get("/api/v1/doctors", headers=admin_headers)).json()
    created = await client.post("/api/v1/patients", headers=admin_headers, json={
        **payload, "hospital_id": hospitals[0]["id"], "primary_doctor_id": doctors[0]["id"]})
    assert created.status_code == 200, created.text
    patient_id = created.json()["id"]
    assert created.json()["display_name"] == "KUMAR, Ravi"

    # The new patient is immediately in the primary doctor's list and chart.
    assert any(p["id"] == patient_id for p in (await client.get("/api/v1/patients", headers=doctor_headers)).json())
    timeline = (await client.get(f"/api/v1/patients/{patient_id}/timeline", headers=doctor_headers)).json()
    assert timeline["care_team"][0]["relationship_type"] == "PRIMARY_CARE"
    # Server-side search by MRN fragment and by family name.
    assert any(p["id"] == patient_id for p in (await client.get("/api/v1/patients?q=REG-00", headers=admin_headers)).json())
    assert any(p["id"] == patient_id for p in (await client.get("/api/v1/patients?q=kumar", headers=admin_headers)).json())
    # Duplicate MRNs are refused.
    duplicate = await client.post("/api/v1/patients", headers=admin_headers, json={**payload, "hospital_id": hospitals[0]["id"]})
    assert duplicate.status_code == 409

