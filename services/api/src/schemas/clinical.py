from typing import List, Optional
from datetime import date, datetime
from pydantic import BaseModel, Field

class PatientOut(BaseModel):
    """Returned only by care-role endpoints (/patients); never used by research or insurance APIs."""
    id: str
    display_code: str
    date_of_birth: date
    sex: str
    created_at: datetime
    display_name: Optional[str] = None
    record_status: str = "ACTIVE"
    merged_into_id: Optional[str] = None
    has_portal_account: bool = False

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
    allergy_override_reason: Optional[str] = None

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
    # Doctors record visits under their own profile; administrators choose the doctor.
    doctor_id: Optional[str] = None
    hospital_id: Optional[str] = None  # defaults to the doctor's hospital
    visit_type: str = Field(..., pattern="^(Outpatient Consultation|Inpatient Admission|Emergency Evaluation|Telehealth Review|Clinical Encounter)$")
    summary_code: Optional[str] = Field(default=None, max_length=50)
    visit_at: Optional[datetime] = None

class VisitOut(BaseModel):
    id: str
    patient_id: str
    doctor_id: str
    doctor_name: Optional[str] = None
    hospital_id: Optional[str] = None
    hospital_name: Optional[str] = None
    status: str = "ACTIVE"
    discharged_at: Optional[datetime] = None
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
    allergies: List[dict] = []
    care_team: List[dict] = []
    facilities: List[str] = []
