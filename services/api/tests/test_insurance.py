import pytest
from decimal import Decimal

@pytest.mark.asyncio
async def test_claim_transaction_rollback_and_anomaly_queue(client):
    analyst_auth = (await client.post("/api/v1/auth/demo-switch?role=insurance_analyst")).json()
    headers = {"Authorization": f"Bearer {analyst_auth['access_token']}"}

    # 1. Fetch existing policy and visit
    policies_res = await client.get("/api/v1/insurance/policies", headers=headers)
    assert policies_res.status_code == 200
    policies = policies_res.json()
    assert len(policies) > 0
    policy_id = policies[0]["id"]

    claims_res = await client.get("/api/v1/insurance/claims", headers=headers)
    assert claims_res.status_code == 200
    claims = claims_res.json()
    assert len(claims) > 0
    visit_id = claims[0]["visit_id"]

    # 2. Test transactional atomic rollback on invalid item (negative quantity)
    invalid_claim_payload = {
        "policy_id": policy_id,
        "visit_id": visit_id,
        "items": [
            {
                "item_code": "CPT-99213",
                "description": "Standard clinic encounter",
                "quantity": -2, # Invalid!
                "unit_cost": "150.00"
            }
        ]
    }
    fail_res = await client.post("/api/v1/insurance/claims", json=invalid_claim_payload, headers=headers)
    assert fail_res.status_code == 400
    assert "rolled back" in fail_res.json()["detail"].lower()

    # 3. Test anomaly review queue contains flagged claims
    flagged_res = await client.get("/api/v1/insurance/claims?flagged_only=true", headers=headers)
    assert flagged_res.status_code == 200
    flagged_claims = flagged_res.json()
    if not flagged_claims:
        # Submit a high-cost claim to trigger explainable anomaly flag
        high_claim = await client.post("/api/v1/insurance/claims", json={
            "policy_id": policy_id,
            "visit_id": visit_id,
            "items": [
                {"item_code": "SURG-HIGH", "description": "High tier complex procedure", "quantity": 5, "unit_cost": "25000.00"}
            ]
        }, headers=headers)
        assert high_claim.status_code == 200
        flagged_res = await client.get("/api/v1/insurance/claims?flagged_only=true", headers=headers)
        flagged_claims = flagged_res.json()

    assert len(flagged_claims) > 0
    anomaly_claim = flagged_claims[0]
    assert anomaly_claim["review_flag"] is True

    # 4. Underwriter reviews and resolves claim
    review_res = await client.post(f"/api/v1/insurance/claims/{anomaly_claim['id']}/review", json={
        "decision": "APPROVED",
        "approved_amount": "600.00",
        "reason": "Verified secondary physician attendance. One duplicate charge denied, primary approved."
    }, headers=headers)
    assert review_res.status_code == 200
    reviewed_claim = review_res.json()
    assert reviewed_claim["status"] == "APPROVED"
    assert reviewed_claim["review_flag"] is False
