import pytest

@pytest.mark.asyncio
async def test_cohort_clustering_pipeline(client):
    researcher_auth = (await client.post("/api/v1/auth/demo-switch?role=researcher")).json()
    headers = {"Authorization": f"Bearer {researcher_auth['access_token']}"}

    # Run clustering with k=3
    run_res = await client.post("/api/v1/cohorts/run", json={
        "name": "Metabolic Cohort 2026",
        "k": 3,
        "features": ["diagnoses", "medications", "lab_abnormalities"],
        "random_state": 42
    }, headers=headers)
    assert run_res.status_code == 200
    cohort = run_res.json()
    assert cohort["name"] == "Metabolic Cohort 2026"
    assert len(cohort["clusters"]) in (2, 3)
    assert cohort["inertia"] is not None
    assert "Exploratory synthetic pattern only" in cohort["disclaimer"]

    # List cohorts
    list_res = await client.get("/api/v1/cohorts", headers=headers)
    assert list_res.status_code == 200
    assert len(list_res.json()) >= 1

@pytest.mark.asyncio
async def test_graph_endpoints(client):
    admin_auth = (await client.post("/api/v1/auth/demo-switch?role=admin")).json()
    headers = {"Authorization": f"Bearer {admin_auth['access_token']}"}

    # Overview
    overview_res = await client.get("/api/v1/graph/overview", headers=headers)
    assert overview_res.status_code == 200
    ov = overview_res.json()
    assert len(ov["nodes"]) > 0
    assert len(ov["edges"]) > 0

    # Disease Co-occurrence
    cooccur_res = await client.get("/api/v1/graph/disease-cooccurrence", headers=headers)
    assert cooccur_res.status_code == 200
    co = cooccur_res.json()
    assert all(e["type"] == "CO_OCCURS_WITH" for e in co["edges"])

    # Drug Side Effects
    side_effects_res = await client.get("/api/v1/graph/drug-side-effects", headers=headers)
    assert side_effects_res.status_code == 200
    se = side_effects_res.json()
    assert "causation" in se["disclaimer"].lower()

    # Multi-hop Path-Finding Query (Blueprint 4.1)
    path_res = await client.get("/api/v1/graph/path-query?disease_code=E11", headers=headers)
    assert path_res.status_code == 200
    path_data = path_res.json()
    assert path_data["disease_code"] == "E11"
    assert "results" in path_data
    assert "disclaimer" in path_data

@pytest.mark.asyncio
async def test_generate_patient_cohorts_function():
    import pandas as pd
    from src.services.cohort_ml import generate_patient_cohorts

    sample_df = pd.DataFrame([
        {"age": 55, "visit_frequency": 4, "hba1c_level": 7.8, "sys_bp": 140, "claim_cost": 2500.0},
        {"age": 30, "visit_frequency": 1, "hba1c_level": 5.2, "sys_bp": 115, "claim_cost": 400.0},
        {"age": 68, "visit_frequency": 6, "hba1c_level": 8.4, "sys_bp": 150, "claim_cost": 4200.0},
        {"age": 25, "visit_frequency": 1, "hba1c_level": 5.0, "sys_bp": 110, "claim_cost": 300.0},
    ])
    result_df, centers = generate_patient_cohorts(sample_df, n_clusters=2)
    assert "cohort_id" in result_df.columns
    assert len(centers) == 2

