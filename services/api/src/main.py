import logging
import re
import uuid
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text
from src import database
from src.config import settings
from src.database import check_connection, init_db
from src.request_context import request_id_var
from src.services.crypto import constant_time_hash_equals
from src.services.events import EventRelay
from src.services.mongo import DocumentStoreUnavailable
from src.services.monitoring import Monitor, collect_metrics, render_prometheus
from src.services.outbox import OutboxWorker

# Configure structured logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("medchain.api")

_REQUEST_ID_PATTERN = re.compile(r"^[A-Za-z0-9._-]{8,100}$")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting MedChain healthcare data prototype...")
    if settings.is_development:
        await init_db()
    else:
        if not await check_connection():
            raise RuntimeError("Configured PostgreSQL is unavailable.")
        try:
            async with database.async_engine.connect() as connection:
                await connection.execute(text("SELECT version_num FROM alembic_version LIMIT 1"))
        except Exception as exc:
            raise RuntimeError("Database migrations are missing; run `alembic upgrade head` before startup.") from exc
    OutboxWorker.start()
    if EventRelay.start(database.async_engine):
        logger.info("Real-time events fan out through PostgreSQL LISTEN/NOTIFY.")
    Monitor.start()
    yield
    await Monitor.stop()
    await EventRelay.stop()
    await OutboxWorker.stop()
    logger.info("Shutting down MedChain healthcare data prototype...")

app = FastAPI(
    title="MedChain Healthcare Data API",
    version="1.1.0",
    description="Prototype API for consent-managed healthcare records, real-time clinical integration, analytics, and audit events.",
    docs_url="/docs" if settings.is_development else None,
    redoc_url="/redoc" if settings.is_development else None,
    openapi_url="/openapi.json" if settings.is_development else None,
    lifespan=lifespan
)


@app.middleware("http")
async def request_context_and_security_headers(request: Request, call_next):
    incoming = request.headers.get("x-request-id", "")
    request_id = incoming if _REQUEST_ID_PATTERN.match(incoming) else uuid.uuid4().hex
    token = request_id_var.set(request_id)
    try:
        response = await call_next(request)
    finally:
        request_id_var.reset(token)
    response.headers["X-Request-ID"] = request_id
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers.setdefault("Cache-Control", "no-store")  # API responses may contain PHI
    if not settings.is_development:
        response.headers["Strict-Transport-Security"] = "max-age=63072000; includeSubDomains"
    return response


@app.exception_handler(DocumentStoreUnavailable)
async def document_store_unavailable_handler(request: Request, exc: DocumentStoreUnavailable):
    logger.error("Document store unavailable while handling %s %s", request.method, request.url.path)
    return JSONResponse(
        status_code=503,
        content={"detail": "The clinical document store is temporarily unavailable. Retry shortly."},
        headers={"Retry-After": "30"},
    )


# CORS Configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Accept", "Authorization", "Content-Type", "X-Request-ID"],
    expose_headers=["X-Request-ID"],
)

# Import and include routers under /api/v1
from src.routers.auth import router as auth_router
from src.routers.patients import router as patients_router
from src.routers.clinical import router as clinical_router
from src.routers.documents import router as documents_router
from src.routers.insurance import router as insurance_router
from src.routers.consent import router as consent_router
from src.routers.research import router as research_router
from src.routers.integrity import router as integrity_router
from src.routers.graph import router as graph_router
from src.routers.cohorts import router as cohorts_router
from src.routers.audit import router as audit_router
from src.routers.blockchain import router as blockchain_router
from src.routers.admin import router as admin_router
from src.routers.fhir import router as fhir_router
from src.routers.integration import router as integration_router
from src.routers.events import router as events_router
from src.routers.scim import router as scim_router
from src.routers.users import router as users_router

for router in (
    auth_router, patients_router, clinical_router, documents_router, insurance_router, consent_router,
    research_router, integrity_router, graph_router, cohorts_router, audit_router, blockchain_router,
    admin_router, fhir_router, integration_router, events_router, scim_router, users_router,
):
    app.include_router(router, prefix="/api/v1")


@app.get("/metrics", include_in_schema=False)
async def prometheus_metrics(request: Request):
    """Prometheus scrape endpoint: `Authorization: Bearer <token>` matching METRICS_BEARER_TOKEN_HASH,
    or an admin session. Metrics are operational counts only and contain no patient data."""
    from fastapi import HTTPException
    from fastapi.responses import PlainTextResponse
    from src.routers.deps import get_current_user, security

    header = request.headers.get("authorization", "")
    token = header[7:] if header.lower().startswith("bearer ") else ""
    async with database.AsyncSessionLocal() as db:
        if not (token and constant_time_hash_equals(token, settings.METRICS_BEARER_TOKEN_HASH)):
            try:
                user = await get_current_user(request, await security(request), db)
            except HTTPException:
                return JSONResponse(status_code=401, content={"detail": "Metrics require a scrape token or admin session."})
            if user.role != "admin":
                return JSONResponse(status_code=403, content={"detail": "Admin only."})
        metrics = await collect_metrics(db)
    return PlainTextResponse(render_prometheus(metrics), media_type="text/plain; version=0.0.4")

@app.get("/")
def root():
    return {
        "service": "MedChain API",
        "version": "1.1.0",
        "docs_url": "/docs" if settings.is_development else None,
        "api_v1_base": "/api/v1",
        "status": "operational"
    }

@app.get("/api/v1/health", tags=["Health"])
def liveness_check():
    """Minimal public liveness probe; detailed dependency status is admin-only."""
    return {"status": "healthy", "service": "MedChain API", "version": "1.1.0"}
