from typing import List, Optional, Dict, Any
from datetime import datetime
from pydantic import BaseModel

class CohortRunRequest(BaseModel):
    name: Optional[str] = "Cardio-Metabolic Risk Phenotype Cohort"
    description: Optional[str] = "Exploratory clustering cohort"
    k: Optional[int] = None
    n_clusters: Optional[int] = None
    features: Optional[List[str]] = ["diagnoses", "medications", "lab_abnormalities"]
    random_state: int = 42

    @property
    def cluster_k(self) -> int:
        return self.k or self.n_clusters or 3

class CohortMembershipSummary(BaseModel):
    cluster_label: int
    cluster_name: str
    patient_count: int
    top_diagnoses: List[str]
    top_medications: List[str]
    avg_age: float

class CohortOut(BaseModel):
    id: str
    name: str
    description: Optional[str] = None
    algorithm: str
    created_at: datetime
    clusters: List[CohortMembershipSummary] = []
    inertia: Optional[float] = None
    disclaimer: str = "Exploratory synthetic pattern only. Not for clinical diagnosis or causal inference."

    class Config:
        from_attributes = True
