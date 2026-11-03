from collections import defaultdict
from itertools import combinations
from typing import Any, Dict, Optional, Set
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from src.database import get_db
from src.schemas.graph import GraphDataOut, GraphSyncStatusOut
from src.services.neo4j_sync import GraphSyncService
from src.services.consent_engine import ConsentPolicyEngine
from src.services.privacy import MIN_RESEARCH_GROUP_SIZE
from src.models import (
    AppUser,
    Diagnosis,
    Disease,
    Medication,
    ObservedAdverseEvent,
    Prescription,
    SideEffect,
    Visit,
    Doctor,
)
from src.routers.deps import get_current_user, require_role

router = APIRouter(prefix="/graph", tags=["Derived Graph Intelligence"])

async def _authorized_research_patient_ids(
    project_id: Optional[str],
    scopes: list[str],
    current_user: AppUser,
    db: AsyncSession,
) -> Optional[Set[str]]:
    if current_user.role == "admin":
        return None
    if current_user.role == "doctor":
        doctor = (await db.execute(select(Doctor).where(Doctor.user_id == current_user.id))).scalar_one_or_none()
        if not doctor:
            return set()
        result = await db.execute(select(Visit.patient_id).where(Visit.doctor_id == doctor.id).distinct())
        return set(result.scalars().all())
    if current_user.role != "researcher":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This graph view is limited to clinical roles or consent-authorized researchers.",
        )
    if not project_id:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="project_id is required for consent-scoped research graph queries.",
        )

    patient_sets = []
    for scope in scopes:
        allowed, reason, consents = await ConsentPolicyEngine.evaluate_research_access(
            db=db,
            actor=current_user,
            project_id=project_id,
            requested_scope=scope,
        )
        if not allowed:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Research graph query rejected by Consent Policy Engine: {reason}",
            )
        patient_sets.append({consent.patient_id for consent in consents})

    authorized = set.intersection(*patient_sets) if patient_sets else set()
    if len(authorized) < MIN_RESEARCH_GROUP_SIZE:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Research graph results require at least {MIN_RESEARCH_GROUP_SIZE} consented patients.",
        )
    return authorized


async def _consented_disease_graph(db: AsyncSession, patient_ids: Set[str]) -> Dict[str, Any]:
    if not patient_ids:
        return {"nodes": [], "edges": [], "disclaimer": "No patients have active consent for this project and scope."}

    rows = (await db.execute(
        select(Visit.patient_id, Disease.id, Disease.code, Disease.name)
        .join(Diagnosis, Diagnosis.visit_id == Visit.id)
        .join(Disease, Disease.id == Diagnosis.disease_id)
        .where(Visit.patient_id.in_(patient_ids))
    )).all()

    patient_diseases: Dict[str, Set[str]] = defaultdict(set)
    disease_info: Dict[str, Dict[str, str]] = {}
    for patient_id, disease_id, code, name in rows:
        patient_diseases[patient_id].add(disease_id)
        disease_info[disease_id] = {"code": code, "name": name}

    pair_patients: Dict[tuple[str, str], Set[str]] = defaultdict(set)
    for patient_id, diseases in patient_diseases.items():
        for left, right in combinations(sorted(diseases), 2):
            pair_patients[(left, right)].add(patient_id)

    disease_patients: Dict[str, Set[str]] = defaultdict(set)
    for patient_id, diseases in patient_diseases.items():
        for disease_id in diseases:
            disease_patients[disease_id].add(patient_id)
    visible_disease_ids = {
        disease_id for disease_id, patients in disease_patients.items()
        if len(patients) >= MIN_RESEARCH_GROUP_SIZE
    }

    nodes = [
        {"id": f"disease_{disease_id}", "label": "Disease", "properties": info}
        for disease_id, info in disease_info.items()
        if disease_id in visible_disease_ids
    ]
    edges = [
        {
            "id": f"consented_cooccur_{left}_{right}",
            "source": f"disease_{left}",
            "target": f"disease_{right}",
            "type": "CO_OCCURS_WITH",
            "properties": {"patient_count": len(patient_ids_for_pair)},
        }
        for (left, right), patient_ids_for_pair in pair_patients.items()
        if len(patient_ids_for_pair) >= MIN_RESEARCH_GROUP_SIZE
    ]
    return {
        "nodes": nodes,
        "edges": edges,
        "disclaimer": "Co-occurrence edges use only patients with active project consent; they do not imply causation.",
    }


async def _consented_drug_side_effect_graph(db: AsyncSession, patient_ids: Set[str]) -> Dict[str, Any]:
    if not patient_ids:
        return {"nodes": [], "edges": [], "disclaimer": "No patients have active consent for this project and scope."}

    rows = (await db.execute(
        select(
            ObservedAdverseEvent.patient_id,
            Medication.id,
            Medication.code,
            Medication.name,
            SideEffect.id,
            SideEffect.code,
            SideEffect.name,
        )
        .join(Prescription, Prescription.id == ObservedAdverseEvent.prescription_id)
        .join(Medication, Medication.id == Prescription.medication_id)
        .join(SideEffect, SideEffect.id == ObservedAdverseEvent.side_effect_id)
        .where(ObservedAdverseEvent.patient_id.in_(patient_ids))
    )).all()

    medication_info: Dict[str, Dict[str, str]] = {}
    side_effect_info: Dict[str, Dict[str, str]] = {}
    edge_patients: Dict[tuple[str, str], Set[str]] = defaultdict(set)
    medication_patients: Dict[str, Set[str]] = defaultdict(set)
    side_effect_patients: Dict[str, Set[str]] = defaultdict(set)
    for patient_id, medication_id, medication_code, medication_name, effect_id, effect_code, effect_name in rows:
        medication_info[medication_id] = {"code": medication_code, "name": medication_name}
        side_effect_info[effect_id] = {"code": effect_code, "name": effect_name}
        edge_patients[(medication_id, effect_id)].add(patient_id)
        medication_patients[medication_id].add(patient_id)
        side_effect_patients[effect_id].add(patient_id)

    nodes = [
        {"id": f"med_{medication_id}", "label": "Medication", "properties": info}
        for medication_id, info in medication_info.items()
        if len(medication_patients[medication_id]) >= MIN_RESEARCH_GROUP_SIZE
    ] + [
        {"id": f"se_{effect_id}", "label": "SideEffect", "properties": info}
        for effect_id, info in side_effect_info.items()
        if len(side_effect_patients[effect_id]) >= MIN_RESEARCH_GROUP_SIZE
    ]
    edges = [
        {
            "id": f"consented_side_effect_{medication_id}_{effect_id}",
            "source": f"med_{medication_id}",
            "target": f"se_{effect_id}",
            "type": "OBSERVED_WITH",
            "properties": {"patient_count": len(affected_patients), "evidence_quality": "OBSERVED_ASSOCIATION"},
        }
        for (medication_id, effect_id), affected_patients in edge_patients.items()
        if len(affected_patients) >= MIN_RESEARCH_GROUP_SIZE
    ]
    return {
        "nodes": nodes,
        "edges": edges,
        "disclaimer": "Associations use consented synthetic records and do not prove pharmacological causation.",
    }


@router.get("/overview", response_model=GraphDataOut)
async def get_graph_overview(
    project_id: Optional[str] = None,
    current_user: AppUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    patient_ids = await _authorized_research_patient_ids(
        project_id,
        ["aggregate_diagnoses", "medication_history"],
        current_user,
        db,
    )
    if patient_ids is None:
        return await GraphSyncService.get_graph_data()
    disease_graph = await _consented_disease_graph(db, patient_ids)
    drug_graph = await _consented_drug_side_effect_graph(db, patient_ids)
    return {
        "nodes": disease_graph["nodes"] + drug_graph["nodes"],
        "edges": disease_graph["edges"] + drug_graph["edges"],
        "disclaimer": "Graph includes only patients with active project consent for diagnosis and medication scopes; associations are not causal.",
    }

@router.get("/disease-cooccurrence", response_model=GraphDataOut)
async def get_disease_cooccurrence(
    project_id: Optional[str] = None,
    current_user: AppUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    patient_ids = await _authorized_research_patient_ids(
        project_id, ["aggregate_diagnoses"], current_user, db
    )
    if patient_ids is None:
        return await GraphSyncService.get_graph_data("disease_cooccurrence")
    return await _consented_disease_graph(db, patient_ids)

@router.get("/drug-side-effects", response_model=GraphDataOut)
async def get_drug_side_effects(
    project_id: Optional[str] = None,
    current_user: AppUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    patient_ids = await _authorized_research_patient_ids(
        project_id, ["medication_history"], current_user, db
    )
    if patient_ids is None:
        return await GraphSyncService.get_graph_data("drug_side_effects")
    return await _consented_drug_side_effect_graph(db, patient_ids)

@router.get("/treatments")
async def get_condition_treatments(
    condition_code: Optional[str] = None,
    project_id: Optional[str] = None,
    current_user: AppUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    patient_ids = await _authorized_research_patient_ids(
        project_id,
        ["aggregate_diagnoses", "medication_history"],
        current_user,
        db,
    )
    query = (
        select(
            Disease.code.label("disease_code"),
            Disease.name.label("disease_name"),
            Medication.code.label("drug_code"),
            Medication.name.label("drug_name"),
            func.count(func.distinct(Visit.patient_id)).label("patient_count"),
        )
        .join(Diagnosis, Diagnosis.visit_id == Visit.id)
        .join(Disease, Disease.id == Diagnosis.disease_id)
        .join(Prescription, Prescription.visit_id == Visit.id)
        .join(Medication, Medication.id == Prescription.medication_id)
        .group_by(Disease.code, Disease.name, Medication.code, Medication.name)
    )
    if condition_code:
        query = query.where(Disease.code == condition_code)
    if patient_ids is not None:
        query = query.where(Visit.patient_id.in_(patient_ids))

    rows = (await db.execute(query)).mappings().all()
    return {
        "results": [
            dict(row) for row in rows
            if patient_ids is None or row["patient_count"] >= MIN_RESEARCH_GROUP_SIZE
        ],
        "disclaimer": "Relationships are co-occurrences in synthetic visit records, not prescribing guidance or evidence of causation.",
    }

@router.get("/status", response_model=GraphSyncStatusOut)
async def get_graph_status(current_user: AppUser = Depends(require_role(["doctor", "admin"]))):
    status_info = GraphSyncService.get_status()
    return status_info

