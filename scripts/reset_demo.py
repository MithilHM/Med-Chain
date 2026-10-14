import sys
import os
import asyncio

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../services/api"))

from src.database import reset_db
from src.services.mongo import MongoDocumentService
from scripts.seed_demo import seed

async def reset():
    print("[Reset] Dropping relational schema and clearing stores...")
    await reset_db()
    await MongoDocumentService.clear_all()
    print("[Reset] Repopulating deterministic seed data...")
    await seed()
    print("[Reset] Reset complete.")

if __name__ == "__main__":
    asyncio.run(reset())
