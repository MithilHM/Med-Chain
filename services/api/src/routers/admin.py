import time
import sys
from pathlib import Path
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from src import database
from src.database import get_db
from src.models import AppUser
from src.services.mongo import MongoDocumentService
from src.services.neo4j_sync import GraphSyncService
from src.services.blockchain import BlockchainService
from src.routers.deps import get_current_user, record_access_event, require_role
from src.config import settings

router = APIRouter(prefix="/admin", tags=["System Health & Administration"])

_SHOWCASE_QUERIES = {
    "disease-prevalence": {
        "title": "Disease prevalence (joins and HAVING)",
        "description": "Counts distinct patients across diagnosis and visit tables. Groups smaller than five are suppressed.",
        "sql": """SELECT d.code AS disease_code, d.name AS disease_name,
       COUNT(DISTINCT v.patient_id) AS patient_count
FROM disease d
JOIN diagnosis diag ON diag.disease_id = d.id
JOIN visit v ON v.id = diag.visit_id
GROUP BY d.code, d.name
HAVING COUNT(DISTINCT v.patient_id) >= :minimum_group_size
ORDER BY patient_count DESC, d.code
LIMIT 50""",
    },
    "high-cost-disease-cohort": {
        "title": "High-cost disease cohorts (CTE and subquery)",
        "description": "Builds a high-claim cohort in a CTE, then returns disease aggregates with small groups suppressed.",
        "sql": """WITH high_claim_patients AS (
    SELECT pol.patient_id, SUM(clm.claimed_amount) AS total_claimed
    FROM insurance_claim clm
    JOIN insurance_policy pol ON pol.id = clm.policy_id
    GROUP BY pol.patient_id
    HAVING SUM(clm.claimed_amount) > 300
), patient_diseases AS (
    SELECT DISTINCT high_claim_patients.patient_id, disease.code, disease.name,
           high_claim_patients.total_claimed
    FROM high_claim_patients
    JOIN visit ON visit.patient_id = high_claim_patients.patient_id
    JOIN diagnosis ON diagnosis.visit_id = visit.id
    JOIN disease ON disease.id = diagnosis.disease_id
)
SELECT code AS disease_code, name AS disease_name,
       COUNT(patient_id) AS patient_count,
       ROUND(AVG(total_claimed), 2) AS average_patient_claimed
FROM patient_diseases
GROUP BY code, name
HAVING COUNT(patient_id) >= :minimum_group_size
ORDER BY patient_count DESC, code
LIMIT 50""",
    },
    "monthly-claims-window": {
        "title": "Monthly claims (CTE and window function)",
        "description": "Aggregates claims by month and calculates the running total without exposing patient identifiers.",
        "sql": """WITH monthly_claims AS (
    SELECT {month_expression} AS claim_month,
           SUM(clm.claimed_amount) AS monthly_claimed,
           COUNT(DISTINCT pol.patient_id) AS patient_count
    FROM insurance_claim clm
    JOIN insurance_policy pol ON pol.id = clm.policy_id
    GROUP BY {month_expression}
    HAVING COUNT(DISTINCT pol.patient_id) >= :minimum_group_size
)
SELECT claim_month, patient_count, monthly_claimed,
       SUM(monthly_claimed) OVER (
           ORDER BY claim_month
           ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
       ) AS cumulative_claimed
FROM monthly_claims
ORDER BY claim_month""",
    },
}


def _showcase_sql(query_id: str, dialect: str) -> str:
    query = _SHOWCASE_QUERIES[query_id]["sql"]
    if query_id == "monthly-claims-window":
        month_expression = (
            "strftime('%Y-%m', submitted_at)"
            if dialect == "sqlite"
            else "to_char(submitted_at, 'YYYY-MM')"
        )
        return query.format(month_expression=month_expression)
    return query

@router.get("/health")
async def get_system_health(
    current_user: AppUser = Depends(require_role(["admin"])),
    db: AsyncSession = Depends(get_db),
):
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

    database_mode = "sqlite_fallback" if database.is_fallback_active else "postgresql"
    service_health = {
        "relational_database": db_up and not database.is_fallback_active,
        "document_store": mongo_health.get("status") == "up" and mongo_health.get("mode") == "mongodb_live_encrypted",
        "graph_intelligence": graph_health.get("status") == "SYNCHRONIZED" and graph_health.get("mode") == "live_neo4j",
        "blockchain_evidence": chain_health.get("status") == "connected",
    }
    degraded_services = [name for name, healthy in service_health.items() if not healthy]

    return {
        "status": "healthy" if not degraded_services else "degraded",
        "degraded_services": degraded_services,
        "timestamp": time.time(),
        "services": {
            "relational_database": {
                "status": "up" if db_up else "down",
                "latency_ms": latency_ms,
                "engine": database_mode
            },
            "document_store": mongo_health,
            "graph_intelligence": graph_health,
            "blockchain_evidence": chain_health
        }
    }


@router.get("/dbms/showcase")
async def list_dbms_showcase_queries(
    current_user: AppUser = Depends(require_role(["admin"])),
):
    return [
        {"id": query_id, "title": query["title"], "description": query["description"]}
        for query_id, query in _SHOWCASE_QUERIES.items()
    ] + [{
        "id": "patient-index-plan",
        "title": "Patient lookup index plan",
        "description": "Shows the query plan for a fixed indexed display-code lookup; no patient record is returned.",
    }]


@router.get("/dbms/showcase/{query_id}")
async def execute_dbms_showcase_query(
    query_id: str,
    current_user: AppUser = Depends(require_role(["admin"])),
    db: AsyncSession = Depends(get_db),
):
    if query_id not in {*_SHOWCASE_QUERIES, "patient-index-plan"}:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Showcase query not found.")

    dialect = db.get_bind().dialect.name
    if query_id == "patient-index-plan":
        sql = (
            "EXPLAIN QUERY PLAN SELECT id FROM patient WHERE display_code = 'PT-100201'"
            if dialect == "sqlite"
            else "EXPLAIN SELECT id FROM patient WHERE display_code = 'PT-100201'"
        )
        result = await db.execute(text(sql))
    else:
        sql = _showcase_sql(query_id, dialect)
        result = await db.execute(text(sql), {"minimum_group_size": 5})

    columns = list(result.keys())
    rows = [dict(row) for row in result.mappings().all()]
    await record_access_event(
        db,
        current_user.id,
        None,
        "DBMS_SHOWCASE_QUERY",
        query_id,
        "EXECUTE_READ_ONLY_AGGREGATE",
    )
    return {
        "id": query_id,
        "title": "Patient lookup index plan" if query_id == "patient-index-plan" else _SHOWCASE_QUERIES[query_id]["title"],
        "sql": sql,
        "columns": columns,
        "rows": rows,
        "row_count": len(rows),
        "dialect": dialect,
        "disclaimer": "Synthetic data demonstration. Aggregate query results suppress groups smaller than five patients.",
    }
@router.post("/graph/rebuild")
@router.post("/sync/graph")
async def trigger_graph_rebuild(
    current_user: AppUser = Depends(require_role(["admin"])),
    db: AsyncSession = Depends(get_db)
):
    result = await GraphSyncService.rebuild_graph(db)
    if result["status"] != "SYNCHRONIZED":
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "message": "The relational graph snapshot was rebuilt, but the live Neo4j projection did not synchronize.",
                "details": result,
            },
        )
    return {
        "status": "synced",
        "message": f"Graph projection rebuilt from authoritative relational records in {result['mode']} mode.",
        "details": result
    }

@router.post("/demo/reset")
async def trigger_demo_reset(
    current_user: AppUser = Depends(require_role(["admin"]))
):
    if (
        not settings.DEMO_MODE
        or settings.ENVIRONMENT.strip().lower() not in {"development", "dev", "test", "testing"}
    ):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found.")

    import asyncio
    project_root = next(
        (
            parent
            for parent in Path(__file__).resolve().parents
            if (parent / "scripts" / "reset_demo.py").is_file()
        ),
        None,
    )
    if project_root is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Demo reset scripts are not available in this deployment.",
        )
    sys.path.insert(0, str(project_root))
    from scripts.reset_demo import reset
    await reset()
    return {"message": "All data stores reset and reseeded with deterministic demo records."}
