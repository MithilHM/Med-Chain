import pytest

@pytest.mark.asyncio
async def test_consent_lifecycle_and_instant_revocation(client):
    # 1. Login as researcher and get projects
    researcher_auth = (await client.post("/api/v1/auth/demo-switch?role=researcher")).json()
    r_headers = {"Authorization": f"Bearer {researcher_auth['access_token']}"}

    projects_res = await client.get("/api/v1/research-projects", headers=r_headers)
    assert projects_res.status_code == 200
    projects = projects_res.json()
    assert len(projects) > 0
    project_id = projects[0]["id"]

    # 2. Researcher executes authorized query while consent is active
    query_res = await client.post("/api/v1/research/query", json={
        "project_id": project_id,
        "query_type": "disease_distribution"
    }, headers=r_headers)
    assert query_res.status_code == 200
    data = query_res.json()
    assert data["status"] == "AUTHORIZED"
    assert len(data["results"]) > 0

    # 3. Patient logs in and inspects active consents
    patient_auth = (await client.post("/api/v1/auth/demo-switch?role=patient")).json()
    p_headers = {"Authorization": f"Bearer {patient_auth['access_token']}"}

    consents_res = await client.get("/api/v1/consents", headers=p_headers)
    assert consents_res.status_code == 200
    consents = consents_res.json()
    assert len(consents) > 0
    active_consent = next(c for c in consents if c["status"] == "GRANTED")

    # 4. Patient revokes consent
    revoke_res = await client.post(f"/api/v1/consents/{active_consent['id']}/revoke", headers=p_headers)
    assert revoke_res.status_code == 200
    assert revoke_res.json()["status"] == "REVOKED"

    # 5. Researcher retries query targeting that revoked patient
    denied_res = await client.post("/api/v1/research/query", json={
        "project_id": project_id,
        "query_type": "disease_distribution",
        "filters": {"patient_id": active_consent["patient_id"]}
    }, headers=r_headers)

    assert denied_res.status_code == 403
    assert "CONSENT_REVOKED_OR_MISSING" in str(denied_res.json())
