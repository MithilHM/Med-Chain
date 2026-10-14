import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from src.config import settings
from src.database import check_connection, init_db

# Configure structured logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("medchain.api")

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting MedChain API Application Gateway...")
    await check_connection()
    yield
    logger.info("Shutting down MedChain API Application Gateway...")

app = FastAPI(
    title="MedChain Healthcare Intelligence API",
    version="1.0.0",
    description="Privacy-Preserving Healthcare Intelligence, Multi-Model Database & Blockchain Audit Gateway",
    lifespan=lifespan
)

# CORS Configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
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

app.include_router(auth_router, prefix="/api/v1")
app.include_router(patients_router, prefix="/api/v1")
app.include_router(clinical_router, prefix="/api/v1")
app.include_router(documents_router, prefix="/api/v1")
app.include_router(insurance_router, prefix="/api/v1")
app.include_router(consent_router, prefix="/api/v1")
app.include_router(research_router, prefix="/api/v1")
app.include_router(integrity_router, prefix="/api/v1")
app.include_router(graph_router, prefix="/api/v1")
app.include_router(cohorts_router, prefix="/api/v1")
app.include_router(audit_router, prefix="/api/v1")
app.include_router(blockchain_router, prefix="/api/v1")
app.include_router(admin_router, prefix="/api/v1")

@app.get("/")
def root():
    return {
        "service": "MedChain API",
        "version": "1.0.0",
        "docs_url": "/docs",
        "api_v1_base": "/api/v1",
        "status": "operational"
    }

from src.routers.admin import get_system_health
app.add_api_route("/api/v1/health", get_system_health, methods=["GET"], tags=["System Health & Administration"])
