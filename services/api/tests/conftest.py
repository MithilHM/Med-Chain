import os
import sys
import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../../"))

from src.main import app
from scripts.reset_demo import reset

@pytest_asyncio.fixture(scope="session", autouse=True)
async def setup_test_db():
    await reset()

@pytest_asyncio.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
