from typing import List, Optional, Dict, Any, Literal
from datetime import datetime
from pydantic import BaseModel, Field, field_validator

FeatureGroup = Literal["diagnoses", "medications", "lab_abnormalities", "age_bracket"]

class CohortRunRequest(BaseModel):
    project_id: Optional[str] = None
    name: Optional[str] = Field(default="Cardio-Metabolic Risk Phenotype Cohort", min_length=1, max_length=150)
    description: Optional[str] = "Exploratory clustering cohort"
    k: Optional[int] = Field(default=None, gt=1, le=20)
    n_clusters: Optional[int] = Field(default=None, gt=1, le=20)
    features: List[FeatureGroup] = Field(
        default_factory=lambda: ["diagnoses", "medications", "lab_abnormalities"],
        min_length=1,
    )
    random_state: int = Field(default=42, ge=0, le=2**32 - 1)

    @field_validator("features")
    @classmethod
    def feature_groups_must_be_unique(cls, features: List[FeatureGroup]) -> List[FeatureGroup]:
        if len(features) != len(set(features)):
            raise ValueError("Feature groups must be unique.")
        return features

    @property
    def cluster_k(self) -> int:
        return self.k or self.n_clusters or 3

class CohortMembershipSummary(BaseModel):
    cluster_label: int
    cluster_name: str
    patient_count: int
    top_diagnoses: List[str]
    top_medications: List[str]
    avg_age: Optional[float] = None

class CohortOut(BaseModel):
    id: str
    name: str
    description: Optional[str] = None
    algorithm: str
    created_at: datetime
    clusters: List[CohortMembershipSummary] = []
    inertia: Optional[float] = None
    features: List[str] = []
    disclaimer: str = "Exploratory synthetic pattern only. Not for clinical diagnosis or causal inference."

    class Config:
        from_attributes = True
