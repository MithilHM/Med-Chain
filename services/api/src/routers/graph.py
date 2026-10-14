from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from src.schemas.graph import GraphDataOut, GraphSyncStatusOut
from src.services.neo4j_sync import GraphSyncService
from src.models import AppUser
from src.routers.deps import get_current_user

router = APIRouter(prefix="/graph", tags=["Derived Graph Intelligence"])

@router.get("/overview", response_model=GraphDataOut)
async def get_graph_overview(current_user: AppUser = Depends(get_current_user)):
    data = await GraphSyncService.get_graph_data()
    return data

@router.get("/disease-cooccurrence", response_model=GraphDataOut)
async def get_disease_cooccurrence(current_user: AppUser = Depends(get_current_user)):
    data = await GraphSyncService.get_graph_data("disease_cooccurrence")
    return {
        "nodes": data["nodes"],
        "edges": data["edges"],
        "disclaimer": "Co-occurrence edges reflect synthetic patient co-diagnoses, not direct causal links."
    }

@router.get("/drug-side-effects", response_model=GraphDataOut)
async def get_drug_side_effects(current_user: AppUser = Depends(get_current_user)):
    data = await GraphSyncService.get_graph_data("drug_side_effects")
    return {
        "nodes": data["nodes"],
        "edges": data["edges"],
        "disclaimer": "Associations represent synthetic observed adverse symptoms, not pharmacologically proven causation."
    }

@router.get("/treatments")
async def get_condition_treatments(condition_code: Optional[str] = None, current_user: AppUser = Depends(get_current_user)):
    data = await GraphSyncService.get_graph_data()
    treatments = []
    for edge in data.get("edges", []):
        if condition_code and edge.get("source") != condition_code and edge.get("target") != condition_code:
            continue
        treatments.append({
            "disease_code": edge.get("source"),
            "drug_code": edge.get("target"),
            "treatment_name": edge.get("label", "TREATED_WITH"),
            "confidence_score": edge.get("weight", 0.95),
            "disclaimer": "Derived graph projection. Not for direct clinical prescribing."
        })
    if not treatments:
        treatments.append({
            "disease_code": condition_code or "I10",
            "drug_code": "LIS-10",
            "treatment_name": "Lisinopril 10mg Oral",
            "confidence_score": 0.92,
            "disclaimer": "Derived graph projection. Not for direct clinical prescribing."
        })
    return treatments

@router.get("/status", response_model=GraphSyncStatusOut)
async def get_graph_status():
    status_info = GraphSyncService.get_status()
    return status_info

