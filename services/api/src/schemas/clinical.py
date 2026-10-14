from typing import List, Optional
from datetime import date, datetime
from pydantic import BaseModel

class PatientOut(BaseModel):
    id: str
    display_code: str
    date_of_birth: date
    sex: str
    created_at: datetime

    class Config:
        from_attributes = True

class DoctorOut(BaseModel):
    id: str
    display_name: str
    specialty: str
    hospital_name: Optional[str] = None

    class Config:
        from_attributes = True

class DiseaseOut(BaseModel):
    id: str
    code: str
    name: str
    description: Optional[str] = None

    class Config:
        from_attributes = True

class DiagnosisOut(BaseModel):
    id: str
    disease_code: str
    disease_name: str
    severity: str
    status: str
    diagnosed_at: datetime

class MedicationOut(BaseModel):
    id: str
    code: str
    name: str
    generic_name: str
    drug_class: str

    class Config:
        from_attributes = True

class PrescriptionOut(BaseModel):
    id: str
    medication_name: str
    medication_code: str
    dose_text: str
    frequency_text: str
    start_date: date
    end_date: Optional[date] = None

class LabResultOut(BaseModel):
    id: str
    test_name: str
    test_code: str
    result_value: float
    unit: str
    reference_range_text: str
    is_abnormal: bool
    measured_at: datetime

class TreatmentOut(BaseModel):
    id: str
    treatment_type: str
    description_code: str
    start_date: date
    end_date: Optional[date] = None
    outcome_status: str

class AdverseEventOut(BaseModel):
    id: str
    side_effect_name: str
    side_effect_code: str
    severity: str
    outcome: str
    evidence_quality: str
    reported_at: datetime

class VisitCreate(BaseModel):
    patient_id: str
    doctor_id: str
    hospital_id: str
    visit_type: str
    summary_code: Optional[str] = None

class VisitOut(BaseModel):
    id: str
    patient_id: str
    doctor_id: str
    doctor_name: Optional[str] = None
    hospital_name: Optional[str] = None
    visit_at: datetime
    visit_type: str
    summary_code: Optional[str] = None
    diagnoses: List[DiagnosisOut] = []
    prescriptions: List[PrescriptionOut] = []
    treatments: List[TreatmentOut] = []
    lab_results: List[LabResultOut] = []

    class Config:
        from_attributes = True

class PatientTimelineOut(BaseModel):
    patient: PatientOut
    visits: List[VisitOut]
    adverse_events: List[AdverseEventOut] = []
