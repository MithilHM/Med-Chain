# MedChain Review Backlog

Static source review of the current worktree, 2026-11-03. This records confirmed code gaps and review priorities; it is not a runtime security certification. The application was not started and no tests or builds were run.

## Required fixes

| Priority | Finding | Why it matters | Required fix |
| --- | --- | --- | --- |
| P1 | Consent and blockchain writes do not have durable cross-store delivery. [`consent.py`](../services/api/src/routers/consent.py#L145) calls the chain before the SQL transaction commits; access events and document anchors also submit inline. The [`outbox_event` model](../services/api/src/models/consent.py#L81) has no producer or worker. | A database failure after an on-chain grant/revoke can leave SQL and chain evidence inconsistent. Failed chain events have no durable retry path. | Commit authoritative SQL state and an outbox row atomically, then process chain and graph events with idempotency, retries, and visible terminal status. Preserve immediate database-side revocation. |
| P1 | A research query can race consent revocation. [`consent_engine.py`](../services/api/src/services/consent_engine.py) reads consent, commits its access event, and returns patient IDs before the analytics query runs. A concurrent revocation can complete in that gap. | A query may continue using a consent that was revoked after its initial check. | Make authorization and data selection share a transaction/locking strategy, or revalidate active consent in the same query transaction before returning results. Add a concurrent-revocation acceptance check. |
| P1 | Access tokens are stored in `localStorage` in [`api.ts`](../apps/web/src/lib/api.ts#L76) for the configured default of 1,440 minutes in [`config.py`](../services/api/src/config.py#L24); logout only deletes the browser copy. | XSS can steal a long-lived bearer token; a stolen token remains valid after logout. | Use short-lived access tokens and a revocable refresh/session mechanism. Prefer HttpOnly, Secure, SameSite cookies with CSRF protections for browser sessions; add login rate limiting. |
| P1 | The application starts with `Base.metadata.create_all` in [`database.py`](../services/api/src/database.py#L77); Alembic has configuration but no versioned revisions. | Existing databases do not receive later schema constraints safely, and deployed schema evolution is not reproducible. | Generate and review an initial migration, make startup use migrations, and keep destructive reset out of normal startup. |
| P2 | Neo4j rebuild deletes the live graph before writing the replacement in [`neo4j_sync.py`](../services/api/src/services/neo4j_sync.py#L175). Status now detects failures, but a mid-rebuild failure can leave the live graph partial. Health uses the last recorded state rather than pinging Neo4j on each check. | Queries can encounter partial/stale derived data, and a later outage may remain reported as healthy until a rebuild attempts a write. | Build a versioned staging projection and swap only after success; periodically check connectivity and freshness. Keep the current failure status behavior. |
| P2 | MongoDB unavailability in production raises an unhandled `RuntimeError` in [`mongo.py`](../services/api/src/services/mongo.py). | Requests fail closed but are returned as generic 500 errors instead of a clear 503 store-unavailable response. | Translate the store-unavailable error to HTTP 503 at API boundaries and keep genuine missing-document results as 404. |
| P2 | Web3 calls are synchronous inside async request handlers in [`blockchain.py`](../services/api/src/services/blockchain.py), and transactions use the account's current nonce without cross-request coordination. | RPC waits block the API event loop; concurrent transactions can reuse a nonce or fail unpredictably. | Use an async RPC client or worker, serialize nonce allocation per signing account, and retry safely with idempotent outbox events. |
| P2 | README shows static “11 tests passed”, “8 contracts passed”, and “compiled” badges; the repository has no workflow-backed status source. | The badges can become stale and imply verification that is not tied to the current commit. | Remove static pass-count badges or replace them with real CI status badges after workflows are added. |
| P2 | The existing [`test_e2e_prd_scenario.py`](../services/api/tests/test_e2e_prd_scenario.py#L11) expects detailed store status from the now-minimal public health route. | The security change intentionally changes that response contract; the current acceptance test is stale and would need to check public liveness separately from authenticated admin health. | Update the existing test contract and run it when the Python environment is available. |
| P2 | The documented end-to-end flows have not been verified in this workspace. | Static inspection cannot establish that the API, web app, databases, contract, and seeded workflows work together. | Once a Python runtime and Docker are available, run the documented setup and focused acceptance checks; fix failures and record results. |

## Improvements after required fixes

- Add pagination and query batching to patient timelines and document lists; those handlers still issue per-record lookups and can become slow on larger datasets.
- Add explicit patient onboarding and doctor-patient assignment records if this should support workflows beyond seeded demo patients. Current doctor access is derived from existing visits.
- Add encryption-key identifiers and a rotation/migration procedure; changing `DOCUMENT_ENCRYPTION_KEY` currently makes existing encrypted payloads unreadable.
- Consider an RFC 8785 implementation only if commitments must be reproduced by other languages. The current implementation is sorted-key compact Python JSON and is documented accordingly.
- Harden deployment separately from local demo Compose: bind database, Neo4j, and Hardhat ports to localhost or private networks; use managed secrets/TLS; disable interactive API docs in production; and avoid default credentials.
- Add CI workflows for API checks, frontend builds, smart-contract tests, and migration validation. Keep those checks tied to commit SHAs rather than manually maintained badges.
- Add structured audit retention/export policy and tests for denied access, consent expiry/revocation, small-cell suppression, provider scope, and cross-store failure recovery.

## Already addressed in this worktree

PostgreSQL URL override validation is now implemented: embedded credentials, driver compatibility, and matching async/sync targets are checked at startup.

Blockchain operations now reject mismatched RPC chain IDs, require deployed contract bytecode, and report contract/chain problems as degraded status.

See [CHANGE_CHECKLIST.md](CHANGE_CHECKLIST.md) for the itemized completed change list. Recent fixes include consent-scoped research and small-cell protections, encrypted document payloads, provider scoping, safer production document-store fallback behavior, admin-only infrastructure diagnostics, chain-aware integrity verification, graph rebuild reporting/performance, and safer error responses.
