# Production Readiness for Hospital Use

## Current status

The code-level controls for a single-hospital pilot are implemented and tested. The remaining gates require the hospital itself: validation against its systems, infrastructure, and institutional approval. Until every gate below is closed, connect MedChain only to a hospital **test** environment and test interface feed, and do not load real patient data.

Legend: ✅ implemented and tested in this repository · 🏥 requires the hospital or infrastructure (cannot be closed by code alone)

## Gates

| Gate | Status | Notes |
| --- | --- | --- |
| Deployment boundary | ✅ / 🏥 | Decision: one installation per hospital. `HOSPITAL_FACILITY_CODES` rejects data for other facilities. Multi-hospital tenancy is out of scope. The hospital confirms the facility codes. |
| Schema lifecycle | ✅ | Baseline regenerated from models; migrations `002` and `003`; CI upgrades, drift-checks, downgrades, and re-upgrades on PostgreSQL. |
| Durable cross-store evidence | ✅ | Transactional outbox, idempotent dispatch, backoff, single-sender election, alerting on failures and backlog. Verified against a live chain in CI. |
| Consent revocation vs. data use | ✅ | `FOR SHARE` / `FOR UPDATE` serialization, proven by a two-connection PostgreSQL test in CI. |
| Identity | ✅ / 🏥 | OIDC SSO (PKCE, JWKS, nonce, role mapping), SCIM provisioning and deprovisioning, TOTP MFA with recovery codes, fail-closed sessions, lockout, database-backed rate limiting. 🏥 Register the app in the hospital IdP, map groups, and connect SCIM. |
| Clinical access model | ✅ / 🏥 | Care-team assignments from ADT/FHIR/onboarding, which end after discharge (`CARE_TEAM_POST_DISCHARGE_DAYS`); break-the-glass with review. 🏥 Clinical governance sets the window lengths. |
| Patient identity | ✅ / 🏥 | Identifier-only matching, conflict review, encrypted names with blind-index search, approval-gated merges (`A40`). 🏥 Probabilistic or EMPI matching uses the hospital EMPI identifier. |
| Interface | ✅ / 🏥 | HL7 v2 `A01/A02/A03/A04/A08/A11/A13/A40`, `ORU^R01`; FHIR R4 import/export. 🏥 Agree the interface spec, register facilities and providers, and run the hospital's test feed end to end. |
| Data protection | ✅ / 🏥 | Field and document encryption with a key ring and rotation job; no PHI in the graph, ledger, alerts, metrics, or events. 🏥 TLS everywhere, encrypted volumes and backups, a secrets manager, least-privilege database accounts. |
| Ledger network | 🏥 | Production chain handling is implemented (secret-file key, EIP-1559, gas estimation, confirmations, writer rotation). 🏥 Stand up a permissioned network (e.g. Besu QBFT) and an HSM-backed signer. |
| Operations | ✅ / 🏥 | Prometheus metrics, webhook alerting, an Operations console, and a runbook ([OPERATIONS.md](OPERATIONS.md)). 🏥 Wire alerts to on-call; load-test at peak message rate; run failure drills (DB, Mongo, chain, MLLP). |
| Recovery | 🏥 | `GET /admin/disaster-recovery` reports `NOT_VERIFIED` until infrastructure provides evidence. Record a dated restore drill. |
| Institutional review | 🏥 | Privacy, security, legal, clinical-safety, and procurement approvals for the jurisdiction (e.g. HIPAA, GDPR, DPDP Act). Independent penetration test. |

## Explicitly out of scope

MedChain is not an EHR, does not provide clinical decision support, and does not replace the hospital's identity, ordering, laboratory, pharmacy, billing, or medical-record systems. Critical-result flags in the live feed mirror the lab's `HH`/`LL`/`AA` flags; they are not a validated alerting system and do not replace the hospital's critical-result notification process. Blockchain anchoring is tamper-evidence for audit, not a substitute for the authoritative database, access controls, or the institutional audit process.
