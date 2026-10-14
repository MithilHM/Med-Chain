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
