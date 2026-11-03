import sys
import asyncio
from pathlib import Path

project_root = Path(__file__).resolve().parent.parent
api_root = project_root / "services" / "api"
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(api_root if api_root.is_dir() else project_root))

from src.database import reset_db
from src.config import settings
from src.services.mongo import MongoDocumentService
from scripts.seed_demo import seed

async def reset():
    if (
        not settings.DEMO_MODE
        or settings.ENVIRONMENT.strip().lower() not in {"development", "dev", "test", "testing"}
    ):
        raise RuntimeError("Demo reset is disabled outside development, test, and demo mode.")

    print("[Reset] Dropping relational schema and clearing stores...")
    await reset_db()
    await MongoDocumentService.clear_all()
    print("[Reset] Repopulating deterministic seed data...")
    await seed()
    print("[Reset] Reset complete.")

if __name__ == "__main__":
    asyncio.run(reset())
