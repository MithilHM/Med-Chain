import time
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from src.database import get_db, check_connection
from src.models import AppUser
from src.services.mongo import MongoDocumentService
from src.services.neo4j_sync import GraphSyncService
from src.services.blockchain import BlockchainService
from src.routers.deps import get_current_user, require_role

router = APIRouter(prefix="/admin", tags=["System Health & Administration"])

@router.get("/health")
async def get_system_health(db: AsyncSession = Depends(get_db)):
    t0 = time.time()
    db_up = False
    latency_ms = 0.0
    try:
        await db.execute(text("SELECT 1"))
        db_up = True
        latency_ms = round((time.time() - t0) * 1000, 2)
    except Exception:
        db_up = False

    mongo_health = await MongoDocumentService.is_healthy()
    graph_health = GraphSyncService.get_status()
    chain_health = BlockchainService.get_status()

    return {
        "status": "healthy" if db_up else "degraded",
        "timestamp": time.time(),
        "services": {
            "relational_database": {
                "status": "up" if db_up else "down",
                "latency_ms": latency_ms,
                "engine": "PostgreSQL / SQLite Fallback"
            },
            "document_store": mongo_health,
            "graph_intelligence": graph_health,
            "blockchain_evidence": chain_health
        }
    }

@router.post("/graph/rebuild")
@router.post("/sync/graph")
async def trigger_graph_rebuild(
    current_user: AppUser = Depends(require_role(["admin"])),
    db: AsyncSession = Depends(get_db)
):
    result = await GraphSyncService.rebuild_graph(db)
    return {
        "status": "synced",
        "message": "Graph projection rebuilt successfully from authoritative relational records.",
        "details": result
    }

@router.post("/demo/reset")
async def trigger_demo_reset(
    current_user: AppUser = Depends(require_role(["admin"]))
):
    import sys
    import os
    import asyncio
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../../"))
    from scripts.reset_demo import reset
    await reset()
    return {"message": "All data stores reset and reseeded with deterministic demo records."}
