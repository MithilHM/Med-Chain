import pytest

@pytest.mark.asyncio
async def test_login_success_and_failure(client):
    # Valid login
    res = await client.post("/api/v1/auth/login", json={
        "email": "doctor@medchain.local",
        "password": "Password123!"
    })
    assert res.status_code == 200
    data = res.json()
    assert "access_token" in data
    assert data["user"]["role"] == "doctor"

    # Invalid password
    res_bad = await client.post("/api/v1/auth/login", json={
        "email": "doctor@medchain.local",
        "password": "WrongPassword!"
    })
    assert res_bad.status_code == 401

@pytest.mark.asyncio
async def test_demo_switch(client):
    res = await client.post("/api/v1/auth/demo-switch?role=patient")
    assert res.status_code == 200
    data = res.json()
    assert data["user"]["role"] == "patient"
    assert data["user"]["email"] == "patient@medchain.local"

@pytest.mark.asyncio
async def test_revocable_session_lifecycle(client):
    # 1. Login to obtain token and register active session
    res = await client.post("/api/v1/auth/login", json={
        "email": "doctor@medchain.local",
        "password": "Password123!"
    })
    assert res.status_code == 200
    token = res.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # 2. Access protected endpoint with active token
    me_res = await client.get("/api/v1/auth/me", headers=headers)
    assert me_res.status_code == 200
    assert me_res.json()["email"] == "doctor@medchain.local"

    # 3. List active sessions
    sessions_res = await client.get("/api/v1/auth/sessions", headers=headers)
    assert sessions_res.status_code == 200
    sessions = sessions_res.json()
    assert len(sessions) > 0
    assert not sessions[0]["is_revoked"]

    # 4. Revoke session via logout
    logout_res = await client.post("/api/v1/auth/logout", headers=headers)
    assert logout_res.status_code in (200, 204)

    # 5. Attempting to use the revoked token MUST be denied (401)
    denied_res = await client.get("/api/v1/auth/me", headers=headers)
    assert denied_res.status_code == 401
    assert "revoked" in denied_res.json()["detail"].lower()
