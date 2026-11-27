import os
import sys
import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../../"))
sys.path.insert(0, os.path.dirname(__file__))
# Every test client shares one address; the dedicated rate-limit test lowers this itself.
os.environ.setdefault("LOGIN_RATE_LIMIT_PER_MINUTE", "1000")
os.environ.setdefault("MONITOR_ENABLED", "false")
# The session fixture wipes and reseeds its stores, so keep them apart from the local dev app's data.
_TEST_DIR = os.path.dirname(os.path.abspath(__file__)).replace("\\", "/")
os.environ.setdefault("USE_SQLITE_FALLBACK", "true")
os.environ.setdefault("FALLBACK_SQLITE_URL", f"sqlite+aiosqlite:///{_TEST_DIR}/medchain_test.db")
os.environ.setdefault("FALLBACK_SQLITE_SYNC_URL", f"sqlite:///{_TEST_DIR}/medchain_test.db")
os.environ.setdefault("MONGO_DB_NAME", "medchain_docs_test")

from src.main import app
from src.services import mongo
from scripts.reset_demo import reset

mongo._fallback_storage_file = f"{_TEST_DIR}/mongo_documents_test_fallback.json"

@pytest_asyncio.fixture(scope="session", autouse=True)
async def setup_test_db():
    await reset()

@pytest_asyncio.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
