import time
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession
from src import database
from src.database import get_db
from src.models import AppUser, EmergencyAccessGrant, InboundMessage, OperationalAlert, OutboxEvent
from src.services import key_rotation
from src.services.monitoring import run_evaluation
from src.services.mongo import MongoDocumentService
from src.services.neo4j_sync import GraphSyncService
from src.services.blockchain import BlockchainService
from src.routers.deps import get_current_user, record_access_event, require_role
from src.config import settings
from src.services.outbox import OutboxService, OutboxWorker

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
    graph_health = await GraphSyncService.get_status_async()
    chain_health = await BlockchainService.get_status_async()
    outbox_counts = {}
    oldest_pending = None
    review_backlog = 0
    if db_up:
        outbox_counts = dict((await db.execute(
            select(OutboxEvent.status, func.count(OutboxEvent.id)).group_by(OutboxEvent.status)
        )).all())
        oldest_pending = (await db.execute(
            select(func.min(OutboxEvent.created_at)).where(OutboxEvent.status.in_(["PENDING", "PROCESSING"]))
        )).scalar()
        review_backlog = (await db.execute(
            select(func.count(InboundMessage.id)).where(InboundMessage.status == "NEEDS_REVIEW")
        )).scalar() or 0

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
            "blockchain_evidence": chain_health,
            "transactional_outbox": {
                "status": "down" if not db_up else ("attention" if outbox_counts.get("FAILED") else "up"),
                "worker_running": OutboxWorker._task is not None and not OutboxWorker._task.done(),
                "counts": {name: outbox_counts.get(name, 0) for name in ("PENDING", "PROCESSING", "COMPLETED", "FAILED")},
                "oldest_undelivered_at": oldest_pending,
            },
            "clinical_integration": {
                "messages_needing_review": review_backlog,
            },
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



@router.get("/outbox/events")
async def list_outbox_events(
    event_status: Optional[str] = Query(default=None, alias="status"),
    limit: int = Query(default=50, ge=1, le=500),
    current_user: AppUser = Depends(require_role(["admin"])),
    db: AsyncSession = Depends(get_db),
):
    counts = dict((await db.execute(
        select(OutboxEvent.status, func.count(OutboxEvent.id)).group_by(OutboxEvent.status)
    )).all())
    query = select(OutboxEvent).order_by(OutboxEvent.created_at.desc()).limit(limit)
    if event_status:
        query = query.where(OutboxEvent.status == event_status.upper())
    events = (await db.execute(query)).scalars().all()
    summary = {name.lower(): counts.get(name, 0) for name in ("PENDING", "PROCESSING", "COMPLETED", "FAILED")}
    return {
        **summary,
        "total": sum(summary.values()),
        "events": [
            {
                "id": e.id,
                "event_type": e.event_type,
                "status": e.status,
                "attempt_count": e.attempt_count,
                "max_retries": e.max_retries,
                "next_attempt_at": e.next_attempt_at,
                "last_error": e.last_error,
                "created_at": e.created_at,
                "processed_at": e.processed_at,
            }
            for e in events
        ],
    }


@router.post("/outbox/process")
async def process_outbox_events(
    limit: int = Query(default=20, ge=1, le=500),
    current_user: AppUser = Depends(require_role(["admin"])),
):
    summary = await OutboxWorker.run_once(limit=limit)
    return {"status": "success", "processed_events": summary["completed"], "summary": summary}


@router.post("/outbox/retry-failed")
async def retry_failed_outbox_events(
    current_user: AppUser = Depends(require_role(["admin"])),
    db: AsyncSession = Depends(get_db),
):
    # Return terminal events to the queue after the underlying cause is fixed.
    result = await db.execute(
        text("UPDATE outbox_event SET status = 'PENDING', attempt_count = 0, next_attempt_at = NULL, locked_at = NULL "
             "WHERE status = 'FAILED'")
    )
    await db.commit()
    return {"status": "success", "reset_events": result.rowcount}


@router.get("/disaster-recovery")
async def get_disaster_recovery_posture(
    current_user: AppUser = Depends(require_role(["admin"])),
):
    """Report DR facts the application can observe. It does not claim backups exist."""
    return {
        "status": "NOT_VERIFIED",
        "observed": {
            "relational_engine": "sqlite_fallback" if database.is_fallback_active else "postgresql",
            "document_payload_encryption": "AES-256-GCM (application layer)",
            "volume_encryption": "unknown to the application",
            "backups": "unknown to the application",
            "last_restore_drill": None,
        },
        "recommended_targets": {"rpo": "<= 1 hour", "rto": "<= 4 hours"},
        "note": "Backups, point-in-time recovery, and restore drills are provisioned and evidenced by "
                "infrastructure. Record a dated, successful restore drill before any hospital pilot.",
    }


@router.get("/alerts")
async def list_alerts(
    include_resolved: bool = Query(default=False),
    current_user: AppUser = Depends(require_role(["admin"])),
    db: AsyncSession = Depends(get_db),
):
    query = select(OperationalAlert).order_by(OperationalAlert.last_seen_at.desc()).limit(200)
    if not include_resolved:
        query = query.where(OperationalAlert.status == "OPEN")
    return [
        {
            "id": a.id, "alert_key": a.alert_key, "severity": a.severity, "summary": a.summary, "status": a.status,
            "first_seen_at": a.first_seen_at, "last_seen_at": a.last_seen_at, "resolved_at": a.resolved_at,
            "notified_at": a.notified_at,
        }
        for a in (await db.execute(query)).scalars().all()
    ]


@router.post("/alerts/evaluate")
async def evaluate_alerts_now(current_user: AppUser = Depends(require_role(["admin"]))):
    return await run_evaluation()


@router.get("/encryption/status")
async def encryption_status(current_user: AppUser = Depends(require_role(["admin"]))):
    """Counts of encrypted values per key id (to confirm a rotation finished before retiring a key)."""
    return {
        "active_key_id": settings.DOCUMENT_ENCRYPTION_ACTIVE_KEY_ID,
        "configured_key_ids": sorted(settings.encryption_key_ring),
        "fields": await key_rotation.status(),
    }


class BreakGlassReview(BaseModel):
    outcome: str = Field(..., pattern="^(APPROPRIATE|INAPPROPRIATE)$")
    note: Optional[str] = Field(default=None, max_length=2000)


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


@router.get("/break-glass")
async def list_break_glass_grants(
    review_status: Optional[str] = Query(default="PENDING_REVIEW"),
    current_user: AppUser = Depends(require_role(["admin"])),
    db: AsyncSession = Depends(get_db),
):
    query = select(EmergencyAccessGrant).order_by(EmergencyAccessGrant.granted_at.desc()).limit(200)
    if review_status:
        query = query.where(EmergencyAccessGrant.review_status == review_status.upper())
    grants = (await db.execute(query)).scalars().all()
    now = datetime.now(timezone.utc)
    return [
        {
            "id": g.id,
            "user_id": g.user_id,
            "patient_id": g.patient_id,
            "justification": g.justification,
            "granted_at": g.granted_at,
            "expires_at": g.expires_at,
            "active": _aware(g.expires_at) > now and g.review_status != "INAPPROPRIATE",
            "review_status": g.review_status,
            "reviewed_by": g.reviewed_by,
            "reviewed_at": g.reviewed_at,
            "review_note": g.review_note,
        }
        for g in grants
    ]


@router.post("/break-glass/{grant_id}/review")
async def review_break_glass_grant(
    grant_id: str,
    review: BreakGlassReview,
    current_user: AppUser = Depends(require_role(["admin"])),
    db: AsyncSession = Depends(get_db),
):
    grant = await db.get(EmergencyAccessGrant, grant_id)
    if not grant:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Emergency access grant not found.")
    if grant.user_id == current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Reviewers cannot review their own emergency access.")
    now = datetime.now(timezone.utc)
    grant.review_status = review.outcome
    grant.review_note = review.note
    grant.reviewed_by = current_user.id
    grant.reviewed_at = now
    # An INAPPROPRIATE outcome revokes any remaining window immediately: the access check excludes
    # such grants. The original window is kept unchanged as part of the audit record.
    await record_access_event(
        db, current_user.id, grant.patient_id, "BREAK_GLASS_REVIEW", grant.id,
        "REVIEW_EMERGENCY_ACCESS", "GRANTED", f"REVIEWED_{review.outcome}",
    )
    return {"status": "REVIEWED", "grant_id": grant.id, "review_status": grant.review_status}


@router.get("/sessions")
async def list_active_sessions(
    current_user: AppUser = Depends(require_role(["admin"])),
    db: AsyncSession = Depends(get_db),
):
    from src.models.users import UserSession
    sessions = (await db.execute(
        select(UserSession).order_by(UserSession.created_at.desc()).limit(100)
    )).scalars().all()
    return [
        {
            "id": s.id,
            "user_id": s.user_id,
            "is_revoked": s.is_revoked,
            "expires_at": s.expires_at.isoformat() if s.expires_at else None,
            "created_at": s.created_at.isoformat() if s.created_at else None,
            "revoked_at": s.revoked_at.isoformat() if s.revoked_at else None,
        }
        for s in sessions
    ]


@router.post("/sessions/{session_id}/revoke")
async def revoke_session(
    session_id: str,
    current_user: AppUser = Depends(require_role(["admin"])),
    db: AsyncSession = Depends(get_db),
):
    from src.models.users import UserSession
    from src.models.base import get_utc_now
    session = (await db.execute(
        select(UserSession).where(UserSession.id == session_id)
    )).scalar_one_or_none()
    if not session:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found.")
    session.is_revoked = True
    session.revoked_at = get_utc_now()
    await db.commit()
    return {"status": "revoked", "session_id": session_id}
