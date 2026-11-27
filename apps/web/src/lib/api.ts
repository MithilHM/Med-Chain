const API_BASE = "/api/v1";

/** Epoch ms for an API timestamp. Values without an offset (SQLite dev databases) are UTC. */
export const utcTime = (value: string) => Date.parse(/(Z|[+-]\d\d:?\d\d)$/.test(value) ? value : `${value}Z`);
const USER_KEY = "medchain_user";

function notifyUserContextChanged() {
  if (typeof window !== "undefined") {
    window.dispatchEvent(new Event("medchain-user-context-changed"));
  }
}

export interface UserContext {
  id: string;
  email: string;
  role: string;
  is_active: boolean;
  demo_mode?: boolean;
  patient_id?: string | null;
  doctor_id?: string | null;
  mfa_enabled?: boolean;
  auth_source?: string;
}

export interface ApiError extends Error {
  status?: number;
  detail?: any;
}

/** Fired when an API call finds the session gone (idle timeout, revoked, or shift limit). */
export const SESSION_EXPIRED_EVENT = "medchain-session-expired";
const SELF_HANDLED_401 = ["/auth/login", "/auth/mfa/verify", "/auth/signup", "/auth/invitations/", "/auth/me", "/auth/refresh", "/auth/logout"];

type RequestOptions = Omit<RequestInit, "body"> & { body?: unknown };

async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const headers = new Headers(options.headers);
  headers.set("Accept", "application/json");
  // Authentication uses the HttpOnly session cookie only; JavaScript never holds a bearer token.

  if (options.body !== undefined) {
    headers.set("Content-Type", "application/json");
  }

  const response = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers,
    body: options.body === undefined ? undefined : JSON.stringify(options.body),
    credentials: "same-origin",
    cache: "no-store",
  });

  if (!response.ok) {
    let message = `Request failed (${response.status})`;
    let detail: any;
    try {
      const payload = await response.json();
      detail = payload?.detail;
      message = typeof detail === "string" ? detail
        // FastAPI validation errors: [{loc, msg}, ...]; drop pydantic's "Value error, " prefix.
        : Array.isArray(detail) ? detail.map((d) => String(d?.msg ?? d).replace(/^Value error, /, "")).join(" ")
        : detail?.message || JSON.stringify(detail || payload);
    } catch {
      // Keep the status-based message when the server did not return JSON.
    }
    const error = new Error(message) as ApiError;
    error.status = response.status;
    error.detail = detail;
    // Sign-in endpoints answer 401 for bad credentials, and AuthShell handles /auth/me and /auth/refresh
    // itself; anywhere else a 401 means the session ended.
    if (response.status === 401 && !SELF_HANDLED_401.some((p) => path.startsWith(p)) && typeof window !== "undefined") {
      window.dispatchEvent(new CustomEvent(SESSION_EXPIRED_EVENT, { detail: message }));
    }
    throw error;
  }

  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

function query(values: Record<string, string | number | boolean | undefined>): string {
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(values)) {
    if (value !== undefined) params.set(key, String(value));
  }
  const serialized = params.toString();
  return serialized ? `?${serialized}` : "";
}

export const ApiClient = {
  getAuthConfig: () =>
    request<{ password_login: boolean; oidc_enabled: boolean; oidc_login_url: string | null; demo_mode: boolean }>("/auth/config"),

  /** Password step. Returns either a signed-in user or an MFA challenge token. */
  async login(email: string, password: string) {
    const result = await request<{ user?: UserContext; mfa_required?: boolean; mfa_token?: string }>("/auth/login", {
      method: "POST",
      body: { email, password },
    });
    if (result.user && typeof window !== "undefined") {
      window.localStorage.setItem(USER_KEY, JSON.stringify(result.user));
      notifyUserContextChanged();
    }
    return result;
  },

  async verifyMfa(mfaToken: string, code: string) {
    const result = await request<{ user: UserContext }>("/auth/mfa/verify", {
      method: "POST",
      body: { mfa_token: mfaToken, code },
    });
    if (typeof window !== "undefined") {
      window.localStorage.setItem(USER_KEY, JSON.stringify(result.user));
      notifyUserContextChanged();
    }
    return result;
  },

  enrollMfa: () => request<{ secret: string; otpauth_uri: string }>("/auth/mfa/enroll", { method: "POST" }),
  activateMfa: (code: string) =>
    request<{ status: string; recovery_codes: string[] }>("/auth/mfa/activate", { method: "POST", body: { code } }),
  disableMfa: (code: string) => request<any>("/auth/mfa/disable", { method: "POST", body: { code } }),
  getMySessions: () => request<any[]>("/auth/sessions"),

  getAlerts: (includeResolved = false) => request<any[]>(`/admin/alerts${query({ include_resolved: includeResolved })}`),
  evaluateAlerts: () => request<any>("/admin/alerts/evaluate", { method: "POST" }),
  getOutboxDelivery: (status?: string) => request<any>(`/admin/outbox/events${query({ status })}`),
  getIntegrationStatus: () => request<any>("/integration/status"),
  getInboundMessages: (status?: string) => request<any[]>(`/integration/messages${query({ status })}`),
  reprocessInboundMessage: (id: string) =>
    request<any>(`/integration/messages/${encodeURIComponent(id)}/reprocess`, { method: "POST" }),
  getMergeRequests: (status = "PENDING") => request<any[]>(`/integration/merges${query({ status })}`),
  decideMerge: (id: string, decision: "approve" | "reject", note?: string) =>
    request<any>(`/integration/merges/${encodeURIComponent(id)}/${decision}`, { method: "POST", body: { note } }),
  getBreakGlassGrants: (reviewStatus = "PENDING_REVIEW") =>
    request<any[]>(`/admin/break-glass${query({ review_status: reviewStatus })}`),
  reviewBreakGlass: (id: string, outcome: "APPROPRIATE" | "INAPPROPRIATE", note?: string) =>
    request<any>(`/admin/break-glass/${encodeURIComponent(id)}/review`, { method: "POST", body: { outcome, note } }),
  getEncryptionStatus: () => request<any>("/admin/encryption/status"),

  async demoSwitch(role: string) {
    const result = await request<{ user: UserContext; access_token?: string }>(
      `/auth/demo-switch${query({ role })}`,
      { method: "POST" },
    );
    if (typeof window !== "undefined") {
      window.localStorage.setItem(USER_KEY, JSON.stringify(result.user));
      notifyUserContextChanged();
    }
    return result;
  },

  async getCurrentUser() {
    return request<UserContext>("/auth/me");
  },

  refreshSession: () => request<{ status: string; idle_timeout_seconds: number }>("/auth/refresh", { method: "POST" }),

  clearLocalUser() {
    if (typeof window !== "undefined") {
      window.localStorage.removeItem("medchain_token"); // legacy value from older builds
      window.localStorage.removeItem(USER_KEY);
      window.localStorage.removeItem("medchain_session_refreshed"); // AuthShell's idle-timeout clock
      notifyUserContextChanged();
    }
  },

  async logout() {
    try {
      await request<void>("/auth/logout", { method: "POST" });
    } catch {
      // Clear browser state even if the API is temporarily unavailable.
    } finally {
      ApiClient.clearLocalUser();
    }
  },

  getSystemHealth: () => request<any>("/health"),
  getAdminHealth: () => request<any>("/admin/health"),
  getDbmsShowcaseQueries: () => request<any[]>("/admin/dbms/showcase"),
  runDbmsShowcaseQuery: (queryId: string) =>
    request<any>(`/admin/dbms/showcase/${encodeURIComponent(queryId)}`),

  getPatients: (q?: string) => request<any[]>(`/patients${query({ q: q || undefined })}`),
  getPatient: (patientId: string) => request<any>(`/patients/${encodeURIComponent(patientId)}`),
  getPatientTimeline: (patientId: string) =>
    request<any>(`/patients/${encodeURIComponent(patientId)}/timeline`),

  /** Administrators only. Returns the patient plus a one-time portal code when requested. */
  registerPatient: (payload: {
    display_code: string; date_of_birth: string; sex: string; given_name?: string; family_name?: string;
    hospital_id: string; primary_doctor_id?: string; issue_portal_invitation?: boolean;
  }) => request<any>("/patients", { method: "POST", body: payload }),
  updatePatient: (patientId: string, payload: Record<string, any>) =>
    request<any>(`/patients/${encodeURIComponent(patientId)}`, { method: "PATCH", body: payload }),
  issuePortalInvitation: (patientId: string) =>
    request<any>(`/patients/${encodeURIComponent(patientId)}/portal-invitation`, { method: "POST" }),
  getCareTeam: (patientId: string) => request<any[]>(`/patients/${encodeURIComponent(patientId)}/care-team`),
  addCareTeamMember: (patientId: string, doctorId: string, relationshipType: string) =>
    request<any>(`/patients/${encodeURIComponent(patientId)}/care-team`, {
      method: "POST", body: { doctor_id: doctorId, relationship_type: relationshipType },
    }),
  endCareTeamMember: (patientId: string, assignmentId: string) =>
    request<any>(`/patients/${encodeURIComponent(patientId)}/care-team/${encodeURIComponent(assignmentId)}`, { method: "DELETE" }),
  addAllergy: (patientId: string, payload: { substance: string; reaction?: string; severity: string }) =>
    request<any>(`/patients/${encodeURIComponent(patientId)}/allergies`, { method: "POST", body: payload }),
  updateAllergyStatus: (patientId: string, allergyId: string, status: string) =>
    request<any>(`/patients/${encodeURIComponent(patientId)}/allergies/${encodeURIComponent(allergyId)}`, {
      method: "PATCH", body: { status },
    }),

  getDoctors: () => request<any[]>("/doctors"),
  getDiseases: () => request<any[]>("/diseases"),
  getMedications: () => request<any[]>("/medications"),
  getLabTests: () => request<any[]>("/lab-tests"),
  addDiagnosis: (visitId: string, payload: { disease_code: string; severity: string; status?: string }) =>
    request<any>(`/visits/${encodeURIComponent(visitId)}/diagnoses`, { method: "POST", body: payload }),
  addPrescription: (visitId: string, payload: Record<string, any>) =>
    request<any>(`/visits/${encodeURIComponent(visitId)}/prescriptions`, { method: "POST", body: payload }),
  addLabResult: (visitId: string, payload: { lab_test_code: string; result_value: number }) =>
    request<any>(`/visits/${encodeURIComponent(visitId)}/lab-results`, { method: "POST", body: payload }),
  dischargeVisit: (visitId: string) =>
    request<any>(`/visits/${encodeURIComponent(visitId)}/discharge`, { method: "POST" }),

  // Sign-up, activation, and account administration
  previewInvitation: (token: string) => request<any>(`/auth/invitations/${encodeURIComponent(token.trim())}`),
  async signup(payload: { token: string; password: string; email?: string; date_of_birth?: string }) {
    const result = await request<any>("/auth/signup", { method: "POST", body: payload });
    if (result.user && typeof window !== "undefined") {
      window.localStorage.setItem(USER_KEY, JSON.stringify(result.user));
      notifyUserContextChanged();
    }
    return result;
  },
  changePassword: (currentPassword: string, newPassword: string) =>
    request<any>("/auth/password", { method: "POST", body: { current_password: currentPassword, new_password: newPassword } }),
  listUsers: (role?: string) => request<any[]>(`/admin/users${query({ role })}`),
  createStaffUser: (payload: Record<string, any>) => request<any>("/admin/users", { method: "POST", body: payload }),
  updateUser: (userId: string, payload: { is_active?: boolean; role?: string }) =>
    request<any>(`/admin/users/${encodeURIComponent(userId)}`, { method: "PATCH", body: payload }),
  issuePasswordReset: (userId: string) =>
    request<any>(`/admin/users/${encodeURIComponent(userId)}/password-reset`, { method: "POST" }),
  resetUserMfa: (userId: string) => request<any>(`/admin/users/${encodeURIComponent(userId)}/mfa-reset`, { method: "POST" }),
  createHospital: (payload: { name: string; region: string; facility_code: string }) =>
    request<any>("/admin/hospitals", { method: "POST", body: payload }),
  getInsuranceProviders: () => request<any[]>("/admin/insurance-providers"),

  breakGlassEmergency: (patientId: string, justification: string) =>
    request<any>(`/patients/${encodeURIComponent(patientId)}/break-glass`, {
      method: "POST",
      body: { justification },
    }),

  createVisit: (payload: Record<string, any>) =>
    request<any>("/visits", { method: "POST", body: payload }),

  getDocuments: (patientId?: string) =>
    request<any[]>(`/documents${query({ patient_id: patientId })}`),
  getDocumentDetail: (documentId: string) =>
    request<any>(`/documents/${encodeURIComponent(documentId)}`),
  createDocument: (document: {
    patient_id: string;
    visit_id?: string;
    document_type: string;
    title: string;
    content: string;
    structured_extract?: Record<string, unknown>;
  }) => request<any>("/documents", { method: "POST", body: document }),

  amendDocument: (
    documentId: string,
    payload: { amendment_text: string; reason: string; author_signature?: string }
  ) =>
    request<any>(`/documents/${encodeURIComponent(documentId)}/amend`, {
      method: "POST",
      body: payload,
    }),

  getConsents: () => request<any[]>("/consents"),
  getAccessRequests: () => request<any[]>("/access-requests"),
  createAccessRequest: (input: {
    patient_id: string;
    project_id: string;
    purpose: string;
    requested_scopes: string[];
  }) => request<any>("/access-requests", { method: "POST", body: input }),
  decideAccessRequest: (requestId: string, decision: "APPROVED" | "REJECTED", validDays = 30, approvedScopes?: string[]) =>
    request<any>(`/access-requests/${encodeURIComponent(requestId)}/decision`, {
      method: "POST",
      body: { decision, valid_days: validDays, ...(approvedScopes ? { approved_scopes: approvedScopes } : {}) },
    }),
  revokeConsent: (consentId: string) =>
    request<any>(`/consents/${encodeURIComponent(consentId)}/revoke`, { method: "POST" }),

  getResearchProjects: () => request<any[]>("/research-projects"),
  createResearchProject: (input: { title: string; purpose: string }) =>
    request<any>("/research-projects", { method: "POST", body: input }),
  executeResearchQuery: (input: {
    project_id: string;
    query_type: string;
    disease_code?: string;
    filters?: Record<string, unknown>;
  }) => request<any>("/research/query", { method: "POST", body: input }),

  getInsuranceClaims: (flaggedOnly = false) =>
    request<any[]>(`/insurance/claims${query({ flagged_only: flaggedOnly || undefined })}`),
  getInsurancePolicies: (patientId?: string) =>
    request<any[]>(`/insurance/policies${query({ patient_id: patientId })}`),
  getInsuranceExpenditure: () => request<any>("/insurance/analytics/expenditure"),
  createInsuranceClaim: (input: {
    policy_id: string;
    visit_id: string;
    items: Array<{
      item_code: string;
      description: string;
      quantity: number;
      unit_cost: number;
      treatment_id?: string;
    }>;
  }) => request<any>("/insurance/claims", { method: "POST", body: input }),
  reviewClaim: (
    claimId: string,
    decision: string,
    reason: string,
    approvedAmount?: number,
  ) =>
    request<any>(`/insurance/claims/${encodeURIComponent(claimId)}/review`, {
      method: "POST",
      body: { decision, reason, approved_amount: approvedAmount },
    }),

  getGraphOverview: (projectId?: string) =>
    request<any>(`/graph/overview${query({ project_id: projectId })}`),
  getDiseaseCooccurrence: (projectId?: string) =>
    request<any>(`/graph/disease-cooccurrence${query({ project_id: projectId })}`),
  getDrugSideEffects: (projectId?: string) =>
    request<any>(`/graph/drug-side-effects${query({ project_id: projectId })}`),
  getConditionTreatments: (conditionCode?: string, projectId?: string) =>
    request<any>(`/graph/treatments${query({ condition_code: conditionCode, project_id: projectId })}`),
  rebuildGraph: () => request<any>("/admin/graph/rebuild", { method: "POST" }),

  getCohorts: (projectId?: string) =>
    request<any[]>(`/cohorts${query({ project_id: projectId })}`),
  runCohortClustering: (input: {
    project_id: string;
    name: string;
    k: number;
    features: string[];
    random_state: number;
  }) => request<any>("/cohorts/run", { method: "POST", body: input }),

  getAuditEvents: () => request<any[]>("/audit/events"),
  verifyDocument: (documentId: string) =>
    request<any>(`/integrity/verify/${encodeURIComponent(documentId)}`),
  tamperDocumentDemo: (documentId: string) =>
    request<any>(`/integrity/tamper-demo/${encodeURIComponent(documentId)}`, { method: "POST" }),
  getBlockchainStatus: () => request<any>("/blockchain/status"),
  resetDemo: () => request<any>("/admin/demo/reset", { method: "POST" }),

  // HL7 FHIR Interoperability
  getFhirMetadata: () => request<any>("/fhir/metadata"),
  importFhirBundle: (bundle: Record<string, any>) =>
    request<any>("/fhir/import", { method: "POST", body: bundle }),
  exportPatientFhir: (patientId: string) =>
    request<any>(`/fhir/patients/${encodeURIComponent(patientId)}/export`),

  // Outbox Telemetry & Disaster Recovery
  getOutboxEvents: async (limit = 50) =>
    (await request<{ events: any[] }>(`/admin/outbox/events${query({ limit })}`)).events,
  processOutbox: (limit = 20) => request<any>(`/admin/outbox/process${query({ limit })}`, { method: "POST" }),
  retryFailedOutbox: () => request<any>("/admin/outbox/retry-failed", { method: "POST" }),
  getHospitals: () => request<any[]>("/admin/hospitals"),
  getDisasterRecovery: () => request<any>("/admin/disaster-recovery"),

  // Workstation Sessions
  listSessions: () => request<any[]>("/auth/sessions"),
  revokeAllSessions: () => request<any>("/auth/sessions/revoke-all", { method: "POST" }),
};
