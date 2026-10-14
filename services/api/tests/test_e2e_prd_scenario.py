import pytest
from fastapi.testclient import TestClient
from src.main import app

client = TestClient(app)

def test_prd_section_16_full_narrative():
    # ---------------------------------------------------------
    # Step 1: System Baseline & Multi-Store Health Check
    # ---------------------------------------------------------
    health_res = client.get("/api/v1/health")
    assert health_res.status_code == 200
    health_data = health_res.json()
    assert health_data["status"] in ["healthy", "degraded"]
    assert "relational_database" in health_data["services"]
    assert "document_store" in health_data["services"]
    assert "graph_intelligence" in health_data["services"]
    assert "blockchain_evidence" in health_data["services"]

    # ---------------------------------------------------------
    # Step 2: Researcher Onboarding & Project Registration
    # ---------------------------------------------------------
    login_res = client.post("/api/v1/auth/login", json={
        "email": "researcher@medchain.local",
        "password": "Password123!"
    })
    assert login_res.status_code == 200
    researcher_token = login_res.json()["access_token"]
    researcher_headers = {"Authorization": f"Bearer {researcher_token}"}

    # Register research project
    proj_res = client.post("/api/v1/research-projects", json={
        "title": "Cardio-Metabolic Cross-Disorder Longitudinal Study",
        "purpose": "Longitudinal metabolic syndrome progression and drug interactions under IRB protocol."
    }, headers=researcher_headers)
    assert proj_res.status_code == 200
    project = proj_res.json()
    project_id = project["id"]

    # ---------------------------------------------------------
    # Step 3: Access Request Submission
    # ---------------------------------------------------------
    # Target patient: PT-100201
    req_res = client.post("/api/v1/access-requests", json={
        "patient_id": "PT-100201",
        "project_id": project_id,
        "purpose": "Required for statistical cohort analysis under IRB protocol.",
        "requested_scopes": ["aggregate_diagnoses"]
    }, headers=researcher_headers)
    assert req_res.status_code == 200
    access_req = req_res.json()
    request_id = access_req["id"]
    assert access_req["status"] == "PENDING"

    # ---------------------------------------------------------
    # Step 4: Centralized Policy Evaluation (Deny-by-Default)
    # ---------------------------------------------------------
    # Researcher queries before patient consent is granted -> DENIED 403
    query_denied = client.post("/api/v1/research/query", json={
        "project_id": project_id,
        "query_type": "disease_distribution",
        "filters": {"patient_id": "PT-100201"}
    }, headers=researcher_headers)
    assert query_denied.status_code == 403
    error_detail = query_denied.json()["detail"]
    assert "CONSENT_REVOKED_OR_MISSING" in str(error_detail)

    # ---------------------------------------------------------
    # Step 5: Patient Consent Management & Policy Re-Evaluation (Grant)
    # ---------------------------------------------------------
    # Log in as Patient PT-100201
    patient_login = client.post("/api/v1/auth/login", json={
        "email": "patient@medchain.local",
        "password": "Password123!"
    })
    assert patient_login.status_code == 200
    patient_token = patient_login.json()["access_token"]
    patient_headers = {"Authorization": f"Bearer {patient_token}"}

    # Grant consent for this request
    grant_res = client.post(f"/api/v1/access-requests/{request_id}/decision", json={
        "decision": "APPROVED",
        "valid_days": 365
    }, headers=patient_headers)
    assert grant_res.status_code == 200
    assert grant_res.json()["status"] == "APPROVED"

    # Researcher queries again -> NOW AUTHORIZED (200)
    query_allowed = client.post("/api/v1/research/query", json={
        "project_id": project_id,
        "query_type": "disease_distribution",
        "filters": {"patient_id": "PT-100201"}
    }, headers=researcher_headers)
    assert query_allowed.status_code == 200
    allowed_data = query_allowed.json()
    assert allowed_data["status"] == "AUTHORIZED"
    assert "results" in allowed_data

    # ---------------------------------------------------------
    # Step 6: Research Cohort Execution & Exploration
    # ---------------------------------------------------------
    cohort_res = client.post("/api/v1/cohorts/run", json={
        "name": "E2E Cardio Cohort",
        "k": 3
    }, headers=researcher_headers)
    assert cohort_res.status_code == 200
    cohort_data = cohort_res.json()
    assert len(cohort_data["clusters"]) == 3
    assert cohort_data["inertia"] is not None

    # ---------------------------------------------------------
    # Step 7: Real-Time Patient Consent Revocation & Immediate Enforcement
    # ---------------------------------------------------------
    # Retrieve active consent id
    consents_res = client.get("/api/v1/consents", headers=patient_headers)
    assert consents_res.status_code == 200
    active_consents = [c for c in consents_res.json() if c["status"] == "GRANTED" and c["project_id"] == project_id]
    assert len(active_consents) > 0
    consent_id = active_consents[0]["id"]

    # Revoke consent
    revoke_res = client.post(f"/api/v1/consents/{consent_id}/revoke", headers=patient_headers)
    assert revoke_res.status_code == 200
    assert revoke_res.json()["status"] == "REVOKED"

    # Researcher queries again -> IMMEDIATELY FORBIDDEN (403)
    query_revoked = client.post("/api/v1/research/query", json={
        "project_id": project_id,
        "query_type": "disease_distribution",
        "filters": {"patient_id": "PT-100201"}
    }, headers=researcher_headers)
    assert query_revoked.status_code == 403

    # ---------------------------------------------------------
    # Step 8: Cross-Database Data Consistency & Graph Rebuild
    # ---------------------------------------------------------
    admin_login = client.post("/api/v1/auth/login", json={
        "email": "admin@medchain.local",
        "password": "Password123!"
    })
    admin_headers = {"Authorization": f"Bearer {admin_login.json()['access_token']}"}

    sync_res = client.post("/api/v1/admin/graph/rebuild", headers=admin_headers)
    assert sync_res.status_code == 200
    assert "details" in sync_res.json()

    # ---------------------------------------------------------
    # Step 9: Clinical Document Tamper Detection & Cryptographic Integrity Verification
    # ---------------------------------------------------------
    docs_res = client.get("/api/v1/documents", headers=admin_headers)
    assert docs_res.status_code == 200
    docs = docs_res.json()
    assert len(docs) > 0
    target_doc = docs[0]
    doc_id = target_doc["id"]

    # Verify untampered
    verify_res1 = client.get(f"/api/v1/integrity/verify/{doc_id}", headers=admin_headers)
    assert verify_res1.status_code == 200
    assert verify_res1.json()["is_valid"] is True
    assert verify_res1.json()["verification_status"] == "VERIFIED_MATCH"

    # Intentionally tamper document content
    tamper_res = client.post(f"/api/v1/integrity/tamper-demo/{doc_id}", headers=admin_headers)
    assert tamper_res.status_code == 200

    # Verify again -> TAMPER DETECTED
    verify_res2 = client.get(f"/api/v1/integrity/verify/{doc_id}", headers=admin_headers)
    assert verify_res2.status_code == 200
    assert verify_res2.json()["is_valid"] is False
    assert verify_res2.json()["verification_status"] == "TAMPER_DETECTED"

    # ---------------------------------------------------------
    # Step 10: Insurance Claim Submission, Atomic Rollback, & Anomaly Detection
    # ---------------------------------------------------------
    # Submitting claim with invalid quantity <= 0 triggers atomic rollback
    pol_res = client.get("/api/v1/insurance/policies", headers=admin_headers)
    assert pol_res.status_code == 200
    test_policy_id = pol_res.json()[0]["id"]
    claims_list_res = client.get("/api/v1/insurance/claims", headers=admin_headers)
    assert claims_list_res.status_code == 200
    test_visit_id = claims_list_res.json()[0]["visit_id"]

    rollback_res = client.post("/api/v1/insurance/claims", json={
        "policy_id": test_policy_id,
        "visit_id": test_visit_id,
        "items": [
            {"item_code": "99213", "description": "Consultation", "quantity": -2, "unit_cost": 100.0}
        ]
    }, headers=admin_headers)
    assert rollback_res.status_code == 400
    assert "item quantity must be positive" in rollback_res.json()["detail"]

    # Check anomaly flags for existing claims
    anomaly_res = client.get("/api/v1/insurance/anomalies", headers=admin_headers)
    assert anomaly_res.status_code == 200
    anomalies = anomaly_res.json()
    assert len(anomalies) > 0
    flag_id = anomalies[0]["id"]

    # Resolve anomaly
    adj_res = client.post(f"/api/v1/insurance/anomalies/{flag_id}/resolve", json={
        "resolution_status": "CONFIRMED_FRAUD",
        "notes": "E2E automated test: duplicate claim detected within 48h."
    }, headers=admin_headers)
    assert adj_res.status_code == 200
    assert adj_res.json()["resolution_status"] == "CONFIRMED_FRAUD"

    # ---------------------------------------------------------
    # Step 11: Graph Analytics & Treatment Exploration
    # ---------------------------------------------------------
    graph_res = client.get("/api/v1/graph/treatments?condition_code=I10", headers=admin_headers)
    assert graph_res.status_code == 200
    treatments = graph_res.json()
    assert len(treatments) > 0
    assert "drug_code" in treatments[0]
    assert "confidence_score" in treatments[0]

    # ---------------------------------------------------------
    # Step 12: Audit Trail Verification & On-Chain Proof Inspection
    # ---------------------------------------------------------
    audit_res = client.get("/api/v1/audit/logs?limit=50", headers=admin_headers)
    assert audit_res.status_code == 200
    logs = audit_res.json()
    assert len(logs) > 0
    action_types = {log["action"] for log in logs}
    assert any("CONSENT" in act or "TAMPER" in act or "RESEARCH" in act for act in action_types)
