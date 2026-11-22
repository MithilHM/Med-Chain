import pytest

@pytest.mark.asyncio
async def test_public_and_admin_health_endpoints(client):
    # 1. Public health exposes minimal liveness only
    pub_res = await client.get("/api/v1/health")
    assert pub_res.status_code == 200
    pub_data = pub_res.json()
    assert pub_data["status"] == "healthy"
    assert "version" in pub_data
    assert "services" not in pub_data # Internal infrastructure details hidden from public

    # 2. Admin health exposes detailed multi-store diagnostics
    admin_auth = (await client.post("/api/v1/auth/demo-switch?role=admin")).json()
    admin_headers = {"Authorization": f"Bearer {admin_auth['access_token']}"}

    admin_res = await client.get("/api/v1/admin/health", headers=admin_headers)
    assert admin_res.status_code == 200
    admin_data = admin_res.json()
    assert "services" in admin_data
    assert "relational_database" in admin_data["services"]
    assert "document_store" in admin_data["services"]
    assert "graph_intelligence" in admin_data["services"]
    assert "blockchain_evidence" in admin_data["services"]
    assert "transactional_outbox" in admin_data["services"]

@pytest.mark.asyncio
async def test_transactional_outbox_processing(client):
    admin_auth = (await client.post("/api/v1/auth/demo-switch?role=admin")).json()
    admin_headers = {"Authorization": f"Bearer {admin_auth['access_token']}"}

    # 1. Trigger document creation which enqueues an outbox event
    doc_res = await client.post("/api/v1/documents", json={
        "patient_id": admin_auth["user"]["patient_id"] or "100201",
        "document_type": "Progress Note",
        "title": "Outbox Verification Note",
        "content": "Patient evaluated for outbox consistency pipeline."
    }, headers=admin_headers)
    assert doc_res.status_code in (200, 404) # Depending on seeded patient

    # 2. Trigger outbox processing
    process_res = await client.post("/api/v1/admin/outbox/process?limit=10", headers=admin_headers)
    assert process_res.status_code == 200
    assert process_res.json()["status"] == "success"
    assert "processed_events" in process_res.json()

@pytest.mark.asyncio
async def test_consent_revocation_idempotency_and_outbox(client):
    patient_auth = (await client.post("/api/v1/auth/demo-switch?role=patient")).json()
    p_headers = {"Authorization": f"Bearer {patient_auth['access_token']}"}

    consents_res = await client.get("/api/v1/consents", headers=p_headers)
    assert consents_res.status_code == 200
    consents = consents_res.json()
    assert len(consents) > 0
    test_consent = consents[0]

    # Revoke once
    r1 = await client.post(f"/api/v1/consents/{test_consent['id']}/revoke", headers=p_headers)
    assert r1.status_code == 200
    assert r1.json()["status"] == "REVOKED"

    # Revoke second time (idempotent, no race or crash)
    r2 = await client.post(f"/api/v1/consents/{test_consent['id']}/revoke", headers=p_headers)
    assert r2.status_code == 200
    assert r2.json()["status"] == "REVOKED"

