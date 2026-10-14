# Product Requirements Document (PRD)

## Privacy-Preserving Healthcare Intelligence & Research Database

**Document type:** Implementation-ready PRD for an agentic coding IDE\
**Project type:** Undergraduate DBMS capstone\
**Primary objective:** Build an end-to-end, locally runnable healthcare
data platform demonstrating database engineering, privacy-aware data
sharing, research analytics, insurance analytics, graph relationships,
and blockchain-backed consent/auditability.

------------------------------------------------------------------------

## 1. Instructions to the Coding Agent

Build this project end to end in clearly separated phases. Do not stop
after scaffolding or produce mock screens with non-functional controls.
Every visible action must be wired to a working backend and persistent
data, except where explicitly marked as a demo-only simulation.

Before implementation: 1. Inspect the repository and preserve useful
existing code. 2. Create `docs/IMPLEMENTATION_PLAN.md` with phases,
dependencies, and acceptance checks. 3. Create `docs/ARCHITECTURE.md`,
`docs/ERD.md`, and `docs/API.md`. 4. Implement one phase at a time. Run
its tests before proceeding. 5. Keep the project runnable with
documented commands and Docker Compose. 6. Use synthetic data only. Do
not connect to real hospital systems or use real patient information. 7.
Do not claim clinical validity, causal discovery, regulatory compliance,
or production readiness. 8. If a dependency or feature cannot run in the
local environment, document the limitation and provide a functional
fallback rather than silently faking success.

## 2. Product Summary

The platform integrates: - **PostgreSQL** as the authoritative
relational source of truth for structured healthcare and insurance
data. - **MongoDB** for semi-structured clinical notes, diagnostic
documents, and variable-format medical records. - **Neo4j** as a derived
graph projection for exploring patient--disease--drug--side-effect
relationships. - **Machine-learning-based cohorting** to group
synthetic, de-identified patient records using selected clinical
features. - **A local blockchain development network** with Solidity
smart contracts for consent events and tamper-evident audit
commitments. - **A web application** with role-specific workflows for
patients, doctors, researchers, insurance analysts, and administrators.

The platform is a database-engineering project first. AI/ML and graph
analysis are applications built on carefully modelled, access-controlled
data.

### 2.1 Problem Statement

Healthcare information is heterogeneous and spread across structured
records, clinical documents, treatment history, and insurance claims.
Researchers need to investigate patterns across conditions and
medications, while patients need transparent control over permitted data
sharing. The system demonstrates how relational data, document data,
graph relationships, and a blockchain-backed consent/audit trail can be
integrated without storing medical records directly on-chain.

### 2.2 Goals

1.  Maintain normalized, consistent healthcare and insurance data.
2.  Demonstrate advanced SQL, constraints, indexes, transactions, views,
    and audit history.
3.  Integrate relational records with semi-structured documents.
4.  Explore disease, medication, patient, and observed-side-effect
    relationships through a graph.
5.  Generate explainable patient cohorts from synthetic data.
6.  Let patients grant, scope, expire, and revoke data-sharing consent.
7.  Make record-integrity checks and consent/access events auditable.
8.  Provide role-based access and privacy-preserving research views.
9.  Deliver a complete, demonstrable local application with seed data,
    tests, documentation, and repeatable setup.

### 2.3 Non-Goals

-   No production deployment or connection to actual hospital/insurance
    systems.
-   No medical diagnosis, treatment recommendation, or clinical decision
    support.
-   No assertion that a drug caused an observed side effect; report
    associations only.
-   No automated approval/rejection of insurance claims.
-   No storage of raw medical records, names, phone numbers, government
    IDs, or other direct identifiers on-chain.
-   No claim that blockchain alone guarantees confidentiality, deletion,
    legal compliance, or access control.
-   No complex federated learning, zero-knowledge proof system, or
    production-grade identity infrastructure in the MVP.
-   No requirement for external paid APIs or cloud services.

------------------------------------------------------------------------

## 3. Target Users and Permissions

Implement authentication and server-side authorization for these roles.

### 3.1 Patient

-   View their own synthetic profile, visits, diagnoses, prescriptions,
    lab summaries, and linked documents.
-   Review access requests from research organizations.
-   Grant consent with purpose, data scope, access type, and expiry.
-   Revoke active consent.
-   View a history of grants, revocations, and recorded access events.
-   Request integrity verification for an eligible record.

### 3.2 Doctor

-   View patients assigned to the doctor in the seeded demo.
-   Add and update visits, diagnoses, prescriptions, treatments, and lab
    results.
-   Upload or create synthetic clinical documents.
-   View record integrity status and relevant audit history.
-   Cannot access unrelated patients by changing a URL or API
    identifier.

### 3.3 Researcher

-   Create a research project with a declared purpose and requested data
    scope.
-   Submit an access request.
-   Query only approved, de-identified datasets within the consent
    scope.
-   Explore aggregate cohort and graph results.
-   Cannot retrieve direct patient identifiers or raw clinical documents
    unless a separately modelled permission explicitly permits it; the
    default research scope must not permit this.
-   See aggregate counts and documented caveats, not unsupported causal
    conclusions.

### 3.4 Insurance Analyst

-   View policy, claim, claim-item, treatment, and billing information
    required for insurance workflows.
-   Run disease-wise cost and utilization reports using permitted
    fields.
-   Flag possible duplicate or anomalous claims for human review.
-   Cannot see full clinical notes by default.
-   Cannot use insurance permissions to gain research access.

### 3.5 Administrator

-   Manage demo users, roles, hospitals, reference data, and system
    health.
-   View operational/audit metadata.
-   Cannot bypass patient consent for research exports through ordinary
    application endpoints.
-   Any exceptional administrative action must be explicitly recorded
    and visible in the audit trail.

**Security rule:** Hiding a UI element is not authorization. Enforce
role, ownership, scope, expiry, and revocation in backend services for
every protected request.

------------------------------------------------------------------------

## 4. Technology Stack

Use the following stack unless the repository already has a working
equivalent; document any substitution.

-   **Frontend:** Next.js (TypeScript), React, Tailwind CSS.
-   **Backend API:** Python FastAPI, Pydantic validation, SQLAlchemy
    2.x, Alembic migrations.
-   **Relational DB:** PostgreSQL.
-   **Document DB:** MongoDB.
-   **Graph DB:** Neo4j.
-   **Blockchain:** Solidity smart contract, Hardhat local development
    chain, ethers.js integration from a dedicated service or
    backend-compatible client.
-   **Analytics:** Python, pandas, scikit-learn. Start with K-Means and
    optionally offer hierarchical clustering if time permits.
-   **Authentication:** Secure password hashing (Argon2 or bcrypt),
    short-lived access tokens, and refresh/session handling appropriate
    for a local capstone.
-   **Testing:** pytest for backend; frontend unit/component tests where
    practical; API integration tests; contract tests with Hardhat.
-   **Local orchestration:** Docker Compose for PostgreSQL, MongoDB,
    Neo4j, and the application services. The Hardhat node can run as a
    documented separate local process or a container.
-   **API documentation:** FastAPI OpenAPI/Swagger.
-   **Charts:** A maintained React charting library for aggregate data
    only.

Pin compatible dependency versions and include lockfiles.

------------------------------------------------------------------------

## 5. System Architecture and Data Ownership

### 5.1 Logical Architecture

``` text
Next.js Web UI
      |
      v
FastAPI: authentication, authorization, validation, orchestration
      |
      +------------------- PostgreSQL (authoritative structured data)
      |
      +------------------- MongoDB (clinical documents)
      |
      +------------------- Neo4j (derived graph projection)
      |
      +------------------- Local EVM chain / Solidity contract
      |
      +------------------- Analytics service (cohorts and aggregates)
```

### 5.2 Source-of-Truth Rules

-   PostgreSQL is authoritative for structured patients, visits,
    diagnoses, prescriptions, medications, lab results, treatment,
    policy, claims, consent metadata, and application users.
-   MongoDB is authoritative for document payloads such as clinical
    notes and diagnostic reports. PostgreSQL stores document metadata
    and references.
-   Neo4j is a **derived projection**, never the sole source of medical
    truth. It must be rebuildable from authorized relational data.
-   The blockchain is an append-only evidence/audit layer for
    commitments and consent/access events. PostgreSQL maintains the
    current operational authorization state and the backend checks it
    before returning data.
-   A blockchain transaction does not, by itself, grant a client direct
    access to any database.

### 5.3 Cross-Store Integration

-   Use stable UUIDs for internal entities.
-   PostgreSQL stores `medical_document_id`, `patient_id`, and
    `visit_id` metadata for each document; MongoDB documents contain
    matching opaque UUID references.
-   Use an explicit graph synchronization service. Add a sync
    status/last-synced timestamp and retry failed projection jobs.
    Provide an admin action to rebuild the graph.
-   Use an outbox/event table or equivalent retryable mechanism for
    important cross-store events so a partial failure is visible and
    recoverable.
-   Do not claim distributed ACID transactions across PostgreSQL,
    MongoDB, Neo4j, and the blockchain. Use explicit workflows,
    idempotency, retries, and compensating actions where needed.

------------------------------------------------------------------------

## 6. Data Model

Use UUID primary keys, foreign keys, constraints, created/updated
timestamps, and appropriate indexes. Use UTC timestamps in storage and
render local time in the UI.

### 6.1 PostgreSQL Tables

Implement at least these tables. Avoid overloading one table with
unrelated fields.

#### Identity and organizations

1.  `app_user`
    -   `id`, `email`, `password_hash`, `role`, `is_active`,
        `created_at`, `updated_at`
2.  `patient`
    -   `id`, `user_id` (nullable for seeded records), `display_code`,
        `date_of_birth` or age band, `sex` only if needed for synthetic
        cohort analysis, `created_at`
    -   Keep direct identifiers out of research views.
3.  `doctor`
    -   `id`, `user_id`, `hospital_id`, `display_name`, `specialty`
4.  `hospital`
    -   `id`, `name`, `region`
5.  `research_organization`
    -   `id`, `name`, `organization_type`
6.  `research_project`
    -   `id`, `organization_id`, `title`, `purpose`, `status`,
        `created_by`, `created_at`

#### Clinical reference and encounter data

7.  `visit`
    -   `id`, `patient_id`, `doctor_id`, `hospital_id`, `visit_at`,
        `visit_type`, `summary_code`
8.  `disease`
    -   `id`, `code`, `name`, `description`
9.  `diagnosis`
    -   `id`, `visit_id`, `disease_id`, `diagnosed_at`, `severity`,
        `status`, `notes_reference` (optional)
10. `medication`
    -   `id`, `code`, `name`, `generic_name`, `drug_class`
11. `prescription`
    -   `id`, `visit_id`, `medication_id`, `start_date`, `end_date`,
        `dose_text`, `frequency_text`, `prescribed_by`
12. `treatment`
    -   `id`, `visit_id`, `treatment_type`, `description_code`,
        `start_date`, `end_date`, `outcome_status`
13. `lab_test`
    -   `id`, `code`, `name`, `unit`, `reference_range_text`
14. `lab_result`
    -   `id`, `visit_id`, `lab_test_id`, `result_value`, `result_text`,
        `measured_at`, `is_abnormal`
15. `side_effect`
    -   `id`, `code`, `name`, `description`
16. `observed_adverse_event`
    -   `id`, `patient_id`, `prescription_id` (nullable),
        `side_effect_id`, `reported_at`, `severity`, `outcome`,
        `evidence_quality`
    -   Store this as a reported/observed event; do not represent it as
        proven causation.

#### Documents and integration

17. `medical_document`
    -   `id`, `patient_id`, `visit_id` (nullable), `document_type`,
        `mongo_document_id`, `storage_status`, `created_at`,
        `created_by`
18. `record_integrity`
    -   `id`, `medical_document_id` or record reference,
        `record_version`, `commitment_hash`, `algorithm`, `verified_at`,
        `verification_status`
    -   Keep salts/secrets and any sensitive mapping off-chain; never
        expose them to researchers.

#### Insurance

19. `insurance_provider`
    -   `id`, `name`, `provider_code`
20. `insurance_policy`
    -   `id`, `patient_id`, `provider_id`, `policy_reference`
        (synthetic), `coverage_type`, `valid_from`, `valid_until`,
        `status`
21. `insurance_claim`
    -   `id`, `policy_id`, `visit_id`, `submitted_at`, `claimed_amount`,
        `approved_amount`, `status`, `review_flag`, `review_reason`
22. `claim_item`
    -   `id`, `claim_id`, `treatment_id` (nullable), `item_code`,
        `description`, `quantity`, `unit_cost`, `line_amount`

#### Consent, access and audit

23. `consent`
    -   `id`, `patient_id`, `requester_project_id`, `purpose`,
        `scope_json`, `access_mode`, `valid_from`, `valid_until`,
        `status`, `granted_at`, `revoked_at`, `chain_tx_hash`
24. `access_request`
    -   `id`, `patient_id`, `requester_project_id`,
        `requested_scope_json`, `purpose`, `status`, `requested_at`,
        `decided_at`
25. `access_event`
    -   `id`, `actor_user_id`, `patient_id` (nullable where
        appropriate), `resource_type`, `resource_reference`, `action`,
        `decision`, `reason_code`, `occurred_at`, `request_id`,
        `chain_tx_hash`
26. `blockchain_event`
    -   `id`, `event_type`, `opaque_reference`, `commitment_hash`,
        `transaction_hash`, `block_number`, `status`, `created_at`
27. `outbox_event`
    -   `id`, `event_type`, `aggregate_id`, `payload_json`, `status`,
        `attempt_count`, `created_at`, `processed_at`

#### Cohort analytics

28. `cohort`
    -   `id`, `name`, `description`, `created_by`,
        `feature_definition_json`, `algorithm`, `created_at`
29. `cohort_membership`
    -   `id`, `cohort_id`, `patient_id`, `cluster_label`, `run_id`,
        `created_at`
30. `analytics_run`
    -   `id`, `run_type`, `parameters_json`, `status`, `started_at`,
        `completed_at`, `summary_json`

You may add junction tables when needed. Prefer explicit relationships
and constraints over storing arrays of relational IDs in JSON.

### 6.2 MongoDB Document Shape

Use a `medical_documents` collection. Example:

``` json
{
  "_id": "document UUID",
  "patient_id": "patient UUID",
  "visit_id": "visit UUID or null",
  "document_type": "clinical_note",
  "title": "Synthetic follow-up note",
  "content": "Synthetic clinical text only",
  "structured_extract": {},
  "created_at": "UTC ISO-8601 timestamp",
  "created_by": "user UUID",
  "version": 1
}
```

Create indexes for `patient_id`, `visit_id`, `document_type`, and
`created_at`. Validate input and enforce authorization in the backend
before reading or returning document content. Never place real personal
data in seed documents.

### 6.3 Neo4j Graph Model

Use nodes such as: - `Patient` (opaque internal UUID or a graph-specific
pseudonymous identifier) - `Disease` - `Medication` - `SideEffect` -
`Treatment` - `Cohort`

Use relationships such as: - `(Patient)-[:HAS_DIAGNOSIS]->(Disease)` -
`(Patient)-[:RECEIVED]->(Medication)` -
`(Medication)-[:OBSERVED_WITH]->(SideEffect)` only when supported by
recorded events or explicitly labelled reference evidence -
`(Disease)-[:CO_OCCURS_WITH]->(Disease)` when computed from a documented
cohort and threshold - `(Patient)-[:MEMBER_OF]->(Cohort)`

Graph data must be derived only from data the user is authorized to
process. Do not expose direct identifiers in Neo4j. Include
provenance/source references and timestamps where useful. Make the graph
rebuildable and ensure a researcher query checks current consent before
any patient-level result is returned.

### 6.4 ER Relationship Rules

-   One patient has many visits.
-   One doctor attends many visits; a visit references one assigned
    doctor and hospital in the MVP.
-   One visit has many diagnoses, prescriptions, lab results, and
    treatments.
-   One diagnosis references one disease; a disease can appear in many
    diagnoses.
-   One prescription references one medication; a medication can appear
    in many prescriptions.
-   One patient can have multiple policies; one policy can have many
    claims.
-   One claim has many claim items.
-   One patient can have many medical documents; a document may be
    linked to one visit.
-   One patient can receive many consent requests and grant/revoke
    consent for multiple research projects over time.
-   One cohort has many cohort-membership rows; a patient may appear in
    multiple cohort runs.
-   Enforce foreign keys, uniqueness constraints, valid status values,
    date checks, and non-negative monetary quantities.

------------------------------------------------------------------------

## 7. Functional Requirements

### FR-01: Authentication

-   Users can sign in and sign out.
-   Passwords are hashed with a suitable password-hashing algorithm.
-   Role and active status are checked server-side.
-   Seeded demo credentials are documented for local demonstration only.
-   Do not include production secrets in source control.

### FR-02: Patient and clinical record management

-   Doctors can create/read/update permitted visits, diagnoses,
    prescriptions, treatments, and lab results.
-   Patients can read only their own permitted records.
-   All changes to sensitive records produce an audit event.
-   Validate all IDs and enforce ownership/assignment checks.

### FR-03: Document management

-   Create synthetic clinical notes and diagnostic reports in MongoDB.
-   Store relational metadata and a reference in PostgreSQL.
-   Show document type, visit association, version, and integrity
    status.
-   Provide safe failure handling if MongoDB is unavailable.

### FR-04: Research access request and consent

-   A researcher creates a project and requests a specific scope for a
    stated purpose.
-   A patient sees the request in their dashboard.
-   A patient can grant consent with a scope and expiry or reject the
    request.
-   A patient can revoke active consent at any time.
-   Expired or revoked consent blocks future protected queries and
    exports.
-   Record grants/rejections/revocations and relevant access events in
    PostgreSQL and emit corresponding blockchain events when the local
    chain is available.
-   If chain submission fails, mark the chain status as pending/failed
    and retry safely; do not falsely display it as confirmed.

### FR-05: Consent-aware data access

-   Define scopes such as aggregate diagnoses, de-identified cohort
    data, medication history, lab summaries, and insurance aggregates.
-   Implement a central authorization service that evaluates actor,
    project, purpose, requested fields, consent status, expiry, and
    revocation.
-   Default research access is aggregate or de-identified; never include
    names, emails, phone numbers, or direct identifiers.
-   Check consent immediately before each protected query/export.
-   Deny by default when authorization is missing, ambiguous, expired,
    or revoked.
-   A previously downloaded dataset cannot be remotely erased;
    communicate this limitation clearly.

### FR-06: Record integrity verification

-   Canonicalize the selected record/version deterministically before
    calculating a cryptographic commitment.
-   Keep actual content, salts, secret keys, and patient mappings
    off-chain.
-   Store the commitment and an opaque reference on-chain; avoid patient
    names, medical details, or directly identifying references.
-   Verification recomputes the commitment for the selected version and
    compares it to the stored value.
-   A modified record must display a mismatch.
-   Explain that hashes provide tamper evidence, not confidentiality or
    proof that the original medical statement was true.
-   Avoid hashing low-entropy medical values alone. Use a random salt or
    keyed commitment, keep its mapping/material off-chain, and document
    the threat model.

### FR-07: Blockchain consent/audit contract

-   Use a local Hardhat chain for the capstone.
-   Implement a Solidity contract that emits events for consent granted,
    consent revoked, access event recorded, and record commitment
    anchored.
-   Store minimal opaque references and cryptographic commitments only.
-   Include tests for valid grant, revoke, expiry handling where
    applicable, event emission, invalid input, and duplicate/idempotent
    operations where relevant.
-   The backend remains the enforcement point for database access;
    smart-contract state is evidence and a source of consent-event
    history, not a direct database firewall.
-   Include a chain health indicator and transaction status in the UI.
-   Provide a documented no-chain development mode only if needed for
    local development; mark events as unanchored and never represent
    them as on-chain confirmations.

### FR-08: Patient cohort analysis

-   Provide selectable feature groups: diagnosis history, medication
    exposure, lab summaries, treatment history, and utilization
    aggregates.
-   Use only data permitted for the current research purpose.
-   Start with K-Means and standardize numeric features. Document
    encoding of categorical/multi-label features and missing-value
    handling.
-   Let users choose a cluster count within validated bounds.
-   Store run parameters, algorithm, timestamp, status, and membership
    results.
-   Display cohort sizes and aggregate summaries, not patient-level
    identities.
-   Label outputs as exploratory patterns, not clinical categories or
    treatment advice.
-   Avoid running clustering on direct identifiers.
-   Make the demo deterministic with a fixed random seed.

### FR-09: Disease--drug graph exploration

-   Provide graph queries for:
    -   diseases that co-occur in synthetic records;
    -   medications prescribed within a disease cohort;
    -   reported side effects associated with medication exposure;
    -   cohort-to-treatment/outcome relationships.
-   Show counts, time-window/filter criteria, and provenance.
-   Distinguish observed association from causation.
-   Gate patient-level traversals and exports through the consent
    authorization service.
-   Display a clear empty state if the graph is not synchronized;
    provide a rebuild/retry operation.

### FR-10: Insurance analytics

-   Show claim history, claimed/approved totals, claim statuses,
    disease-wise expenditure, and utilization aggregates according to
    role permissions.
-   Provide a duplicate/anomaly review queue using explainable rules
    such as same policy/patient, overlapping visit dates, same item
    code, and similar amounts.
-   Flag only for human review; do not automatically label fraud or
    decide claims.
-   Keep medical note contents unavailable to insurance analysts by
    default.
-   Record analyst review decisions and reasons.

### FR-11: Advanced DBMS demonstration

Include a documented SQL showcase with at least: - complex multi-table
joins; - CTEs and subqueries; - aggregate queries and
`GROUP BY/HAVING`; - window functions for chronological patient history
or ranked disease costs; - indexes and before/after query-plan
comparison using `EXPLAIN ANALYZE`; - views for role-appropriate
research and insurance summaries; - transaction demonstration with
rollback on failure; - triggers or explicit service-level auditing, with
the chosen design justified; - foreign-key, uniqueness, check, and
not-null constraints; - a normalization walkthrough through 1NF, 2NF,
and 3NF for a representative initial unnormalized dataset.

### FR-12: Audit trail

-   Log successful and denied access to sensitive records and exports.
-   Capture actor, action, resource type, opaque resource reference,
    timestamp, decision, and reason code.
-   Never log passwords, tokens, encryption keys, full clinical content,
    or raw sensitive payloads.
-   Make audit records append-only through application permissions; show
    chain anchoring status separately.
-   Avoid claiming the PostgreSQL audit table itself is immutable.

### FR-13: Demo data and reset

-   Include a deterministic seed generator with synthetic patients,
    visits, diagnoses, medications, lab results, adverse-event
    observations, policies, claims, consent requests, and documents.
-   Provide a safe reset command for the local demo.
-   Include at least enough linked records to demonstrate meaningful
    joins, graph traversal, cohorting, and claims analysis.
-   Mark all records as synthetic in documentation and the UI.

------------------------------------------------------------------------

## 8. User Interface Requirements

Create a clean, responsive academic-demo interface. Prioritize
correctness and clarity over decorative complexity.

### Pages

1.  **Login / Demo Role Selection** --- local demo sign-in; never allow
    production role switching.
2.  **Overview Dashboard** --- role-specific counts and shortcuts.
3.  **Patient Records** --- searchable patient list, record timeline,
    visits, diagnoses, prescriptions, lab results, documents, and
    integrity status.
4.  **Documents** --- document metadata and protected detail view.
5.  **Consent Center** --- patient requests, grant/reject/revoke
    actions, scope, expiry, chain status, and event history.
6.  **Research Projects** --- project creation, purpose, requested
    scope, request status.
7.  **Cohort Explorer** --- configure a clustering run, show cluster
    sizes and aggregate profiles.
8.  **Disease--Drug Graph Explorer** --- filter and inspect connected
    nodes/edges and associated counts.
9.  **Insurance Analytics** --- claims, expenditure summaries,
    utilization, and anomaly review queue.
10. **Audit & Integrity** --- access history, consent events, record
    verification results, transaction references.
11. **Admin / System Health** --- database connectivity, graph sync
    state, blockchain connection, seed/reset controls.

### UI behavior

-   Every button and form must work and show loading, success, empty,
    and error states.
-   Use server-side pagination for lists and validate filters.
-   Do not expose hidden fields or sensitive identifiers in client-side
    data.
-   Clearly label synthetic data, aggregate/de-identified research data,
    pending chain transactions, failed verifications, and exploratory
    analysis.
-   Use confirmation dialogs for consent revocation, record
    modification, and demo reset.
-   Show human-readable error messages without leaking stack traces or
    database internals.
-   Provide a visible explanation when access is denied because consent
    is absent, expired, or revoked.

------------------------------------------------------------------------

## 9. API Requirements

Use REST endpoints under `/api/v1`. Follow consistent response/error
formats and validate all request bodies.

Suggested endpoint groups: - `/auth/*` - `/patients/*` - `/doctors/*` -
`/visits/*` - `/diagnoses/*` - `/diseases/*` - `/medications/*` -
`/prescriptions/*` - `/lab-results/*` - `/treatments/*` -
`/documents/*` - `/research-projects/*` - `/access-requests/*` -
`/consents/*` - `/cohorts/*` - `/graph/*` - `/insurance/policies/*` -
`/insurance/claims/*` - `/analytics/insurance/*` - `/audit/events/*` -
`/integrity/verify/*` - `/blockchain/status` - `/admin/health` -
`/admin/graph/rebuild` - `/admin/demo/reset`

Minimum workflows: 1. Researcher creates a project and submits an access
request. 2. Patient reviews the request and grants scoped consent. 3.
Backend records consent state and anchors the consent event to the local
chain. 4. Researcher runs an allowed aggregate query; backend checks
current consent and records access. 5. Patient revokes consent. 6. The
same protected query is denied and the denial is audited. 7. A user
verifies a medical document commitment; an unchanged record passes and a
modified record fails. 8. An authorized analyst reviews claims and
flagged anomalies. 9. An administrator rebuilds the graph projection and
sees sync status.

Document request/response examples and authorization rules in
`docs/API.md`.

------------------------------------------------------------------------

## 10. Non-Functional Requirements

### Security and privacy

-   Deny by default and enforce authorization on the backend.
-   Hash passwords using Argon2 or bcrypt.
-   Validate input and use parameterized database access.
-   Protect secrets through environment variables; commit only
    `.env.example`.
-   Do not log tokens, passwords, encryption keys, or clinical document
    bodies.
-   Use synthetic data only.
-   Do not place PII, clinical text, diagnosis, medication, or direct
    patient IDs on-chain.
-   Use opaque random references and privacy-aware cryptographic
    commitments.
-   Restrict CORS to the local frontend origin by default.
-   Apply rate limits to login and sensitive export endpoints where
    practical.
-   Clearly document that local demo controls are not a production
    security certification.

### Reliability

-   Provide database health checks, retryable sync jobs, useful logs,
    and explicit partial-failure states.
-   Ensure repeated event processing is idempotent.
-   Do not report an event as on-chain until a successful transaction
    receipt is verified.
-   Make graph projections rebuildable.
-   Provide migrations and seed/reset scripts.

### Performance

-   Use pagination for record lists.
-   Add indexes based on query patterns and demonstrate their effect.
-   Avoid loading all patient records into the browser.
-   Use aggregate queries and only return authorized fields.
-   Establish and document practical demo performance targets; do not
    invent benchmark claims.

### Accessibility and usability

-   Responsive layout and keyboard-accessible controls.
-   Clear labels, validation messages, loading states, empty states, and
    error states.
-   Charts must include readable labels and aggregate values.

------------------------------------------------------------------------

## 11. Hardware and Software Requirements

### Minimum development hardware

-   8 GB RAM recommended as a minimum for a constrained local setup; 16
    GB preferred because PostgreSQL, MongoDB, Neo4j, the frontend,
    backend, and a local blockchain may run concurrently.
-   Modern multi-core CPU.
-   Approximately 10 GB free disk space for dependencies, containers,
    and seed data.
-   GPU not required.

### Software

-   Supported Node.js LTS and package manager.
-   Python 3.11 or another version compatible with pinned dependencies.
-   Docker Engine/Desktop and Docker Compose.
-   Solidity compiler and Hardhat versions pinned in the project.
-   Git and a modern browser.

The setup guide must state tested versions and include troubleshooting
for ports, Docker memory, and unavailable services.

------------------------------------------------------------------------

## 12. Testing and Acceptance Criteria

The project is not complete until all of the following are demonstrated.

### Database

-   Migrations create the schema from an empty database.
-   Seed command produces deterministic synthetic records.
-   Foreign keys and constraints reject invalid data.
-   Transaction rollback leaves no partial claim or clinical update.
-   SQL showcase queries return documented results.
-   Index demonstration includes actual `EXPLAIN ANALYZE` output.

### Access and consent

-   A patient can view their own records but cannot access another
    patient's records.
-   A researcher without consent is denied.
-   A researcher with valid consent can run only the permitted
    query/scope.
-   Expired or revoked consent blocks subsequent requests and exports.
-   An insurance analyst cannot access protected clinical notes by
    changing a URL or API parameter.
-   Successful and denied sensitive access attempts are audited.

### Blockchain and integrity

-   Contract tests pass on the local Hardhat chain.
-   Grant/revoke/access/commitment events appear with transaction
    references.
-   The application distinguishes confirmed, pending, failed, and
    unanchored events.
-   An unchanged record passes verification.
-   A modified record fails verification.
-   No raw patient information appears in contract storage, events, or
    transaction arguments.
-   Backend access remains denied when consent is absent even if a
    client tries to bypass the UI.

### NoSQL and graph

-   A document can be created in MongoDB and linked to a relational
    patient/visit.
-   Missing MongoDB or graph connectivity is reported clearly.
-   Graph synchronization can be retried and rebuilt.
-   Graph results agree with the authoritative seeded relational data
    for defined test cases.
-   Graph access and patient-level research results are consent-checked.

### Analytics and insurance

-   Clustering runs on synthetic, non-identifying features and stores
    run metadata/membership.
-   Repeated runs with the same seed and parameters produce reproducible
    results within the documented environment.
-   Graph and cohort results are labelled exploratory.
-   Insurance summaries calculate totals correctly for the seeded
    dataset.
-   Duplicate/anomaly rules flag examples for review without
    automatically declaring fraud.

### Product quality

-   All major pages work with real API data.
-   No core button is inert.
-   Backend and contract tests pass.
-   Frontend builds successfully.
-   `docker compose up` plus documented commands starts the local demo.
-   A new developer can follow the README from a clean checkout.

------------------------------------------------------------------------

## 13. Phased Implementation Plan

### Phase 0 --- Repository and planning

-   Inspect repository and existing conventions.
-   Write architecture, implementation plan, ERD, and API documentation.
-   Define environment variables and service ports.
-   Acceptance: documented architecture, dependency plan, and runnable
    skeleton.

### Phase 1 --- Foundation and local infrastructure

-   Scaffold frontend and FastAPI backend.
-   Add Docker Compose for PostgreSQL, MongoDB, and Neo4j.
-   Add configuration validation, health endpoints, logging, formatting,
    linting, and tests.
-   Acceptance: services start; health checks report real connectivity;
    frontend reaches backend.

### Phase 2 --- Relational schema and seed data

-   Implement SQLAlchemy models, Alembic migrations, constraints, and
    indexes.
-   Implement deterministic synthetic seed generator.
-   Add representative SQL showcase queries and ERD.
-   Acceptance: fresh migration and seed succeed; schema constraints and
    core queries are tested.

### Phase 3 --- Authentication and role-based access

-   Implement login/session/token handling and password hashing.
-   Implement role/ownership/scope authorization dependencies.
-   Add demo users and role-specific navigation.
-   Acceptance: backend tests prove that cross-role and cross-patient
    access is denied.

### Phase 4 --- Clinical records and MongoDB integration

-   Implement patient, visit, diagnosis, prescription, medication, lab
    result, treatment, and document APIs.
-   Persist document metadata in PostgreSQL and document content in
    MongoDB.
-   Add patient timeline and document UI.
-   Acceptance: a clinical workflow persists data across both stores and
    handles partial failures.

### Phase 5 --- Insurance database and analytics

-   Implement policies, claims, claim items, cost summaries, and review
    flags.
-   Add transactional claim creation and explainable anomaly rules.
-   Add insurance UI and SQL reports.
-   Acceptance: totals are correct; rollback works; analysts cannot
    access restricted clinical documents.

### Phase 6 --- Consent and research workflows

-   Implement research projects, access requests, consent scopes,
    expiry, revocation, and access audit.
-   Implement centralized authorization checks for research queries and
    exports.
-   Add patient Consent Center and researcher project pages.
-   Acceptance: grant permits only the defined scope; expiry/revocation
    blocks future access.

### Phase 7 --- Blockchain contract and record integrity

-   Implement and test the Solidity contract using Hardhat.
-   Add backend blockchain adapter, transaction status tracking,
    commitments, and verification.
-   Keep sensitive data off-chain; add retry/idempotency handling.
-   Acceptance: grant/revoke events can be verified; modified records
    fail verification; chain failure is surfaced honestly.

### Phase 8 --- Neo4j graph intelligence

-   Implement graph projection/synchronization from authorized
    relational records.
-   Add graph queries and graph explorer UI.
-   Add rebuild/retry operations and provenance labels.
-   Acceptance: graph test queries match the seeded reference results
    and unauthorized patient-level queries are denied.

### Phase 9 --- Patient cohort analytics

-   Implement feature extraction, preprocessing, clustering, run
    metadata, membership persistence, and aggregate cohort summaries.
-   Add cohort explorer and reproducibility controls.
-   Acceptance: reproducible synthetic-data run completes and no direct
    identifiers enter the feature matrix.

### Phase 10 --- Audit, integrity and DBMS showcase

-   Complete audit views, record verification interface, SQL showcase,
    query-plan demonstrations, normalization notes, and system-health
    UI.
-   Acceptance: all required DBMS concepts are demonstrated and
    documented.

### Phase 11 --- Hardening, integration and final demo

-   Run all tests; fix integration bugs; test service outages and
    recovery.
-   Add end-to-end smoke tests, screenshots if useful, README, setup
    guide, demo script, known limitations, and troubleshooting.
-   Acceptance: a clean checkout can run the full demo using documented
    commands.

**Do not skip ahead to graph/ML/blockchain before the relational model,
authentication, and consent checks work.**

------------------------------------------------------------------------

## 14. Required Repository Structure

Adapt if a repository already exists, but preserve clear boundaries.

``` text
/
├── apps/
│   └── web/                    # Next.js frontend
├── services/
│   └── api/                    # FastAPI backend
├── contracts/                  # Solidity contracts and Hardhat tests
├── infra/
│   └── docker-compose.yml
├── scripts/
│   ├── seed_demo.py
│   ├── reset_demo.py
│   └── run_sql_showcase.py
├── docs/
│   ├── IMPLEMENTATION_PLAN.md
│   ├── ARCHITECTURE.md
│   ├── ERD.md
│   ├── API.md
│   ├── DBMS_SHOWCASE.md
│   ├── SECURITY_AND_PRIVACY.md
│   └── DEMO_SCRIPT.md
├── .env.example
├── .gitignore
└── README.md
```

------------------------------------------------------------------------

## 15. Environment Variables and Operational Rules

Provide `.env.example` with placeholders for: - PostgreSQL URL - MongoDB
URL/database - Neo4j URI/user/password - authentication secret -
blockchain RPC URL - contract address - demo mode flag - CORS allowed
origin

Never commit actual secrets or local wallet private keys. For local
development, use throwaway Hardhat accounts and synthetic data. Validate
required configuration at startup and explain missing variables clearly.

------------------------------------------------------------------------

## 16. Final Demonstration Scenario

The application must support this complete scenario:

1.  Sign in as a researcher and create a research project seeking
    de-identified records for a defined purpose.
2.  Submit a request for a specific scope.
3.  Sign in as the synthetic patient and inspect the purpose, requested
    data, and expiry.
4.  Grant consent; show the PostgreSQL state and the confirmed
    blockchain transaction/event.
5.  Sign in as the researcher and run an allowed aggregate cohort query.
    Show the result and corresponding audit event.
6.  Revoke consent as the patient.
7.  Retry the same query as the researcher; it must be denied and the
    denial must be logged.
8.  Verify a medical document's integrity, then use a clearly labelled
    demo-only tampering action or test fixture to demonstrate a failed
    verification.
9.  Explore a disease--drug graph and run a reproducible cohort
    analysis.
10. Sign in as an insurance analyst and view disease-wise
    cost/utilization and a flagged claim for human review.
11. Show the SQL showcase, schema/ERD, index plan, and system-health
    page.

The demo should make the project's novelty visible without implying
clinical efficacy or production-grade security.

------------------------------------------------------------------------

## 17. Definition of Done

The project is complete only when: - The entire documented local setup
works from a clean checkout. - PostgreSQL is the authoritative
structured data store and the ERD/schema are documented. - MongoDB
document integration works. - Neo4j graph projection and research
queries work. - Consent grants, scopes, expiry, and revocation are
enforced server-side. - Blockchain events and record commitments are
verifiable on a local development chain. - Patient cohort and insurance
analytics run on synthetic data. - Sensitive information is not written
to the blockchain or leaked through APIs/logs. - Tests cover the key
security, transaction, integration, and analytical workflows. - The UI
has no inert core controls. - README, architecture, ERD, API, DBMS
showcase, security notes, and demo instructions are complete.

**Implementation priority:** correctness and database integrity first;
authorization and consent second; cross-database integration third;
analytics and polished UI after the core workflows pass tests.
