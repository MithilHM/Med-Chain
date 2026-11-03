const API_BASE = "/api/v1";
const TOKEN_KEY = "medchain_token";
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
}

export interface ApiError extends Error {
  status?: number;
}

type RequestOptions = Omit<RequestInit, "body"> & { body?: unknown };

async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const headers = new Headers(options.headers);
  headers.set("Accept", "application/json");

  if (options.body !== undefined) {
    headers.set("Content-Type", "application/json");
  }

  if (typeof window !== "undefined") {
    const token = window.localStorage.getItem(TOKEN_KEY);
    if (token) headers.set("Authorization", `Bearer ${token}`);
  }

  const response = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers,
    body: options.body === undefined ? undefined : JSON.stringify(options.body),
    cache: "no-store",
  });

  if (!response.ok) {
    let message = `Request failed (${response.status})`;
    try {
      const payload = await response.json();
      const detail = payload?.detail;
      message = typeof detail === "string" ? detail : detail?.message || JSON.stringify(detail || payload);
    } catch {
      // Keep the status-based message when the server did not return JSON.
    }
    const error = new Error(message) as ApiError;
    error.status = response.status;
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
  async login(email: string, password: string) {
    const result = await request<{ access_token: string; user: UserContext }>("/auth/login", {
      method: "POST",
      body: { email, password },
    });
    if (typeof window !== "undefined") {
      window.localStorage.setItem(TOKEN_KEY, result.access_token);
      window.localStorage.setItem(USER_KEY, JSON.stringify(result.user));
      notifyUserContextChanged();
    }
    return result;
  },

  async demoSwitch(role: string) {
    const result = await request<{ access_token: string; user: UserContext }>(
      `/auth/demo-switch${query({ role })}`,
      { method: "POST" },
    );
    if (typeof window !== "undefined") {
      window.localStorage.setItem(TOKEN_KEY, result.access_token);
      window.localStorage.setItem(USER_KEY, JSON.stringify(result.user));
      notifyUserContextChanged();
    }
    return result;
  },

  async getCurrentUser() {
    return request<UserContext>("/auth/me");
  },

  logout() {
    if (typeof window !== "undefined") {
      window.localStorage.removeItem(TOKEN_KEY);
      window.localStorage.removeItem(USER_KEY);
      notifyUserContextChanged();
    }
  },

  getSystemHealth: () => request<any>("/admin/health"),
  getDbmsShowcaseQueries: () => request<any[]>("/admin/dbms/showcase"),
  runDbmsShowcaseQuery: (queryId: string) =>
    request<any>(`/admin/dbms/showcase/${encodeURIComponent(queryId)}`),
  getPatients: () => request<any[]>("/patients"),
  getPatient: (patientId: string) => request<any>(`/patients/${encodeURIComponent(patientId)}`),
  getPatientTimeline: (patientId: string) =>
    request<any>(`/patients/${encodeURIComponent(patientId)}/timeline`),

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
};
