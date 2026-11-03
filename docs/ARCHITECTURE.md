# MedChain System Architecture Documentation

## 1. Executive Summary & Core Principles
MedChain is an enterprise-grade academic demonstration platform designed to showcase multi-model database engineering, privacy-preserving research query engines, and tamper-evident auditability using distributed ledger principles.

### Key Architectural Principles:
1. **Clear Source-of-Truth Hierarchy:** Relational data in PostgreSQL is authoritative. Document and graph stores are specialized functional projections.
2. **Off-Chain Clinical Records:** Raw patient identifiers, clinical text, and diagnosis details stay off-chain. Blockchain calls use opaque hashes of internal references and salted document commitments; those hashes should still be treated as sensitive metadata.
3. **Defense-in-Depth Authorization:** Hiding a UI button is not security. Every request is independently authorized by a central policy engine verifying actor role, explicit ownership, active patient consent, and expiration timestamps.
4. **Explicit Store Degradation:** Development and test can use encrypted local document and in-memory graph fallbacks. Production document operations require MongoDB. Blockchain writes are best-effort inline calls, and graph data is rebuilt by an admin action; a transactional outbox worker is not yet implemented.

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
                 |  | (Argon2 / JWT)     |  | (Deny-by-default rules)   |  |
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
- The commitment hash is recorded in PostgreSQL's `record_integrity` table, then submitted to the blockchain inline on a best-effort basis. The result is recorded as confirmed, failed, or unanchored.

### 4.2 Cross-Store Synchronization Status
- The schema includes an `outbox_event` table, but current routes do not write to it and no outbox processor runs. It does not yet provide retry or eventual-delivery guarantees.
- Consent and access events are submitted to Hardhat inline, with database state remaining authoritative. Blockchain outages therefore leave events unanchored or failed until a retry mechanism is implemented.
- Neo4j is rebuilt from relational records by an admin endpoint. There is no automatic graph projection after each relational change.

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
