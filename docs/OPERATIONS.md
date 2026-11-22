# Operations Runbook

For the hospital IT, security, and integration teams running a MedChain installation. MedChain is deployed **one installation per hospital** (or per health system that shares one patient-identity domain). `HOSPITAL_FACILITY_CODES` enforces that boundary: messages and bundles for any other facility are rejected.

## 1. First start

1. Provision PostgreSQL, MongoDB, Neo4j, and the ledger node on a private network with TLS and encrypted volumes. Put every secret below in the hospital secrets manager, not in files on disk.
2. Generate secrets:
   ```bash
   python -c "import secrets;print(secrets.token_hex(32))"        # DOCUMENT_ENCRYPTION_KEYS value, CHAIN_PSEUDONYM_KEY
   python -c "import secrets;print(secrets.token_urlsafe(48))"    # SECRET_KEY
   ```
   Set `DOCUMENT_ENCRYPTION_KEYS=k1:<hex>` and `DOCUMENT_ENCRYPTION_ACTIVE_KEY_ID=k1`. **Back up the encryption key and `CHAIN_PSEUDONYM_KEY` separately from the database**: losing the first makes clinical documents, raw HL7, names, and MFA secrets unreadable, and losing the second breaks lookups of on-chain evidence.
3. `ENVIRONMENT=production`, `DEMO_MODE=false`. The API refuses to start with development keys, weak database passwords, non-HTTPS CORS origins, the Hardhat chain, or without SSO or admin MFA.
4. Migrate, then start: `alembic upgrade head`, then start the API, then (optionally) the MLLP listener (`python -m src.integration.mllp_server`).
5. Create the local break-glass administrator: `python scripts/bootstrap_admin.py it-admin@hospital.org`. It prints a password, an authenticator enrollment URI, and recovery codes **once**; store them in the privileged-access vault. Everyday staff use SSO.
6. Register reference data: each `hospital.facility_code` and each doctor's `external_provider_id` (NPI or staff number) used in the HL7/FHIR feeds.

## 2. Single sign-on and provisioning

**OIDC (Entra ID, Okta, Keycloak, Ping):** register MedChain as a confidential web app with redirect URI `https://<host>/api/v1/auth/oidc/callback`, scopes `openid email profile`, and a groups claim. Then set:

```
OIDC_ENABLED=true
OIDC_ISSUER=https://login.example-idp.com/<tenant>/v2.0
OIDC_CLIENT_ID=...
OIDC_CLIENT_SECRET=...
OIDC_REDIRECT_URI=https://<host>/api/v1/auth/oidc/callback
OIDC_ROLE_CLAIM=groups
OIDC_ROLE_MAP=MedChain-Admins:admin,MedChain-Doctors:doctor,MedChain-Research:researcher,MedChain-Billing:insurance_analyst
OIDC_REQUIRE_MFA_CLAIM=true      # if the IdP reports amr=["mfa"]
```

The first matching group in `OIDC_ROLE_MAP` wins, and the directory is authoritative: a changed group changes the role at the next sign-in. Users without a mapped group are refused.

**SCIM (deprovisioning):** point the identity provider's SCIM connector at `https://<host>/api/v1/scim/v2` with a bearer token, and set `SCIM_BEARER_TOKEN_HASH` to its SHA-256. Disabling or deleting a user in the directory deactivates the MedChain account and revokes its sessions immediately; open real-time streams close within 30 seconds. Accounts are never hard-deleted, so the audit trail stays complete.

**Local accounts** (patients, break-glass admin) use passwords and TOTP. `MFA_REQUIRED_ROLES` lists roles that cannot sign in without MFA. Sign-in is rate-limited per client address across all replicas (`LOGIN_RATE_LIMIT_PER_MINUTE`) and accounts lock after `LOGIN_MAX_FAILED_ATTEMPTS`.

## 3. Monitoring and alerting

- `GET /metrics` serves Prometheus metrics. Scrape it with `Authorization: Bearer <token>` (store the SHA-256 in `METRICS_BEARER_TOKEN_HASH`). The metrics are counts only, with no patient data.
- The built-in monitor (`MONITOR_ENABLED`) evaluates conditions every `MONITOR_INTERVAL_SECONDS` and posts open/resolve transitions to `ALERT_WEBHOOK_URL` (a Teams, Slack, or incident-tool webhook). Alerts are also listed at `GET /admin/alerts` and on the **Operations** page.

| Alert | Severity | Action |
| --- | --- | --- |
| `outbox.failed` | critical | Audit evidence was refused by the ledger. Read `last_error` at `GET /admin/outbox/events?status=FAILED`, fix the cause, then `POST /admin/outbox/retry-failed`. |
| `outbox.backlog` | warning | Evidence is older than `OUTBOX_ALERT_AGE_SECONDS`. Check ledger node health and the signing account balance (if gas is not zero). |
| `integration.feed_silent` | critical | No HL7 within `INTEGRATION_SILENCE_ALERT_MINUTES`. Check the interface engine channel and the MLLP listener. |
| `integration.review_backlog` | warning | Messages need a human decision (Operations → review queue). Fix the mapping, then **Reprocess**. |
| `integration.merge_pending` | info | ADT^A40 merges await a second administrator's approval. |
| `compliance.break_glass_overdue` | warning | Emergency access not reviewed within `BREAK_GLASS_REVIEW_SLA_HOURS`. |
| `store.documents_down` | critical | MongoDB is unreachable; document requests return 503. |
| `graph.unhealthy` | warning | Graph sync failed, is stale, or Neo4j is unreachable. The previous projection stays live; run `POST /admin/graph/rebuild` after fixing. |

## 4. Encryption key rotation

1. Add a new key: `DOCUMENT_ENCRYPTION_KEYS=k1:<old>,k2:<new>` and set `DOCUMENT_ENCRYPTION_ACTIVE_KEY_ID=k2`, then restart. New writes use `k2`; old data still decrypts with `k1`.
2. Back up, then run `python scripts/rotate_encryption_key.py`. It re-encrypts MongoDB documents, raw HL7 messages, patient names, and MFA secrets, and is safe to re-run.
3. Confirm with `python scripts/rotate_encryption_key.py --status` (or `GET /admin/encryption/status`) that nothing remains under `k1`.
4. Remove `k1` from the ring and restart. Keep the retired key in escrow until old backups expire.

Do not rotate `CHAIN_PSEUDONYM_KEY`: on-chain references are derived from it.

## 5. Ledger network

Hardhat is for development only. For a pilot, run a permissioned EVM network operated by the hospital or consortium, for example Hyperledger Besu with QBFT and at least four validators. Then:

- Deploy `MedChainAudit` once, and set `CONTRACT_ADDRESS` and `BLOCKCHAIN_CHAIN_ID`.
- Load the signing key from a mounted secret (`BLOCKCHAIN_PRIVATE_KEY_FILE`), ideally backed by an HSM or KMS-signing proxy.
- Set `BLOCKCHAIN_CONFIRMATIONS` to your finality policy. QBFT is final at 1; probabilistic networks need more.
- Rotate the signing key with `setWriter(newKey, true)` from the owner account, switch MedChain to the new key, then call `setWriter(oldKey, false)`.

Each API replica runs the outbox worker. On PostgreSQL an advisory lock makes exactly one replica the sender, so nonces never collide.

## 6. Scaling out

- Run several API replicas behind the load balancer. The outbox, monitor, and rate limiter coordinate through PostgreSQL.
- Real-time events fan out through PostgreSQL `LISTEN/NOTIFY` (`EVENT_BUS_BACKEND=auto`), so dashboards on any replica receive results ingested by the MLLP listener. Proxies in front of `/api/v1/events/stream` must not buffer responses, and need read timeouts of at least 60 seconds (heartbeats are sent every 15 seconds).
- Only one MLLP listener should own a given interface-engine channel. Duplicate deliveries are harmless (they are idempotent on MSH-10), but they add load.

## 7. Routine checks

| Frequency | Check |
| --- | --- |
| Daily | Open alerts; review queue empty or explained; break-glass reviews completed. |
| Weekly | Outbox `FAILED` count is zero; graph rebuilt; sign-in lockouts reviewed for attacks. |
| Quarterly | Restore drill from backup into an isolated environment, then run `/admin/encryption/status` and an integrity verification there; key-escrow check; access recertification against directory groups. |
