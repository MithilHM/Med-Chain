import logging
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from src.database import get_db
from src.models import AppUser, Cohort, CohortMembership, AnalyticsRun, ResearchProject
from src.schemas.analytics import CohortRunRequest, CohortOut
from src.services.cohort_ml import CohortMLService
from src.services.consent_engine import ConsentPolicyEngine
from src.services.privacy import MIN_RESEARCH_GROUP_SIZE
from src.routers.deps import require_role

router = APIRouter(prefix="/cohorts", tags=["Patient Cohort Analytics"])
logger = logging.getLogger("medchain.cohorts")

@router.get("", response_model=List[CohortOut])
async def list_cohorts(
    current_user: AppUser = Depends(require_role(["researcher", "admin"])),
    db: AsyncSession = Depends(get_db),
    project_id: Optional[str] = Query(default=None),
):
    cohort_query = select(Cohort).order_by(Cohort.created_at.desc())
    if current_user.role == "researcher":
        cohort_query = cohort_query.where(Cohort.created_by == current_user.id)
    cohorts = (await db.execute(cohort_query)).scalars().all()
    runs = (await db.execute(
        select(AnalyticsRun)
        .where(AnalyticsRun.run_type == "COHORT_KMEANS")
        .order_by(AnalyticsRun.started_at.desc())
    )).scalars().all()

    out = []
    for c in cohorts:
        project_ref = (c.feature_definition_json or {}).get("project_id")
        if not project_ref or (project_id and project_ref != project_id):
            continue

        allowed, _, consents = await ConsentPolicyEngine.evaluate_research_access(
            db=db,
            actor=current_user,
            project_id=project_ref,
            requested_scope="deidentified_cohort",
        )
        if not allowed:
            continue

        authorized_patient_ids = {consent.patient_id for consent in consents}
        memberships = (await db.execute(
            select(CohortMembership).where(CohortMembership.cohort_id == c.id)
        )).scalars().all()
        member_ids = {membership.patient_id for membership in memberships}
        # A cached result that contains a now-revoked patient's data is not returned.
        if (
            len(member_ids) < MIN_RESEARCH_GROUP_SIZE
            or not member_ids.issubset(authorized_patient_ids)
        ):
            continue

        run = next(
            (candidate for candidate in runs if (candidate.parameters_json or {}).get("cohort_id") == c.id),
            None,
        )

        clusters = []
        inertia = None
        if run and run.summary_json:
            clusters = run.summary_json.get("clusters", [])
            inertia = run.summary_json.get("inertia")
            if any(cluster.get("patient_count", 0) < MIN_RESEARCH_GROUP_SIZE for cluster in clusters):
                continue

        out.append(CohortOut(
            id=c.id,
            name=c.name,
            description=c.description,
            algorithm=c.algorithm,
            created_at=c.created_at,
            clusters=clusters,
            inertia=inertia,
            features=(c.feature_definition_json or {}).get("features", []),
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
        project_id = run_req.project_id
        consents = []
        if project_id:
            allowed, reason, consents = await ConsentPolicyEngine.evaluate_research_access(
                db=db,
                actor=current_user,
                project_id=project_id,
                requested_scope="deidentified_cohort",
            )
            if not allowed:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=f"Cohort analysis rejected by Consent Policy Engine: {reason}",
                )
        else:
            project_query = select(ResearchProject).where(ResearchProject.status == "ACTIVE")
            if current_user.role == "researcher":
                project_query = project_query.where(ResearchProject.created_by == current_user.id)
            projects = (await db.execute(project_query)).scalars().all()
            authorized_projects = []
            for project in projects:
                allowed, _, project_consents = await ConsentPolicyEngine.evaluate_research_access(
                    db=db,
                    actor=current_user,
                    project_id=project.id,
                    requested_scope="deidentified_cohort",
                )
                if allowed:
                    authorized_projects.append((project.id, project_consents))
            if not authorized_projects:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="No active research project consent covers cohort analysis.",
                )
            if len(authorized_projects) > 1:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail="project_id is required when more than one project has active consent.",
                )
            project_id, consents = authorized_projects[0]

        patient_ids = sorted({consent.patient_id for consent in consents})
        if len(patient_ids) < MIN_RESEARCH_GROUP_SIZE:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Cohort analysis requires at least {MIN_RESEARCH_GROUP_SIZE} consented patients.",
            )
        result = await CohortMLService.run_clustering(
            db=db,
            cohort_name=run_req.name or "Cardio-Metabolic Risk Phenotype Cohort",
            k=run_req.cluster_k,
            creator_user_id=current_user.id,
            project_id=project_id,
            patient_ids=patient_ids,
            features=run_req.features,
            random_state=run_req.random_state
        )
        return result
    except HTTPException:
        raise
    except Exception:
        logger.exception("Cohort clustering failed for user %s", current_user.id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Cohort clustering failed. Please retry or contact an administrator."
        )
