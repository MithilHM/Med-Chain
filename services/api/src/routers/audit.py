from typing import List, Optional
from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from src.database import get_db
from src.models import AppUser, AccessEvent, Doctor, Visit
from src.schemas.consent import AccessEventOut
from src.routers.deps import doctor_accessible_patient_ids, get_current_user, require_role, verify_patient_access

router = APIRouter(prefix="/audit", tags=["Audit Trail"])

@router.get("/events", response_model=List[AccessEventOut])
@router.get("/logs", response_model=List[AccessEventOut])
async def list_audit_events(
    patient_id: Optional[str] = None,
    current_user: AppUser = Depends(require_role(["admin", "patient", "doctor"])),
    db: AsyncSession = Depends(get_db)
):
    query = select(AccessEvent)
    if current_user.role == "patient":
        from src.models import Patient
        pt = (await db.execute(select(Patient).where(Patient.user_id == current_user.id))).scalar_one_or_none()
        if not pt:
            return []
        query = query.where(AccessEvent.patient_id == pt.id)
    elif current_user.role == "doctor":
        doctor = (await db.execute(select(Doctor).where(Doctor.user_id == current_user.id))).scalar_one_or_none()
        if not doctor:
            return []
        assigned_patient_ids = await doctor_accessible_patient_ids(db, doctor, current_user)
        if not assigned_patient_ids:
            return []
        query = query.where(AccessEvent.patient_id.in_(assigned_patient_ids))
        if patient_id:
            await verify_patient_access(patient_id, current_user, db)
            query = query.where(AccessEvent.patient_id == patient_id)
    elif patient_id:
        query = query.where(AccessEvent.patient_id == patient_id)

    events = (await db.execute(query.order_by(AccessEvent.occurred_at.desc()).limit(100))).scalars().all()
    actor_ids = {e.actor_user_id for e in events}
    actors = {
        user.id: user
        for user in (await db.execute(select(AppUser).where(AppUser.id.in_(actor_ids)))).scalars().all()
    } if actor_ids else {}
    out = []
    for e in events:
        actor = actors.get(e.actor_user_id)
        out.append(AccessEventOut(
            id=e.id,
            actor_user_id=e.actor_user_id,
            actor_email=actor.email if actor else None,
            patient_id=e.patient_id,
            resource_type=e.resource_type,
            resource_reference=e.resource_reference,
            action=e.action,
            decision=e.decision,
            reason_code=e.reason_code,
            occurred_at=e.occurred_at,
            chain_tx_hash=e.chain_tx_hash
        ))
    return out
