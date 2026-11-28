// Plain-language names for research consent scopes. The identifier stays visible next to the
// label, because it is what the consent engine and the audit trail record.
export const CONSENT_SCOPE_LABELS: Record<string, { label: string; detail: string }> = {
  aggregate_diagnoses: { label: "Diagnoses", detail: "Counted together with other patients' diagnoses" },
  medication_history: { label: "Medication history", detail: "Your prescriptions, counted together with other patients'" },
  lab_summaries: { label: "Lab result summaries", detail: "Summaries of your lab results, combined with other patients'" },
  deidentified_cohort: { label: "Study group membership", detail: "Whether you are counted in a de-identified study group" },
};

export function scopeLabel(scope: string) {
  return CONSENT_SCOPE_LABELS[scope]?.label ?? scope.replace(/_/g, " ");
}
