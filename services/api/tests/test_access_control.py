import pytest

@pytest.mark.asyncio
async def test_insurance_analyst_cannot_access_clinical_documents(client):
    # Login as insurance analyst
    analyst_auth = (await client.post("/api/v1/auth/demo-switch?role=insurance_analyst")).json()
    headers = {"Authorization": f"Bearer {analyst_auth['access_token']}"}

    # Attempt to query clinical documents list
    res = await client.get("/api/v1/documents", headers=headers)
    assert res.status_code == 403

@pytest.mark.asyncio
async def test_researcher_cannot_access_clinical_documents(client):
    researcher_auth = (await client.post("/api/v1/auth/demo-switch?role=researcher")).json()
    headers = {"Authorization": f"Bearer {researcher_auth['access_token']}"}

    res = await client.get("/api/v1/documents", headers=headers)
    assert res.status_code == 403

@pytest.mark.asyncio
async def test_patient_cross_patient_timeline_denial(client):
    patient_auth = (await client.post("/api/v1/auth/demo-switch?role=patient")).json()
    headers = {"Authorization": f"Bearer {patient_auth['access_token']}"}

    # Attempt to access another patient's timeline using an arbitrary UUID
    fake_other_patient_id = "00000000-0000-0000-0000-000000000000"
    res = await client.get(f"/api/v1/patients/{fake_other_patient_id}/timeline", headers=headers)
    assert res.status_code == 403
    assert "Access denied" in res.json()["detail"]
