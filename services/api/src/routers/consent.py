from typing import List, Optional
from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from src.database import get_db
from src.models import (
    AppUser, ResearchProject, AccessRequest, Consent, Patient, ResearchOrganization
)
from src.schemas.consent import (
    AccessRequestCreate, AccessRequestDecision, AccessRequestOut, ConsentOut
)
from src.services.blockchain import BlockchainService
from src.routers.deps import get_current_user, require_role

router = APIRouter(prefix="", tags=["Research Projects & Patient Consent"])

@router.get("/research-projects")
async def list_research_projects(db: AsyncSession = Depends(get_db)):
    projects = (await db.execute(select(ResearchProject).order_by(ResearchProject.created_at.desc()))).scalars().all()
    out = []
    for p in projects:
        org = (await db.execute(select(ResearchOrganization).where(ResearchOrganization.id == p.organization_id))).scalar_one_or_none()
        out.append({
            "id": p.id,
            "title": p.title,
            "purpose": p.purpose,
            "status": p.status,
            "organization_name": org.name if org else "Academic Institute",
            "created_at": p.created_at
        })
    return out

@router.post("/research-projects")
async def create_research_project(
    data: dict,
    current_user: AppUser = Depends(require_role(["researcher", "admin"])),
    db: AsyncSession = Depends(get_db)
):
    org = (await db.execute(select(ResearchOrganization))).scalars().first()
    org_id = org.id if org else None
    if not org_id:
        new_org = ResearchOrganization(name="Biomedical Intelligence Collaborative", organization_type="Research Consortium")
        db.add(new_org)
        await db.flush()
        org_id = new_org.id

    project = ResearchProject(
        organization_id=org_id,
        title=data.get("title", "Clinical Research Initiative"),
        purpose=data.get("purpose", "Investigating synthetic cohort outcomes"),
        status="ACTIVE",
        created_by=current_user.id
    )
    db.add(project)
    await db.commit()
    await db.refresh(project)
    return project

@router.get("/access-requests", response_model=List[AccessRequestOut])
async def list_access_requests(
    current_user: AppUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    query = select(AccessRequest)
    if current_user.role == "patient":
        pt = (await db.execute(select(Patient).where(Patient.user_id == current_user.id))).scalar_one_or_none()
        if not pt:
            return []
        query = query.where(AccessRequest.patient_id == pt.id)
    
    requests = (await db.execute(query.order_by(AccessRequest.requested_at.desc()))).scalars().all()
    out = []
    for r in requests:
        pt = (await db.execute(select(Patient).where(Patient.id == r.patient_id))).scalar_one_or_none()
        proj = (await db.execute(select(ResearchProject).where(ResearchProject.id == r.requester_project_id))).scalar_one_or_none()
        scopes = r.requested_scope_json if isinstance(r.requested_scope_json, list) else []
        out.append(AccessRequestOut(
            id=r.id,
            patient_id=r.patient_id,
            patient_display_code=pt.display_code if pt else None,
            project_id=r.requester_project_id,
            project_title=proj.title if proj else None,
            purpose=r.purpose,
            requested_scopes=scopes,
            status=r.status,
            requested_at=r.requested_at,
            decided_at=r.decided_at
        ))
    return out

@router.post("/access-requests", response_model=AccessRequestOut)
async def create_access_request(
    req_in: AccessRequestCreate,
    current_user: AppUser = Depends(require_role(["researcher", "admin"])),
    db: AsyncSession = Depends(get_db)
):
    from sqlalchemy import or_
    patient = (await db.execute(select(Patient).where(or_(Patient.id == req_in.patient_id, Patient.display_code == req_in.patient_id)))).scalar_one_or_none()
    if not patient:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Patient not found.")

    project = (await db.execute(select(ResearchProject).where(ResearchProject.id == req_in.project_id))).scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Research project not found.")

    req = AccessRequest(
        patient_id=patient.id,
        requester_project_id=req_in.project_id,
        requested_scope_json=req_in.requested_scopes,
        purpose=req_in.purpose,
        status="PENDING"
    )
    db.add(req)
    await db.commit()
    await db.refresh(req)

    return AccessRequestOut(
        id=req.id,
        patient_id=req.patient_id,
        patient_display_code=patient.display_code,
        project_id=req.requester_project_id,
        project_title=project.title,
        purpose=req.purpose,
        requested_scopes=req_in.requested_scopes,
        status=req.status,
        requested_at=req.requested_at,
        decided_at=req.decided_at
    )

@router.post("/access-requests/{request_id}/decision")
async def decide_access_request(
    request_id: str,
    decision_in: AccessRequestDecision,
    current_user: AppUser = Depends(require_role(["patient", "admin"])),
    db: AsyncSession = Depends(get_db)
):
    req = (await db.execute(select(AccessRequest).where(AccessRequest.id == request_id))).scalar_one_or_none()
    if not req:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Access request not found.")

    # Check ownership if role is patient
    if current_user.role == "patient":
        pt = (await db.execute(select(Patient).where(Patient.user_id == current_user.id))).scalar_one_or_none()
        if not pt or pt.id != req.patient_id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Cannot decide another patient's consent request.")

    now = datetime.now(timezone.utc)
    req.status = decision_in.decision
    req.decided_at = now

    created_consent = None
    if decision_in.decision == "APPROVED":
        # Create Consent record
        valid_days = decision_in.valid_days or 30
        valid_until = now + timedelta(days=valid_days)
        scopes = decision_in.approved_scopes or req.requested_scope_json

        consent = Consent(
            patient_id=req.patient_id,
            requester_project_id=req.requester_project_id,
            purpose=req.purpose,
            scope_json=scopes,
            access_mode="DE_IDENTIFIED",
            valid_from=now,
            valid_until=valid_until,
            status="GRANTED",
            granted_at=now
        )
        db.add(consent)
        await db.flush()

        # Emit on-chain event (or unanchored mode)
        chain_status, tx_hash, block_num = await BlockchainService.record_consent_granted(
            consent.id, consent.patient_id, consent.requester_project_id, int(valid_until.timestamp())
        )
        consent.chain_tx_hash = tx_hash
        created_consent = consent

    await db.commit()
    return {
        "status": req.status,
        "request_id": req.id,
        "consent_id": created_consent.id if created_consent else None,
        "chain_tx_hash": created_consent.chain_tx_hash if created_consent else None
    }

@router.get("/consents", response_model=List[ConsentOut])
async def list_consents(
    current_user: AppUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    query = select(Consent)
    if current_user.role == "patient":
        pt = (await db.execute(select(Patient).where(Patient.user_id == current_user.id))).scalar_one_or_none()
        if not pt:
            return []
        query = query.where(Consent.patient_id == pt.id)
    
    consents = (await db.execute(query.order_by(Consent.granted_at.desc()))).scalars().all()
    out = []
    for c in consents:
        pt = (await db.execute(select(Patient).where(Patient.id == c.patient_id))).scalar_one_or_none()
        proj = (await db.execute(select(ResearchProject).where(ResearchProject.id == c.requester_project_id))).scalar_one_or_none()
        out.append(ConsentOut(
            id=c.id,
            patient_id=c.patient_id,
            patient_display_code=pt.display_code if pt else None,
            project_id=c.requester_project_id,
            project_title=proj.title if proj else None,
            purpose=c.purpose,
            scope_json=c.scope_json if isinstance(c.scope_json, dict) else {"scopes": c.scope_json},
            access_mode=c.access_mode,
            valid_from=c.valid_from,
            valid_until=c.valid_until,
            status=c.status,
            granted_at=c.granted_at,
            revoked_at=c.revoked_at,
            chain_tx_hash=c.chain_tx_hash
        ))
    return out

@router.post("/consents/{consent_id}/revoke")
async def revoke_consent(
    consent_id: str,
    current_user: AppUser = Depends(require_role(["patient", "admin"])),
    db: AsyncSession = Depends(get_db)
):
    consent = (await db.execute(select(Consent).where(Consent.id == consent_id))).scalar_one_or_none()
    if not consent:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Consent record not found.")

    if current_user.role == "patient":
        pt = (await db.execute(select(Patient).where(Patient.user_id == current_user.id))).scalar_one_or_none()
        if not pt or pt.id != consent.patient_id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Cannot revoke another patient's consent.")

    now = datetime.now(timezone.utc)
    consent.status = "REVOKED"
    consent.revoked_at = now

    # Emit on-chain revocation event
    chain_status, tx_hash, block_num = await BlockchainService.record_consent_revoked(
        consent.id, consent.patient_id
    )
    if chain_status == "CONFIRMED":
        consent.chain_tx_hash = tx_hash

    await db.commit()
    return {
        "status": "REVOKED",
        "consent_id": consent.id,
        "revoked_at": consent.revoked_at,
        "chain_tx_hash": tx_hash
    }
