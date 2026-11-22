# MedChain REST API Specification

**Base URL:** `/api/v1`  
**Authentication:** Short-lived JWT in an HttpOnly, SameSite cookie set by `/auth/login`; production responses do not return the token in JSON. Cookie-authenticated state-changing requests require an allowed `Origin`. For synthetic development/test only, login and demo-switch also return a bearer token for the existing automated API examples; bearer authentication is disabled in production.
**Default Error Format:**
```json
{
  "detail": "Error description message",
  "error_code": "RESOURCE_NOT_FOUND | PERMISSION_DENIED | CONSENT_REQUIRED | VALIDATION_ERROR"
}
```

### `GET /health`
- **Authorization:** Public minimal liveness probe; returns only `{"status":"ok"}`.
- **Note:** Dependency details are restricted to administrators at `/admin/health`.

---

## 1. Authentication & Session (`/auth`)

### `POST /auth/login`
- **Description:** Authenticate credentials and set a short-lived HttpOnly session cookie. Production does not return the token in JSON; synthetic development/test returns it for local automated API examples.
- **Request Body:**
  ```json
  {
    "email": "doctor@medchain.local",
    "password": "Password123!"
  }
  ```
- **Response `200 OK`:**
  ```json
  {
    "user": {
      "id": "uuid",
      "email": "doctor@medchain.local",
      "role": "doctor"
    }
  }
  ```

### `GET /auth/me`
- **Description:** Return authenticated user context and linked entity reference (e.g. `patient_id` or `doctor_id`).
- **Authorization:** Any authenticated user.

### `POST /auth/logout`
- **Description:** Invalidates previously issued tokens for the account and clears the session cookie.
- **Authorization:** Authenticated user. Cookie requests must include an allowed `Origin`.

---

## 2. Patients & Clinical Encounters (`/patients`, `/visits`, `/clinical`)

### `GET /patients`
- **Description:** Paginated list of patients.
- **Authorization:**
  - `doctor`: assigned patients only.
  - `admin`: all synthetic patients.
  - `patient`: only own patient record.
  - `researcher`, `insurance_analyst`: 403 Forbidden (must use dedicated de-identified/insurance endpoints).

### `GET /patients/{id}/timeline`
- **Description:** Complete chronological encounter timeline including visits, diagnoses, prescriptions, lab results, and document metadata.
- **Authorization:** Assigned doctor or owner patient.

### `POST /visits`
- **Description:** Create a new clinical visit.
- **Authorization:** `doctor` or `admin`.

---

## 3. Documents & Semi-Structured Data (`/documents`)

### `POST /documents`
- **Description:** Create clinical document (written to MongoDB) with relational metadata (in PostgreSQL).
- **Request Body:**
  ```json
  {
    "patient_id": "uuid",
    "visit_id": "uuid",
    "document_type": "clinical_note",
    "title": "Synthetic Cardiology Follow-up",
    "content": "Patient reports mild chest discomfort..."
  }
  ```
- **Authorization:** `doctor` assigned to the patient.

### `GET /documents/{id}`
- **Description:** Retrieve document metadata and decrypted/fetched narrative text.
- **Authorization:** Assigned doctor or owner patient. Strictly forbidden to researchers and insurance analysts.

---

## 4. Patient Consent & Research Engine (`/consents`, `/access-requests`, `/research`)

### `POST /research-projects`
- **Description:** Create a research initiative declaring purpose and requested scope.
- **Authorization:** `researcher` or `admin`.

### `POST /access-requests`
- **Description:** Request consent from a patient for a research project.
- **Request Body:**
  ```json
  {
    "patient_id": "uuid",
    "project_id": "uuid",
    "purpose": "Type 2 Diabetes Cohort Study",
    "requested_scope": ["aggregate_diagnoses", "medication_history"]
  }
  ```

### `POST /access-requests/{id}/decision`
- **Description:** Patient approves or rejects research access request. When approved, creates a `consent` record and anchors event on-chain.
- **Authorization:** Only the target `patient`.

### `POST /consents/{id}/revoke`
- **Description:** Instantly revoke active consent, blocking all subsequent research queries and emitting a revocation blockchain event.
- **Authorization:** Owner `patient`.
- **Persisted states:** `GRANTED` and `REVOKED`; active access also requires the consent validity window and requested scope to match.

### `POST /research/query`
- **Description:** Execute a privacy-preserving aggregate query against authorized data.
- **Request Body:**
  ```json
  {
    "project_id": "uuid",
    "query_type": "cohort_summary | disease_distribution | lab_trends",
    "filters": {"disease_code": "E11.9"}
  }
  ```
- **Consent Enforcement:**
  - Evaluates active consent for `project_id`.
  - If missing, expired, or revoked: returns `403 Forbidden` with `"error_code": "CONSENT_REVOKED_OR_MISSING"`.
  - Action and decision (`GRANTED` or `DENIED`) logged to `access_event`.

---

## 5. Blockchain & Integrity Verification (`/integrity`, `/blockchain`)

### `GET /integrity/verify/{document_id}`
- **Description:** Recalculates cryptographic commitment for the document version and compares against PostgreSQL and blockchain anchors.
- **Response `200 OK`:**
  ```json
  {
    "document_id": "uuid",
    "expected_hash": "0x4a9f...",
    "computed_hash": "0x4a9f...",
    "status": "VERIFIED_MATCH",
    "chain_tx_hash": "0x8f2c...",
    "chain_status": "CONFIRMED"
  }
  ```

### `POST /integrity/tamper-demo/{document_id}`
- **Description:** *DEMO ONLY.* Modifies one byte in MongoDB document content to prove tamper detection in the verification workflow.

### `GET /blockchain/status`
- **Authorization:** Admin only.
- **Description:** Returns RPC connectivity, configured and actual chain IDs, contract availability, contract address, and latest block when the RPC chain and deployed contract match configuration.

---

## 6. Insurance Analytics (`/insurance`)

- **Authorization scope:** `insurance_analyst` accounts must have an `insurance_analyst` profile linked to a provider. Policy and claim reads, submissions, reviews, anomaly resolution, and expenditure analytics are restricted to that provider. An analyst without a provider assignment is denied. `admin` can manage all providers; `patient` can read only their own policies and claims.

### `GET /insurance/claims`
- **Description:** List claims with anomaly review flags.
- **Authorization:** Provider-scoped `insurance_analyst` or `admin`.

### `POST /insurance/claims`
- **Description:** Transactional claim submission with items.
- **Rollback Demonstration:** Simulates transactional integrity with atomic rollback on invalid item totals.
- **Line item invariant:** The API calculates each line amount from quantity and unit cost; the relational schema checks the equation rounded to cents, including on SQLite fallback.

### `POST /insurance/claims/{id}/review`
- **Description:** Analyst records a human review decision (`APPROVED`, `REJECTED`, `UNDER_REVIEW`) and explanation.
- **Amount invariant:** An approved amount cannot exceed the claim amount; the API validates it and the SQLAlchemy schema defines the same database constraint. Existing databases need a migration to apply model changes.
- **Persisted claim states:** `SUBMITTED`, `UNDER_REVIEW`, `APPROVED`, and `REJECTED`.

### `GET /analytics/insurance/expenditure`
- **Description:** Disease-wise and treatment-type aggregate expenditures.

---

## 7. Derived Graph & Cohorts (`/graph`, `/cohorts`)

### `GET /graph/disease-cooccurrence`
- **Description:** Returns nodes and edges representing co-occurring diagnoses meeting minimum threshold.

### `GET /graph/drug-side-effects`
- **Description:** Returns medications and observed adverse events with explicit association disclaimers.

### `POST /cohorts/run`
- **Description:** Runs deterministic K-Means clustering over synthetic de-identified feature matrices.
- **Request Body:**
  ```json
  {
    "cohort_name": "Metabolic Cohort 2026",
    "k": 3,
    "feature_groups": ["diagnoses", "medications", "lab_abnormalities"]
  }
  ```

---

## 8. Admin & Operational Controls (`/admin`)

### `GET /admin/health`
- **Authorization:** Admin only.
- **Description:** Live probes for PostgreSQL, MongoDB, Neo4j, and the blockchain network. Reports `degraded` and names services using a fallback or unavailable mode.
- **Response `200 OK`:**
  ```json
  {
    "status": "degraded",
    "degraded_services": ["blockchain_evidence"],
    "services": {"relational_database": {"status": "up", "engine": "postgresql"}}
  }
  ```

### `GET /admin/dbms/showcase`
- **Authorization:** Admin only.
- **Description:** Lists fixed, read-only SQL examples for the relational DBMS showcase.

### `GET /admin/dbms/showcase/{query_id}`
- **Authorization:** Admin only.
- **Description:** Executes one allowlisted example: disease prevalence, high-cost disease cohorts, monthly claim windows, or an indexed lookup query plan. Callers cannot submit SQL. Aggregate output suppresses groups with fewer than five patients; the query plan returns no patient record.

### `POST /admin/graph/rebuild`
- **Description:** Drops and regenerates Neo4j projection from authoritative PostgreSQL tables.

### `POST /admin/demo/reset`
- **Description:** Clears all data stores and executes deterministic synthetic seed generator.


### `GET /admin/outbox/events` · `POST /admin/outbox/process` · `POST /admin/outbox/retry-failed`
- **Authorization:** Admin only.
- **Description:** Delivery status of chain evidence (counts by status, recent events with attempts, next retry, and last error); run one worker iteration on demand; requeue `FAILED` events after fixing the cause.

### `GET /admin/break-glass` · `POST /admin/break-glass/{grant_id}/review`
- **Authorization:** Admin only (a reviewer cannot review their own grant).
- **Description:** Compliance queue of emergency-access grants. Body for review: `{"outcome": "APPROPRIATE" | "INAPPROPRIATE", "note": "..."}`. `INAPPROPRIATE` revokes any remaining window immediately.

---

## 9. Emergency Access (`/patients`)

### `POST /patients/{patient_id}/break-glass`
- **Authorization:** Doctor or admin. Body: `{"justification": "at least 10 characters"}`.
- **Description:** Creates a time-boxed grant (`BREAK_GLASS_WINDOW_MINUTES`, default 240) that the access check honors, audits it, and announces it to administrators in real time.
- **Response:** `{"status": "GRANTED", "grant_id", "patient_id", "expires_at", "emergency_window_minutes", ...}`

---

## 10. Real-time Clinical Integration (`/integration`, `/events`)

### `POST /integration/hl7v2[?format=json]`
- **Authorization:** `X-Integration-Key` (per source system) or an admin session.
- **Body:** one HL7 v2 ER7 message (`Content-Type: x-application/hl7-v2+er7`).
- **Response:** an HL7 `ACK` (`MSA-1` = `AA` / `AR` / `AE`), plus headers `X-MedChain-Ack-Code`, `X-MedChain-Message-Status`, `X-MedChain-Message-Id`. See [INTEGRATION.md](INTEGRATION.md).

### `GET /integration/messages?status=NEEDS_REVIEW` · `POST /integration/messages/{id}/reprocess` · `GET /integration/status`
- **Authorization:** Admin only. Metadata only; raw payloads are never returned.

### `GET /events/stream`
- **Authorization:** Admin, doctor, or patient session (researchers and insurance analysts receive 403).
- **Response:** `text/event-stream`. Event types include `encounter.admitted`, `encounter.discharged`, `lab_result.created`, `lab_result.corrected`, `patient.registered`, `document.created`, `document.amended`, `consent.revoked`, and (admins only) `break_glass.granted` and `integration.needs_review`. Payloads carry identifiers and flags only. The stream sends `session_expired` and closes when the session is revoked or expires.

### Chain status in write responses
Consent decisions, revocations, and amendments return `"chain_status": "QUEUED"`: the database change is authoritative immediately, and the evidence is delivered by the outbox worker.

---

## 11. Identity: SSO, MFA, and SCIM (`/auth`, `/scim/v2`)

### `GET /auth/config`
- **Public.** Which sign-in methods the login page offers: `{oidc_enabled, oidc_login_url, password_login, demo_mode}`.

### `POST /auth/login`
- Password step. Returns `{"user": ...}` with a session cookie, or `{"mfa_required": true, "mfa_token": "..."}` when the account has MFA (no session is issued yet). Returns 403 if the role requires MFA and none is enrolled, and 429 when the shared per-client rate limit is exceeded.

### `POST /auth/mfa/verify`
- Body `{"mfa_token", "code"}`. `code` is a current TOTP code or a one-time recovery code; a reused time step is rejected. Issues the session.

### `POST /auth/mfa/enroll` · `POST /auth/mfa/activate` · `POST /auth/mfa/disable`
- Local accounts only. `enroll` returns `{secret, otpauth_uri}`; `activate` (body `{"code"}`) returns one-time `recovery_codes`; `disable` requires a current code, is refused for MFA-required roles, and signs out every session.

### `GET /auth/oidc/login` → `GET /auth/oidc/callback`
- Hospital SSO (authorization code + PKCE). The callback verifies the ID token, maps directory groups to a role through `OIDC_ROLE_MAP`, links or (if enabled) provisions the account, sets the session cookie, and redirects to `OIDC_POST_LOGIN_REDIRECT`.

### `/scim/v2/Users`
- `GET` (with `filter=userName eq "..."`), `GET /{id}`, `POST`, `PUT /{id}`, `PATCH /{id}` (`active`, `roles`, `userName`), `DELETE /{id}` (deactivates). Authenticated with `Authorization: Bearer <token>` matching `SCIM_BEARER_TOKEN_HASH`. Deactivation revokes sessions immediately.

## 12. Merges and Operations (`/integration/merges`, `/admin`, `/metrics`)

### `GET /integration/merges?status=PENDING` · `POST /integration/merges` · `POST /integration/merges/{id}/approve|reject`
- **Admin only.** Proposals come from ADT^A40 or an operator (`{surviving_patient_id, retiring_patient_id, reason}`). Approval needs a different administrator and identical dates of birth, and moves clinical, consent, coverage, identity, and care-team rows in one transaction. The retired record becomes `MERGED` and read-only (writes return 409).

### `GET /admin/alerts` · `POST /admin/alerts/evaluate`
- Open (or, with `include_resolved=true`, all) operational alerts; evaluate now.

### `GET /admin/encryption/status`
- Active key, configured key IDs, and counts of encrypted values per key ID for each encrypted field.

### `GET /metrics`
- Prometheus text format. `Authorization: Bearer <token>` matching `METRICS_BEARER_TOKEN_HASH`, or an admin session. Counts only; no patient data.

### Patient endpoints (changes)
- `GET /patients?family_name=Doe&limit=&offset=`: exact, accent- and case-insensitive family-name search (blind index).
- `PatientOut` now includes `display_name`, `record_status`, and `merged_into_id`.
- `POST /patients` accepts `given_name` and `family_name`.
- `GET /patients/{id}/timeline?limit=&offset=&include_cancelled=` is paginated and hides cancelled visits by default.
