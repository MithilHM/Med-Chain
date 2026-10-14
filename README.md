# MedChain: Privacy-Preserving Healthcare Intelligence & Multi-Model Audit Platform

[![E2E Verification](https://img.shields.io/badge/E2E%20Tests-11%20Passed-brightgreen)](services/api/tests)
[![Smart Contracts](https://img.shields.io/badge/Solidity%20Contracts-8%20Passed-blue)](contracts/test)
[![Frontend Build](https://img.shields.io/badge/Next.js%2014-Compiled%20%E2%9C%93-success)](apps/web)
[![DBMS Showcase](https://img.shields.io/badge/SQL%20Showcase-3NF%20%2B%20CTE%20%2B%20Window%20Functions-orange)](docs/DBMS_SHOWCASE.md)

**MedChain** is a production-grade, privacy-preserving healthcare data intelligence platform. It demonstrates a **hybrid multi-store architecture** integrating authoritative relational persistence, semi-structured clinical document storage, derived graph analytics, unsupervised machine learning cohort discovery, and an immutable Ethereum/Hardhat cryptographic commitment layer.

---

## Architecture Overview

MedChain addresses the tension between clinical data usability, institutional privacy, and tamper evidence through clear separation of concerns:

```
                  +----------------------------------------------+
                  |         MedChain Web Console (Next.js)       |
                  |     Role Switcher: Patient/Doc/Res/Analyst   |
                  +----------------------+-----------------------+
                                         |
                                         v
                  +----------------------------------------------+
                  |      FastAPI Application Gateway & Policies  |
                  |    Centralized Deny-by-Default Consent Engine|
                  +-------+-------------+-------------+----------+
                          |             |             |
        +-----------------+             |             +-----------------+
        |                               |                               |
        v                               v                               v
+---------------+             +-------------------+           +-------------------+
|  PostgreSQL   |             |     MongoDB       |           |   Ethereum / EVM  |
| (Authoritative|             |  (Semi-Structured |           | (Smart Contracts) |
| Relational,   |             |  Clinical Notes   |           | Salted SHA-256    |
| 30 Tables)    |             |  & Discharge Sums)|           | Zero Raw PII/PHI  |
+-------+-------+             +---------+---------+           +---------+---------+
        |                               |                               |
        | Outbox Pattern                | SHA-256 Digest                | Nonce/Block
        v                               v                               v
+---------------+             +-------------------+           +-------------------+
|     Neo4j     |             |  RFC 8785 Canonical|          |   Scikit-Learn    |
| Derived Graph |             | Integrity Service |           | K-Means Cohorting |
| Projection    |             | Tamper Detection  |           | Feature Vectors   |
+---------------+             +-------------------+           +-------------------+
```

### Source-of-Truth Hierarchy
1. **Relational Store (PostgreSQL / SQLite fallback):** Authoritative source of truth for identity, patient demographics, clinical visits, diagnoses, prescriptions, insurance claims, and active consent states.
2. **Document Store (MongoDB / Local JSON fallback):** Rich semi-structured clinical encounter narratives, lab notes, and discharge summaries.
3. **Derived Graph (Neo4j / In-Memory projection):** Synchronized asynchronously via transactional outbox for multi-hop disease co-occurrence and drug-disease interaction queries.
4. **Blockchain Audit Ledger (Solidity / Hardhat):** Append-only cryptographic commitments (salted SHA-256 digests) for access audits and patient consent lifecycle tracking. **Strict zero-PII/raw-data on-chain policy.**

---

## Key Features

- **Centralized Deny-by-Default Consent Engine:** Gated research access control enforcing patient consent scopes (`aggregate_diagnoses`, `medication_history`, `lab_summaries`). Immediate real-time revocation enforcement with zero server restart or cache invalidation delays.
- **Cryptographic Record Integrity:** Deterministic RFC 8785 canonical JSON sorting and salted SHA-256 hashing. Live demonstration of document verification and unauthorized tampering detection.
- **Advanced DBMS Engineering (3NF Schema):** 30 normalized relational tables adhering strictly to First, Second, and Third Normal Forms. Fully documented SQL showcases featuring multi-table joins, recursive Common Table Expressions (CTEs), window functions (`DENSE_RANK`), and `EXPLAIN QUERY PLAN` optimization.
- **Explainable Insurance Fraud Heuristics:** Automated anomaly flagging for overlapping visits, 48-hour duplicate billing, and unbundling, paired with human-in-the-loop analyst adjudication.
- **Unsupervised Patient Cohort Clustering:** Scikit-learn K-Means pipeline generating multidimensional patient risk phenotypes from diagnoses, encounter frequencies, and billing data.
- **Resilient Local Operation:** Built-in self-healing fallbacks allowing full local execution of backend, smart contracts, scripts, and frontend even when external Docker services are offline.

---

## Directory Structure

```
MEDCHAIN/
├── apps/
│   └── web/                   # Next.js 14 App Router Web Application
│       ├── src/app/           # 10 Functional pages (Patients, Documents, Consent, Cohorts, etc.)
│       ├── src/components/    # Glassmorphic UI components, Navbar, Role switcher
│       └── src/lib/api.ts     # Typed API client connecting to backend
├── contracts/
│   ├── contracts/             # MedChainAudit.sol Solidity smart contract
│   ├── test/                  # Hardhat contract test suite (8 tests)
│   └── scripts/               # Contract deployment scripts
├── docs/
│   ├── ARCHITECTURE.md        # System architecture, privacy model & source-of-truth rules
│   ├── IMPLEMENTATION_PLAN.md # 11-Phase execution roadmap matching PRD
│   ├── ERD.md                 # Complete Entity-Relationship schema for all 30 tables
│   ├── API.md                 # OpenAPI REST endpoints and schemas
│   ├── SECURITY_AND_PRIVACY.md# Threat model, commitment math, and cryptographic proofs
│   ├── DBMS_SHOWCASE.md       # 1NF/2NF/3NF normalization, CTEs, and EXPLAIN plans
│   └── DEMO_SCRIPT.md         # Step-by-step 12-stage PRD demo walk-through
├── infra/
│   └── docker-compose.yml     # Multi-store Docker topology (Postgres, Mongo, Neo4j, Hardhat)
├── scripts/
│   ├── seed_demo.py           # Deterministic demo generator across all stores
│   ├── reset_demo.py          # Complete multi-store drop and reseed script
│   └── run_sql_showcase.py    # Executes advanced DBMS analytics and EXPLAIN plans
└── services/
    └── api/                   # FastAPI Backend Gateway
        ├── src/
        │   ├── main.py        # Application entrypoint & route registration
        │   ├── database.py    # SQLAlchemy async engine & fallback logic
        │   ├── models/        # 30 SQLAlchemy relational models
        │   ├── routers/       # 13 REST API routers under /api/v1
        │   ├── schemas/       # Pydantic v2 validation schemas
        │   └── services/      # Business logic: Consent, Integrity, ML, Anomaly, Graph
        └── tests/             # Pytest integration and E2E scenario suite (11 tests)
```

---

## Quickstart Guide

### Prerequisites
- **Python 3.11+**
- **Node.js 18+ & npm**
- *(Optional)* Docker Engine (if running containerized databases)

---

### 1. Smart Contract Suite

```bash
cd contracts
npm install
npm test
```
*Expected output: All 8 contract tests passing.*

---

### 2. Backend Gateway & Database Initialization

```bash
cd services/api

# Create and activate virtual environment
python -m venv .venv
# Windows:
.venv\Scripts\activate
# Linux/macOS:
# source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Seed deterministic demo data across all stores
python ../../scripts/seed_demo.py

# Run backend server
uvicorn src.main:app --host 127.0.0.1 --port 8000 --reload
```
*Backend API docs are now available at: `http://localhost:8000/docs`.*

---

### 3. Frontend Web Console

```bash
cd apps/web
npm install
npm run dev
```
*Frontend Web Console is now live at: `http://localhost:3000`.*

---

## Running the Verification Test Suites

### Complete Backend & E2E Integration Suite
```bash
cd services/api
.venv\Scripts\pytest -v
```
*Runs all 11 test suites including `test_e2e_prd_scenario.py` verifying the full 12-step narrative.*

### Advanced SQL & DBMS Showcase
```bash
cd services/api
.venv\Scripts\python ../../scripts/run_sql_showcase.py
```
*Executes 5 complex queries demonstrating 3NF joins, recursive CTEs, and `EXPLAIN QUERY PLAN`.*

### Frontend Production Build Test
```bash
cd apps/web
npm run build
```
*Verifies 0 TypeScript errors and generates all 14 static route pages.*

---

## Demo Personas & Pre-Seeded Accounts

All seeded demo accounts share the password: **`Password123!`**

| Persona | Email / Login | Role | Demonstrates |
| :--- | :--- | :--- | :--- |
| **System Admin** | `admin@medchain.local` | `admin` | Infrastructure health, graph rebuild, store reset |
| **Primary Patient** | `patient@medchain.local` | `patient` | Access request approval, real-time revocation |
| **Attending Doctor**| `doctor@medchain.local` | `doctor` | Longitudinal encounter timeline, note entry |
| **Research Scientist**| `researcher@medchain.local`| `researcher`| Consent-gated queries, K-Means cohorting |
| **Insurance Analyst**| `analyst@medchain.local` | `insurance_analyst`| Transactional claim rollback, fraud queue |

*You can switch roles instantly in the UI using the header role switcher without logging out.*

---

## Detailed Documentation Links

- [System Architecture & Privacy Model](docs/ARCHITECTURE.md)
- [Implementation Plan & Phase Roadmap](docs/IMPLEMENTATION_PLAN.md)
- [Complete Entity-Relationship Schema (ERD)](docs/ERD.md)
- [API Reference & OpenAPI Specifications](docs/API.md)
- [Cryptographic Security & Threat Model](docs/SECURITY_AND_PRIVACY.md)
- [DBMS Normalization & Query Optimization Showcase](docs/DBMS_SHOWCASE.md)
- [12-Step Evaluation Demonstration Script](docs/DEMO_SCRIPT.md)

---

## Compliance & Privacy Standards

- **HIPAA Minimum Necessary Standard:** Direct identifiers are stripped from research queries. Only consented, de-identified aggregate vectors are accessible.
- **GDPR Article 17 (Right to Erasure / Revocation):** When a patient revokes consent, access is cut off immediately at the centralized policy engine.
- **Off-Chain Confidentiality:** No PHI, names, or cleartext notes are ever committed to the blockchain. All ledger anchors consist of salted SHA-256 cryptographic commitments.
