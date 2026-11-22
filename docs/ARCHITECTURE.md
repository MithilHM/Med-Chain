# MedChain System Architecture Documentation

## 1. Executive Summary & Core Principles
MedChain is an enterprise-grade academic demonstration platform designed to showcase multi-model database engineering, privacy-preserving research query engines, and tamper-evident auditability using distributed ledger principles.

### Key Architectural Principles:
1. **Clear Source-of-Truth Hierarchy:** Relational data in PostgreSQL is authoritative. Document and graph stores are specialized functional projections.
2. **Off-Chain Clinical Records:** Raw patient identifiers, clinical text, and diagnosis details stay off-chain. On-chain references are keyed pseudonyms (HMAC-SHA256 with `CHAIN_PSEUDONYM_KEY`), so holding an internal UUID is not enough to find its on-chain events; document commitments are salted. Treat the pseudonyms as sensitive metadata and keep the key stable and backed up.
3. **Defense-in-Depth Authorization:** Hiding a UI button is not security. Every request is independently authorized by a central policy engine verifying actor role, explicit ownership, active patient consent, and expiration timestamps.
4. **Explicit Store Degradation:** Development and test can use encrypted local document and in-memory graph fallbacks. Production document operations require MongoDB and return HTTP 503 when it is unavailable. Blockchain evidence is written to a transactional outbox in the same database transaction as the authoritative change and delivered by a background worker with retries; graph data is rebuilt by an admin action.
5. **Conservative Clinical Ingestion:** Real-time HL7 v2 and FHIR feeds match patients only on exact assigning-authority identifiers. Conflicts, unknown providers, and unknown facilities go to a human review queue; demographics and timestamps are never invented.

---

## 2. Logical Architecture

```
                                +-----------------------------+
                                |      Next.js Web UI         |
                                | (TypeScript + Tailwind CSS) |
                                +--------------+--------------+
                                               |
                                        HTTP / REST / JWT
                                               v
                 +---------------------------------------------------------+
                 |                 FastAPI Application Gateway             |
                 |                                                         |
                 |  +--------------------+  +---------------------------+  |
                 |  | Security & Auth    |  | Consent Policy Engine     |  |
                 |  | (bcrypt / JWT)     |  | (Deny-by-default rules)   |  |
                 |  +--------------------+  +---------------------------+  |
                 |  | Audit Interceptor  |  | Outbox Dispatcher         |  |
                 |  +--------------------+  +---------------------------+  |
                 +----+---------------+--------------+----------------+----+
                      |               |              |                |
             SQLAlchemy 2.x      Motor/Pymongo   Neo4j Bolt       Web3 / JSON-RPC
                      v               v              v                v
         +----------------+   +------------+   +-----------+   +---------------+
         |   PostgreSQL   |   |  MongoDB   |   |   Neo4j   |   | Local Hardhat |
         | (Authoritative |   | (Clinical  |   |  (Derived |   |  EVM Network  |
         |  Relational)   |   | Documents) |   |   Graph)  |   | (Audit Trails)|
         +----------------+   +------------+   +-----------+   +---------------+
                 ^                                   ^
                 |------- Graph Sync Worker ---------|
```

---

## 3. Data Store Responsibilities & Source-of-Truth Rules

| Data Store | Role | Scope of Data Stored | Mutability & Lifecycle |
| :--- | :--- | :--- | :--- |
| **PostgreSQL** | Authoritative Core | Users, Patients, Doctors, Visits, Diagnoses, Medications, Prescriptions, Lab Tests/Results, Insurance Policies/Claims, Consents, Audit Events, Outbox. | ACID Relational; Primary Source of Truth. |
| **MongoDB** | Semi-Structured Document Store | Rich clinical notes, diagnostic narrative summaries, unstructured radiology/pathology extracts. | Append / Versioned Document Store; Referenced by `medical_document.mongo_document_id`. |
| **Neo4j** | Derived Graph Projection | Knowledge graph nodes: `Patient` (pseudonymous), `Disease`, `Medication`, `SideEffect`, `Cohort`. Edges: `HAS_DIAGNOSIS`, `RECEIVED`, `OBSERVED_WITH`, `CO_OCCURS_WITH`. | 100% Rebuildable from PostgreSQL; Never a primary source of truth. |
| **Solidity / Hardhat EVM** | Tamper-Evident Evidence Layer | Opaque event commitments: `ConsentGranted`, `ConsentRevoked`, `AccessLogged`, `RecordAnchored`. | Append-only public ledger; contains zero readable health data. |

---

## 4. Cross-Store Integration & Reliability Patterns

### 4.1 Document Linking & Integrity Architecture
- When a doctor creates a clinical document, the raw clinical narrative is written to MongoDB's `medical_documents` collection (or the encrypted local fallback in development and test), returning an opaque UUID `_id`.
- A relational metadata record is created in PostgreSQL's `medical_document` table containing `patient_id`, `visit_id`, `document_type`, and `mongo_document_id`.
- Simultaneously, a canonical deterministic JSON serialization of the document is generated:
  $$\text{Commitment} = \text{SHA256}(\text{CanonicalJSON} + \text{OffChainSalt})$$
- The commitment hash is recorded in PostgreSQL's `record_integrity` table together with a `PENDING` `blockchain_event` row and an outbox event, all in one transaction. The outbox worker anchors it and marks the row `CONFIRMED` with its transaction hash.
- Amendments create a new version: the prior payload is preserved as an immutable encrypted snapshot, and the new commitment is anchored with a higher version number. The contract rejects equal or lower versions, so anchored history cannot be overwritten or rolled back.

### 4.2 Transactional Outbox (cross-store delivery)
- Producers (consent grant/revoke, access decisions, document commitments, inbound-message provenance) call `OutboxService.enqueue` inside the transaction that changes authoritative state. If that transaction rolls back, no evidence is emitted; if it commits, the evidence is never lost.
- `OutboxWorker` runs in the API process (`OUTBOX_WORKER_ENABLED`). It claims due events with `SELECT ... FOR UPDATE SKIP LOCKED`, releases claims left by crashed workers, retries with exponential backoff (5 s up to 1 h), and marks events `FAILED` after `OUTBOX_MAX_RETRIES` or on a permanent contract rejection. On PostgreSQL an advisory lock makes one replica the single chain sender, so nonces never collide.
- Dispatch is idempotent: before sending, the worker reads on-chain state (existing commitment/version, consent status). Re-delivery of an already-applied event is a no-op success. A revocation whose grant is not yet anchored waits for it.
- Operators see counts, the oldest undelivered event, and per-event errors at `GET /admin/outbox/events`, and can requeue failures with `POST /admin/outbox/retry-failed`.
- Neo4j is rebuilt from relational records by an admin endpoint. There is no automatic graph projection after each relational change.

### 4.2a Consent Revocation Serialization
- A granted research authorization reads the consent rows `FOR SHARE` and keeps the transaction open while the protected query runs; the router commits afterwards.
- Revocation reads the consent row `FOR UPDATE`, so it waits for in-flight authorized queries to finish, and every query that starts afterwards sees the revocation. (SQLite, used only for development, ignores row locks.)

### 4.2b Real-time Clinical Integration
```
Hospital ADT / LIS ──► Interface engine (Mirth, Rhapsody, Cloverleaf)
                          │  HL7 v2 over MLLP (TLS/mTLS)  or  HTTPS + X-Integration-Key
                          ▼
               MLLP listener / POST /integration/hl7v2
                          │  inbound_message ledger (encrypted raw, unique per source + MSH-10)
                          ▼
               Patient matching ──(conflict / unknown provider)──► NEEDS_REVIEW queue
                          │
                          ▼
        Visits, care-team assignments, lab results  ──► outbox: provenance anchor
                          │ (after commit)
                          ▼
               Event bus ──► GET /events/stream (SSE) ──► care-team dashboards
```
- Supported: `ADT^A01/A04/A08/A03`, `ORU^R01` (numeric results). See [INTEGRATION.md](INTEGRATION.md).
- Real-time events carry identifiers and flags only (for example `critical: true` for HH/LL results). Subscribers receive only events for patients they may access; the stream re-checks the session every 30 seconds and closes when it is revoked or expires.
- On PostgreSQL, every process (API replicas and the MLLP listener) publishes with `NOTIFY` and receives with `LISTEN`, so results ingested anywhere reach dashboards on every replica. While the relay connection is down, delivery falls back to in-process.

### 4.2c Identity and Operations
- Staff authenticate through hospital OIDC SSO; SCIM keeps accounts in step with the directory. Local accounts (patients, break-glass admin) use passwords plus TOTP.
- A monitor evaluates outbox, integration, compliance, and store health, records alert transitions in `operational_alert`, and posts them to a webhook. `/metrics` exposes the same counts to Prometheus. On PostgreSQL an advisory lock makes one replica evaluate and notify.
- Encryption uses a key ring with key IDs in every ciphertext; rotation re-encrypts documents, raw HL7, names, and MFA secrets.

### 4.3a Graph Rebuild Safety
- Each rebuild writes a complete new generation beside the live one, then one write transaction points `ProjectionMeta` at it and removes older generations. Readers filter by the current generation, so a failed rebuild is invisible and the previous projection stays live.
- Patient nodes carry a keyed pseudonym and sex only.

### 4.3 Graph Synchronization Engine
- Neo4j projections represent aggregate disease-drug-side-effect relationships.
- The synchronization service queries committed clinical data from PostgreSQL and merges nodes and relationships into Neo4j using idempotent Cypher queries (`MERGE`).
- An administrative endpoint `/api/v1/admin/graph/rebuild` drops all graph nodes and repopulates the entire projection from authoritative relational records.

---

## 5. Security & Privacy Architecture

### 5.1 Centralized Consent Policy Engine
All research data queries pass through a centralized policy evaluator:
```
Request(actor, project_id, requested_scope, requested_fields)
  │
  ├─> 1. Is actor active and role == "researcher"?
  ├─> 2. Does an active Consent grant exist for project_id?
  ├─> 3. Is current_time < consent.valid_until and consent.revoked_at is NULL?
  ├─> 4. Does requested_scope match granted scope_json?
  ├─> 5. Filter out all direct identifiers (names, emails, dates of birth).
  └─> Return de-identified dataset OR raise HTTP 403 (Logged to access_event).
```

### 5.2 Off-Chain Privacy Model
- **No Direct Identifiers On-Chain:** Hashes committed to Ethereum smart contracts use opaque UUIDs and salt values stored strictly in PostgreSQL.
- **De-Identification Strategy:** Research cohorts use synthetic demographic bands (e.g. age range 40-50, synthetic sex) without names, government identifiers, or contact details.

---

## 6. Local Development & Operational Fallbacks
MedChain is built to be resilient in local environments:
- **Docker Compose:** Spawns PostgreSQL (port 5432), MongoDB (port 27017), Neo4j (port 7474/7687), and API service.
- **No-Chain Fallback Mode:** If the local Hardhat node is not running, blockchain calls record transactions with an `unanchored` or `pending` status rather than crashing, with full UI notification to the user.
- **Database Graceful Fallbacks:** The API features integrated health probes that report degraded status clearly across the UI without application crashes.
