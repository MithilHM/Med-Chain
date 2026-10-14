import pytest

@pytest.mark.asyncio
async def test_record_integrity_verification_and_tamper_detection(client):
    # 1. Doctor logs in and creates a document
    doc_auth = (await client.post("/api/v1/auth/demo-switch?role=doctor")).json()
    headers = {"Authorization": f"Bearer {doc_auth['access_token']}"}

    patients_res = await client.get("/api/v1/patients", headers=headers)
    patient_id = patients_res.json()[0]["id"]

    create_res = await client.post("/api/v1/documents", json={
        "patient_id": patient_id,
        "document_type": "clinical_note",
        "title": "Automated Test Clinical Progress",
        "content": "Patient vitals stable. Normal sinus rhythm observed on telemetry."
    }, headers=headers)
    assert create_res.status_code == 200
    doc_id = create_res.json()["id"]

    # 2. Verify untouched document -> passes
    verify1 = await client.get(f"/api/v1/integrity/verify/{doc_id}", headers=headers)
    assert verify1.status_code == 200
    res1 = verify1.json()
    assert res1["is_valid"] is True
    assert res1["verification_status"] == "VERIFIED_MATCH"

    # 3. Simulate unauthorized tamper in document store
    tamper_res = await client.post(f"/api/v1/integrity/tamper-demo/{doc_id}", headers=headers)
    assert tamper_res.status_code == 200

    # 4. Re-verify -> fails with tamper detection
    verify2 = await client.get(f"/api/v1/integrity/verify/{doc_id}", headers=headers)
    assert verify2.status_code == 200
    res2 = verify2.json()
    assert res2["is_valid"] is False
    assert res2["verification_status"] == "TAMPER_DETECTED"
