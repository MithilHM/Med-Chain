"""Deterministic, conservative patient matching for inbound clinical data.

A wrong match puts one person's clinical data in another person's chart, which is a
patient-safety event. These rules therefore prefer "send to human review" over guessing:

1. Match only on an exact (assigning authority, identifier value) pair.
2. If identifiers in one message resolve to different patients -> conflict (review).
3. If a match is found but date of birth or sex disagrees -> conflict (review); never merge silently.
4. Create a new patient only when the caller allows it (registration/admission feeds) and the
   message carries a real date of birth and sex. Nothing is defaulted or invented.

Probabilistic matching (name + DOB + address scoring) and an enterprise MPI are out of scope;
hospitals typically supply an EMPI identifier that can be added as another assigning authority.
"""
from dataclasses import dataclass
from datetime import date
from typing import Iterable, List, Optional, Tuple

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models import Patient, PatientIdentifier


class PatientMatchError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code  # NOT_FOUND | CONFLICT | INSUFFICIENT_DEMOGRAPHICS | NO_IDENTIFIER
        self.message = message


@dataclass(frozen=True)
class SourceIdentifier:
    system: str
    value: str
    identifier_type: str = "MR"


def normalize_sex(raw: Optional[str]) -> Optional[str]:
    if not raw:
        return None
    value = raw.strip().upper()
    if value in {"M", "MALE"}:
        return "M"
    if value in {"F", "FEMALE"}:
        return "F"
    if value in {"O", "OTHER", "A", "N"}:
        return "O"
    return None  # U / unknown is not evidence either way


async def find_patient(db: AsyncSession, identifiers: Iterable[SourceIdentifier]) -> Optional[Patient]:
    matched: Optional[Patient] = None
    for ident in identifiers:
        row = (await db.execute(
            select(PatientIdentifier).where(
                PatientIdentifier.system == ident.system, PatientIdentifier.value == ident.value
            )
        )).scalar_one_or_none()
        if row is None:
            continue
        if matched is not None and matched.id != row.patient_id:
            raise PatientMatchError(
                "CONFLICT", "Identifiers in this message belong to different patients; manual reconciliation required."
            )
        if matched is None:
            matched = await db.get(Patient, row.patient_id)
    return matched


def _check_demographics(patient: Patient, dob: Optional[date], sex: Optional[str]) -> None:
    mismatches = []
    if dob is not None and patient.date_of_birth != dob:
        mismatches.append("date of birth")
    if sex is not None and patient.sex != sex:
        mismatches.append("sex")
    if mismatches:
        raise PatientMatchError(
            "CONFLICT",
            f"Identifier matched an existing patient but {' and '.join(mismatches)} differ; manual review required.",
        )


async def _link_identifiers(db: AsyncSession, patient: Patient, identifiers: Iterable[SourceIdentifier]) -> None:
    for ident in identifiers:
        exists = (await db.execute(
            select(PatientIdentifier.id).where(
                PatientIdentifier.system == ident.system, PatientIdentifier.value == ident.value
            )
        )).scalar_one_or_none()
        if exists is None:
            db.add(PatientIdentifier(
                patient_id=patient.id, system=ident.system, value=ident.value, identifier_type=ident.identifier_type
            ))


async def _unique_display_code(db: AsyncSession, ident: SourceIdentifier) -> str:
    for candidate in (ident.value[:50], f"{ident.system}-{ident.value}"[:50]):
        taken = (await db.execute(select(Patient.id).where(Patient.display_code == candidate))).scalar_one_or_none()
        if taken is None:
            return candidate
    raise PatientMatchError("CONFLICT", "Could not allocate a unique display code for the new patient.")


async def match_or_create_patient(
    db: AsyncSession,
    identifiers: List[SourceIdentifier],
    date_of_birth: Optional[date],
    sex: Optional[str],
    allow_create: bool,
    enforce_demographics: bool = True,
) -> Tuple[Patient, bool]:
    """Return (patient, created). Raises PatientMatchError when a safe decision is not possible."""
    if not identifiers:
        raise PatientMatchError("NO_IDENTIFIER", "Message has no patient identifier with an assigning authority.")

    patient = await find_patient(db, identifiers)
    if patient is not None:
        if enforce_demographics:
            _check_demographics(patient, date_of_birth, sex)
        await _link_identifiers(db, patient, identifiers)
        return patient, False

    if not allow_create:
        raise PatientMatchError("NOT_FOUND", "No registered patient matches the message identifiers.")
    if date_of_birth is None or sex is None:
        raise PatientMatchError(
            "INSUFFICIENT_DEMOGRAPHICS", "A new patient requires a date of birth and sex; none were defaulted."
        )

    patient = Patient(display_code=await _unique_display_code(db, identifiers[0]), date_of_birth=date_of_birth, sex=sex)
    db.add(patient)
    await db.flush()
    await _link_identifiers(db, patient, identifiers)
    return patient, True
