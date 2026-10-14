from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from src.database import get_db
from src.models import AppUser, Cohort, CohortMembership, AnalyticsRun
from src.schemas.analytics import CohortRunRequest, CohortOut
from src.services.cohort_ml import CohortMLService
from src.routers.deps import get_current_user, require_role

router = APIRouter(prefix="/cohorts", tags=["Patient Cohort Analytics"])

@router.get("", response_model=List[CohortOut])
async def list_cohorts(
    current_user: AppUser = Depends(require_role(["researcher", "admin"])),
    db: AsyncSession = Depends(get_db)
):
    cohorts = (await db.execute(select(Cohort).order_by(Cohort.created_at.desc()))).scalars().all()
    out = []
    for c in cohorts:
        # Fetch analytics run if exists
        run = (await db.execute(
            select(AnalyticsRun).order_by(AnalyticsRun.started_at.desc())
        )).scalars().first()

        clusters = []
        inertia = None
        if run and run.summary_json:
            clusters = run.summary_json.get("clusters", [])
            inertia = run.summary_json.get("inertia")

        out.append(CohortOut(
            id=c.id,
            name=c.name,
            description=c.description,
            algorithm=c.algorithm,
            created_at=c.created_at,
            clusters=clusters,
            inertia=inertia,
            disclaimer="Exploratory synthetic pattern only. Not for clinical diagnosis or causal inference."
        ))
    return out

@router.post("/run", response_model=CohortOut)
async def run_cohort_clustering(
    run_req: CohortRunRequest,
    current_user: AppUser = Depends(require_role(["researcher", "admin"])),
    db: AsyncSession = Depends(get_db)
):
    try:
        result = await CohortMLService.run_clustering(
            db=db,
            cohort_name=run_req.name or "Cardio-Metabolic Risk Phenotype Cohort",
            k=run_req.cluster_k,
            creator_user_id=current_user.id,
            features=run_req.features or ["diagnoses", "medications", "lab_abnormalities"],
            random_state=run_req.random_state
        )
        return result
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Cohort clustering failed: {str(e)}"
        )
