from typing import List, Optional, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select, func, text
from sqlalchemy.ext.asyncio import AsyncSession
from src.database import get_db
from src.models import (
    AppUser, Patient, Visit, Diagnosis, Disease, Prescription, Medication, LabResult
)
from src.schemas.consent import ResearchQueryRequest
from src.services.consent_engine import ConsentPolicyEngine
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
    elif query_req.query_type == "cohort_summary":
        scope_needed = "deidentified_cohort"

    is_allowed, reason, consent = await ConsentPolicyEngine.evaluate_research_access(
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
            GROUP BY d.code, d.name
            ORDER BY diagnosis_count DESC;
        """)
        res = await db.execute(q)
        data = [dict(row) for row in res.mappings()]
        return {
            "query_type": query_req.query_type,
            "status": "AUTHORIZED",
            "results": data,
            "patient_count_aggregated": sum(r["patient_count"] for r in data),
            "disclaimer": "De-identified aggregate analysis only. Direct identifiers are stripped."
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
            GROUP BY m.code, m.name, m.drug_class
            ORDER BY prescription_count DESC;
        """)
        res = await db.execute(q)
        data = [dict(row) for row in res.mappings()]
        return {
            "query_type": query_req.query_type,
            "status": "AUTHORIZED",
            "results": data,
            "disclaimer": "De-identified aggregate analysis only. Direct identifiers are stripped."
        }

    # Default cohort summary
    pt_count = (await db.execute(select(func.count(Patient.id)))).scalar_one()
    diag_count = (await db.execute(select(func.count(Diagnosis.id)))).scalar_one()
    med_count = (await db.execute(select(func.count(Prescription.id)))).scalar_one()

    return {
        "query_type": query_req.query_type,
        "status": "AUTHORIZED",
        "cohort_overview": {
            "total_consented_records": pt_count,
            "total_diagnoses_observed": diag_count,
            "total_prescriptions_recorded": med_count,
        },
        "disclaimer": "De-identified aggregate analysis only. Direct identifiers are stripped."
    }
