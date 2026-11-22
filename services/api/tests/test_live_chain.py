"""End-to-end delivery to a real EVM node (Hardhat/Besu) with the MedChainAudit contract deployed.

Runs when LIVE_CHAIN=1 (CI starts `npx hardhat node` and deploys first). Verifies the outbox
anchors evidence, verification confirms against the chain, references are keyed pseudonyms,
versions only increase, and redelivery is idempotent.
"""
import os

import pytest
from sqlalchemy import select
from web3 import Web3

from src import database
from src.models import BlockchainEvent, Consent, OutboxEvent
from src.services import blockchain as chain
from src.services.outbox import OutboxWorker

pytestmark = pytest.mark.skipif(os.environ.get("LIVE_CHAIN") != "1", reason="LIVE_CHAIN=1 not set; live-chain checks skipped.")


async def _drain():
    totals = {"completed": 0, "failed": 0}
    for _ in range(10):
        summary = await OutboxWorker.run_once(limit=500)
        totals["completed"] += summary["completed"]
        totals["failed"] += summary["failed"]
        if summary["claimed"] == 0:
            break
    return totals


@pytest.mark.asyncio
async def test_outbox_delivers_and_verifies_against_live_chain(client):
    chain.reset_client_cache()
    admin = (await client.post("/api/v1/auth/demo-switch?role=admin")).json()
    headers = {"Authorization": f"Bearer {admin['access_token']}"}
    patient = (await client.post("/api/v1/auth/demo-switch?role=patient")).json()
    p_headers = {"Authorization": f"Bearer {patient['access_token']}"}

    assert (await client.get("/api/v1/blockchain/status", headers=headers)).json()["status"] == "connected"
    assert (await _drain())["failed"] == 0  # seeded consents and anchors

    doc_id = (await client.post("/api/v1/documents", headers=headers, json={
        "patient_id": "PT-100201", "document_type": "Progress Note", "title": "Live chain",
        "content": "BP 132/84. Continue metformin 500mg BID."})).json()["id"]
    await _drain()
    verify = (await client.get(f"/api/v1/integrity/verify/{doc_id}", headers=headers)).json()
    assert verify["verification_status"] == "VERIFIED_MATCH" and verify["chain_status"] == "CONFIRMED"
    assert verify["chain_tx_hash"].startswith("0x")

    contract = chain.get_contract()
    assert contract.functions.getRecordCommitment(Web3.keccak(text=doc_id)).call()[1] == 0  # bare hash finds nothing
    assert contract.functions.getRecordCommitment(chain.chain_ref(doc_id)).call()[1] == 1

    assert (await client.post(f"/api/v1/documents/{doc_id}/amend", headers=headers,
                              json={"amendment_text": "K 4.2 on follow-up.", "reason": "Lab follow-up"})).status_code == 200
    await _drain()
    verify = (await client.get(f"/api/v1/integrity/verify/{doc_id}", headers=headers)).json()
    assert verify["verification_status"] == "VERIFIED_MATCH" and verify["record_version"] == 2

    await client.post(f"/api/v1/integrity/tamper-demo/{doc_id}", headers=headers)
    assert (await client.get(f"/api/v1/integrity/verify/{doc_id}", headers=headers)).json()["verification_status"] == "TAMPER_DETECTED"

    consent_id = (await client.get("/api/v1/consents", headers=p_headers)).json()[0]["id"]
    assert (await client.post(f"/api/v1/consents/{consent_id}/revoke", headers=p_headers)).json()["chain_status"] == "QUEUED"
    await _drain()
    assert contract.functions.consents(chain.chain_ref(consent_id)).call()[3] == chain.CONSENT_REVOKED

    async with database.AsyncSessionLocal() as db:
        consent = await db.get(Consent, consent_id)
        anchor = (await db.execute(select(OutboxEvent).where(
            OutboxEvent.aggregate_id == doc_id, OutboxEvent.event_type == "BLOCKCHAIN_ANCHOR_RECORD",
            OutboxEvent.status == "COMPLETED"))).scalars().first()
        failed = (await db.execute(select(OutboxEvent).where(OutboxEvent.status == "FAILED"))).scalars().all()
        confirmed = (await db.execute(select(BlockchainEvent).where(BlockchainEvent.status == "CONFIRMED"))).scalars().all()
    again = await chain.BlockchainService.record_consent_revoked(consent_id, consent.patient_id)
    assert again.status == chain.CONFIRMED and again.tx_hash is None  # idempotent redelivery
    stale = await chain.BlockchainService.anchor_record(doc_id, anchor.payload_json["commitment_hash"], anchor.payload_json["version"])
    assert stale.status in (chain.PERMANENT_FAILURE, chain.CONFIRMED)  # never rolls an amendment back
    assert not failed and confirmed and all(row.transaction_hash for row in confirmed)
