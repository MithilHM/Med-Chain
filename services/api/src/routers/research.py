from typing import List, Optional, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import bindparam, case, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession
from src.database import get_db
from src.models import (
    AppUser, Visit, Diagnosis, Disease, Prescription, Medication, LabResult, LabTest
)
from src.schemas.consent import ResearchQueryRequest
from src.services.consent_engine import ConsentPolicyEngine
from src.services.privacy import MIN_RESEARCH_GROUP_SIZE
from src.routers.deps import get_current_user, require_role

router = APIRouter(prefix="/research", tags=["Privacy-Preserving Research Engine"])

@router.post("/query")
async def execute_research_query(
    query_req: ResearchQueryRequest,
    current_user: AppUser = Depends(require_role(["researcher", "admin"])),
    db: AsyncSession = Depends(get_db)
):
    """
    Centralized consent-gated research query endpoint.
    Checks active patient consent, requested scopes, and revocation status.
    Returns aggregated metrics or de-identified cohort vectors. Zero direct identifiers.
    """
    scope_needed = "aggregate_diagnoses"
    if query_req.query_type == "medication_utilization":
        scope_needed = "medication_history"
    elif query_req.query_type == "lab_summary":
        scope_needed = "lab_summaries"
    elif query_req.query_type == "cohort_summary":
        scope_needed = "deidentified_cohort"
    elif query_req.query_type != "disease_distribution":
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Unsupported query type: {query_req.query_type}",
        )
    if query_req.disease_code and query_req.query_type != "disease_distribution":
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="disease_code can only be used with disease_distribution queries.",
        )

    is_allowed, reason, consents = await ConsentPolicyEngine.evaluate_research_access(
        db=db,
        actor=current_user,
        project_id=query_req.project_id,
        requested_scope=scope_needed,
        target_patient_id=query_req.filters.get("patient_id") if query_req.filters else None
    )

    if not is_allowed:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "message": f"Research query rejected by Consent Policy Engine: {reason}",
                "error_code": "CONSENT_REVOKED_OR_MISSING",
                "project_id": query_req.project_id
            }
        )

    authorized_patient_ids = sorted({consent.patient_id for consent in consents})
    if len(authorized_patient_ids) < MIN_RESEARCH_GROUP_SIZE:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "message": f"Research output requires at least {MIN_RESEARCH_GROUP_SIZE} consented patients.",
                "error_code": "MINIMUM_GROUP_SIZE_NOT_MET",
                "minimum_group_size": MIN_RESEARCH_GROUP_SIZE,
            },
        )

    # Authorized: Execute aggregate analytics query
    if query_req.query_type == "disease_distribution":
        q = text("""
            SELECT 
                d.code,
                d.name,
                COUNT(diag.id) as diagnosis_count,
                COUNT(DISTINCT v.patient_id) as patient_count
            FROM disease d
            JOIN diagnosis diag ON diag.disease_id = d.id
            JOIN visit v ON v.id = diag.visit_id
            WHERE v.patient_id IN :patient_ids
              AND (:disease_code IS NULL OR d.code = :disease_code)
            GROUP BY d.code, d.name
            ORDER BY diagnosis_count DESC;
        """).bindparams(
            bindparam("patient_ids", expanding=True),
            bindparam("disease_code"),
        )
        res = await db.execute(q, {
            "patient_ids": authorized_patient_ids,
            "disease_code": query_req.disease_code,
        })
        data = [dict(row) for row in res.mappings() if row["patient_count"] >= MIN_RESEARCH_GROUP_SIZE]
        if query_req.disease_code:
            patient_count = max((row["patient_count"] for row in data), default=0)
        else:
            patient_count = len(authorized_patient_ids)
        return {
            "query_type": query_req.query_type,
            "status": "AUTHORIZED",
            "results": data,
            "patient_count_aggregated": patient_count,
            "disclaimer": f"De-identified aggregate analysis only. Direct identifiers are stripped; result cells below {MIN_RESEARCH_GROUP_SIZE} patients are suppressed."
        }

    elif query_req.query_type == "medication_utilization":
        q = text("""
            SELECT 
                m.code,
                m.name,
                m.drug_class,
                COUNT(pr.id) as prescription_count,
                COUNT(DISTINCT v.patient_id) as patient_count
            FROM medication m
            JOIN prescription pr ON pr.medication_id = m.id
            JOIN visit v ON v.id = pr.visit_id
            WHERE v.patient_id IN :patient_ids
            GROUP BY m.code, m.name, m.drug_class
            ORDER BY prescription_count DESC;
        """).bindparams(bindparam("patient_ids", expanding=True))
        res = await db.execute(q, {"patient_ids": authorized_patient_ids})
        data = [dict(row) for row in res.mappings() if row["patient_count"] >= MIN_RESEARCH_GROUP_SIZE]
        return {
            "query_type": query_req.query_type,
            "status": "AUTHORIZED",
            "results": data,
            "disclaimer": f"De-identified aggregate analysis only. Direct identifiers are stripped; result cells below {MIN_RESEARCH_GROUP_SIZE} patients are suppressed."
        }

    elif query_req.query_type == "lab_summary":
        lab_summary = (
            select(
                LabTest.code.label("test_code"),
                LabTest.name.label("test_name"),
                LabTest.unit.label("unit"),
                func.count(LabResult.id).label("result_count"),
                func.count(func.distinct(Visit.patient_id)).label("patient_count"),
                func.sum(case((LabResult.is_abnormal.is_(True), 1), else_=0)).label("abnormal_result_count"),
                func.avg(LabResult.result_value).label("average_result"),
            )
            .join(Visit, Visit.id == LabResult.visit_id)
            .join(LabTest, LabTest.id == LabResult.lab_test_id)
            .where(Visit.patient_id.in_(authorized_patient_ids))
            .group_by(LabTest.code, LabTest.name, LabTest.unit)
            .order_by(LabTest.name.asc())
        )
        rows = (await db.execute(lab_summary)).mappings().all()
        return {
            "query_type": query_req.query_type,
            "status": "AUTHORIZED",
            "results": [
                {
                    **dict(row),
                    "abnormal_result_count": (
                        row["abnormal_result_count"]
                        if row["abnormal_result_count"] >= MIN_RESEARCH_GROUP_SIZE
                        else None
                    ),
                }
                for row in rows
                if row["patient_count"] >= MIN_RESEARCH_GROUP_SIZE
            ],
            "patient_count_aggregated": len(authorized_patient_ids),
            "disclaimer": f"Synthetic laboratory values are grouped for exploratory research; result cells below {MIN_RESEARCH_GROUP_SIZE} patients are suppressed. This is not clinical guidance.",
        }

    # Default cohort summary
    pt_count = len(authorized_patient_ids)
    diagnosis_summary = (await db.execute(
        select(
            func.count(Diagnosis.id).label("diagnosis_count"),
            func.count(func.distinct(Visit.patient_id)).label("patient_count"),
        )
        .join(Visit, Diagnosis.visit_id == Visit.id)
        .where(Visit.patient_id.in_(authorized_patient_ids))
    )).one()
    medication_summary = (await db.execute(
        select(
            func.count(Prescription.id).label("prescription_count"),
            func.count(func.distinct(Visit.patient_id)).label("patient_count"),
        )
        .join(Visit, Prescription.visit_id == Visit.id)
        .where(Visit.patient_id.in_(authorized_patient_ids))
    )).one()

    return {
        "query_type": query_req.query_type,
        "status": "AUTHORIZED",
        "cohort_overview": {
            "total_consented_records": pt_count,
            "total_diagnoses_observed": (
                diagnosis_summary.diagnosis_count
                if diagnosis_summary.patient_count >= MIN_RESEARCH_GROUP_SIZE
                else None
            ),
            "total_prescriptions_recorded": (
                medication_summary.prescription_count
                if medication_summary.patient_count >= MIN_RESEARCH_GROUP_SIZE
                else None
            ),
        },
        "disclaimer": f"De-identified aggregate analysis only. Direct identifiers are stripped; counts below {MIN_RESEARCH_GROUP_SIZE} are suppressed."
    }
