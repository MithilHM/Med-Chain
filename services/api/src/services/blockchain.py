"""EVM audit-ledger client.

Design rules:
- Only opaque keyed pseudonyms (HMAC-SHA256 with CHAIN_PSEUDONYM_KEY) and commitments go on-chain.
  A bare keccak of an internal UUID would let anyone holding that UUID link every on-chain event to it.
- web3 is synchronous, so every RPC call runs in a worker thread and never blocks the API event loop.
- Transactions from the signing account are serialized with a lock and use the pending nonce.
- Write methods check on-chain state first so the outbox can safely retry (at-least-once delivery
  without duplicate state changes).
"""
import asyncio
import hashlib
import hmac
import json
import logging
import os
import threading
import time
from dataclasses import dataclass
from typing import Any, Callable, Dict, Optional, Tuple

from web3 import Web3

from src.config import settings

logger = logging.getLogger("medchain.blockchain")

_w3: Optional[Web3] = None
_contract = None
_contract_address: Optional[str] = None
_last_check_time: float = 0.0
_is_connected_cache: bool = False
_last_chain_id: Optional[int] = None
_client_lock = threading.Lock()
_send_lock = threading.Lock()

# Result statuses for write operations
CONFIRMED = "CONFIRMED"          # state is on-chain (newly sent, or already present)
RETRY = "RETRY"                  # transient: chain unavailable, timeout, or dependency not yet anchored
PERMANENT_FAILURE = "PERMANENT_FAILURE"  # the contract will never accept this payload

CONSENT_NONE, CONSENT_GRANTED, CONSENT_REVOKED = 0, 1, 2


@dataclass
class ChainResult:
    status: str
    tx_hash: Optional[str] = None
    block_number: Optional[int] = None
    detail: Optional[str] = None


def get_contract_abi() -> Optional[list]:
    abi_path = os.path.join(
        os.path.dirname(__file__),
        "../../../../contracts/artifacts/contracts/MedChainAudit.sol/MedChainAudit.json"
    )
    if os.path.exists(abi_path):
        try:
            with open(abi_path, "r", encoding="utf-8") as f:
                return json.load(f).get("abi")
        except Exception as e:
            logger.warning("Failed to read contract artifact: %s", e)
    return None


def get_web3_client() -> Optional[Web3]:
    global _w3, _last_check_time, _is_connected_cache, _last_chain_id
    with _client_lock:
        now = time.time()
        # Cache the connectivity result briefly to avoid repeated socket timeouts.
        if now - _last_check_time < 10.0:
            return _w3 if _is_connected_cache else None

        _last_check_time = now
        try:
            w3 = Web3(Web3.HTTPProvider(settings.BLOCKCHAIN_RPC_URL, request_kwargs={"timeout": 3}))
            if w3.is_connected():
                actual_chain_id = int(w3.eth.chain_id)
                _last_chain_id = actual_chain_id
                if actual_chain_id != settings.BLOCKCHAIN_CHAIN_ID:
                    logger.error(
                        "Blockchain RPC chain ID %s does not match configured chain ID %s.",
                        actual_chain_id, settings.BLOCKCHAIN_CHAIN_ID,
                    )
                    _w3, _is_connected_cache = None, False
                    return None
                _w3, _is_connected_cache = w3, True
                return _w3
            _w3, _is_connected_cache, _last_chain_id = None, False, None
        except Exception:
            _w3, _is_connected_cache, _last_chain_id = None, False, None
        return None


def reset_client_cache() -> None:
    """Force the next call to re-check connectivity (used after failures and in tests)."""
    global _last_check_time
    with _client_lock:
        _last_check_time = 0.0


def get_contract():
    global _contract, _contract_address
    w3 = get_web3_client()
    if not w3:
        return None
    try:
        checksum_address = Web3.to_checksum_address(settings.CONTRACT_ADDRESS)
        if not w3.eth.get_code(checksum_address):
            _contract, _contract_address = None, None
            return None
        if _contract is not None and _contract_address == checksum_address:
            return _contract
        abi = get_contract_abi()
        if not abi:
            return None
        _contract = w3.eth.contract(address=checksum_address, abi=abi)
        _contract_address = checksum_address
    except Exception as e:
        _contract, _contract_address = None, None
        logger.warning("Failed to initialize deployed contract instance: %s", e)
    return _contract


def chain_ref(text: str) -> bytes:
    """Keyed 32-byte pseudonym for an internal identifier."""
    return hmac.new(settings.CHAIN_PSEUDONYM_KEY.encode("utf-8"), text.encode("utf-8"), hashlib.sha256).digest()


# Backwards-compatible name used by older call sites.
to_bytes32 = chain_ref


def _send_transaction(build: Callable[[Any], Any]) -> ChainResult:
    """Sign and send one contract transaction; serialized per process to avoid nonce reuse."""
    w3 = get_web3_client()
    contract = get_contract()
    if not w3 or not contract:
        return ChainResult(RETRY, detail="Blockchain RPC or contract unavailable.")
    with _send_lock:
        try:
            private_key = settings.blockchain_private_key
            account = w3.eth.account.from_key(private_key)
            function_call = build(contract)
            tx_params = {
                "from": account.address,
                "nonce": w3.eth.get_transaction_count(account.address, "pending"),
                "chainId": settings.BLOCKCHAIN_CHAIN_ID,
            }
            # Estimated gas with headroom; a revert surfaces here as a permanent failure.
            tx_params["gas"] = int(function_call.estimate_gas({"from": account.address}) * 1.25) + 10000
            base_fee = w3.eth.get_block("latest").get("baseFeePerGas")
            if base_fee is not None:  # EIP-1559 network (Besu, Geth, Hardhat)
                priority = w3.eth.max_priority_fee
                tx_params.update(maxPriorityFeePerGas=priority, maxFeePerGas=int(base_fee) * 2 + priority)
            else:  # legacy pricing (zero-gas permissioned networks report 0)
                tx_params["gasPrice"] = w3.eth.gas_price
            tx = function_call.build_transaction(tx_params)
            signed = w3.eth.account.sign_transaction(tx, private_key)
            tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
            receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=settings.BLOCKCHAIN_TX_TIMEOUT_SECONDS)
            if receipt.status == 1 and settings.BLOCKCHAIN_CONFIRMATIONS > 1:
                target = receipt.blockNumber + settings.BLOCKCHAIN_CONFIRMATIONS - 1
                deadline = time.time() + settings.BLOCKCHAIN_TX_TIMEOUT_SECONDS
                while w3.eth.block_number < target:
                    if time.time() > deadline:
                        return ChainResult(RETRY, detail="Transaction mined but not yet confirmed.")
                    time.sleep(1)
        except Exception as e:
            reset_client_cache()
            message = str(e)
            if "revert" in message.lower():
                return ChainResult(PERMANENT_FAILURE, detail=message[:300])
            logger.warning("Blockchain transaction failed and will be retried: %s", message[:300])
            return ChainResult(RETRY, detail=message[:300])
    tx_hex = Web3.to_hex(receipt.transactionHash)  # always 0x-prefixed (HexBytes.hex() is not in web3 v7)
    if receipt.status != 1:
        return ChainResult(PERMANENT_FAILURE, tx_hex, receipt.blockNumber, "Transaction reverted.")
    return ChainResult(CONFIRMED, tx_hex, receipt.blockNumber)


def _consent_state(contract, consent_id: str) -> Optional[int]:
    try:
        record = contract.functions.consents(chain_ref(consent_id)).call()
        return int(record[3])
    except Exception as e:
        logger.warning("Could not read on-chain consent state: %s", e)
        return None


def _anchor_record_sync(record_ref: str, commitment_hex: str, version: int) -> ChainResult:
    contract = get_contract()
    if not contract:
        return ChainResult(RETRY, detail="Contract unavailable.")
    commitment_bytes = bytes.fromhex(commitment_hex.replace("0x", ""))
    try:
        existing_commitment, existing_version, _ = contract.functions.getRecordCommitment(chain_ref(record_ref)).call()
    except Exception as e:
        reset_client_cache()
        return ChainResult(RETRY, detail=f"Could not read existing commitment: {e}"[:300])
    if int(existing_version) == int(version) and bytes(existing_commitment) == commitment_bytes:
        return ChainResult(CONFIRMED, detail="Commitment already anchored.")
    if int(existing_version) >= int(version):
        return ChainResult(PERMANENT_FAILURE, detail="A different commitment is already anchored for this or a later version.")
    return _send_transaction(lambda c: c.functions.anchorRecord(chain_ref(record_ref), commitment_bytes, int(version)))


def _grant_consent_sync(consent_id: str, patient_id: str, project_id: str, valid_until_ts: int) -> ChainResult:
    contract = get_contract()
    if not contract:
        return ChainResult(RETRY, detail="Contract unavailable.")
    state = _consent_state(contract, consent_id)
    if state is None:
        return ChainResult(RETRY, detail="Could not read consent state.")
    if state in (CONSENT_GRANTED, CONSENT_REVOKED):
        return ChainResult(CONFIRMED, detail="Consent grant already recorded.")
    if valid_until_ts <= int(time.time()):
        return ChainResult(PERMANENT_FAILURE, detail="Consent expired before it could be anchored.")
    return _send_transaction(lambda c: c.functions.grantConsent(
        chain_ref(consent_id), chain_ref(patient_id), chain_ref(project_id), int(valid_until_ts)
    ))


def _revoke_consent_sync(consent_id: str, patient_id: str) -> ChainResult:
    contract = get_contract()
    if not contract:
        return ChainResult(RETRY, detail="Contract unavailable.")
    state = _consent_state(contract, consent_id)
    if state is None:
        return ChainResult(RETRY, detail="Could not read consent state.")
    if state == CONSENT_REVOKED:
        return ChainResult(CONFIRMED, detail="Consent revocation already recorded.")
    if state == CONSENT_NONE:
        # The grant has not been anchored yet; retry after the grant event is delivered.
        return ChainResult(RETRY, detail="Consent grant not yet anchored.")
    return _send_transaction(lambda c: c.functions.revokeConsent(chain_ref(consent_id), chain_ref(patient_id)))


def _log_access_sync(event_id: str, actor_id: str, resource_ref: str, action: str, decision: str) -> ChainResult:
    # Access logs are events only; a retry after an unobserved success yields a duplicate log entry with
    # the same eventIdHash, which consumers de-duplicate.
    return _send_transaction(lambda c: c.functions.logAccessEvent(
        chain_ref(event_id), chain_ref(actor_id), chain_ref(resource_ref), action[:64], decision[:16]
    ))


def _get_record_commitment_sync(record_ref: str) -> Tuple[str, Optional[str], Optional[int]]:
    contract = get_contract()
    if not contract:
        return "UNAVAILABLE", None, None
    try:
        commitment, version, _anchored_at = contract.functions.getRecordCommitment(chain_ref(record_ref)).call()
        if not version or int.from_bytes(bytes(commitment), "big") == 0:
            return "UNANCHORED", None, None
        return "CONFIRMED", Web3.to_hex(commitment), int(version)
    except Exception as e:
        logger.error("Failed to read record commitment from blockchain: %s", e)
        return "UNAVAILABLE", None, None


class BlockchainService:
    @staticmethod
    async def get_record_commitment(record_ref: str) -> Tuple[str, Optional[str], Optional[int]]:
        """Read the anchored commitment: (CONFIRMED|UNANCHORED|UNAVAILABLE, commitment_hex, version)."""
        return await asyncio.to_thread(_get_record_commitment_sync, record_ref)

    @staticmethod
    async def anchor_record(record_ref: str, commitment_hex: str, version: int = 1) -> ChainResult:
        return await asyncio.to_thread(_anchor_record_sync, record_ref, commitment_hex, version)

    @staticmethod
    async def record_consent_granted(consent_id: str, patient_id: str, project_id: str, valid_until_ts: int) -> ChainResult:
        return await asyncio.to_thread(_grant_consent_sync, consent_id, patient_id, project_id, valid_until_ts)

    @staticmethod
    async def record_consent_revoked(consent_id: str, patient_id: str) -> ChainResult:
        return await asyncio.to_thread(_revoke_consent_sync, consent_id, patient_id)

    @staticmethod
    async def log_access_event(event_id: str, actor_id: str, resource_ref: str, action: str, decision: str) -> ChainResult:
        return await asyncio.to_thread(_log_access_sync, event_id, actor_id, resource_ref, action, decision)

    @staticmethod
    async def get_status_async() -> Dict[str, Any]:
        return await asyncio.to_thread(BlockchainService.get_status)

    @staticmethod
    def get_status() -> Dict[str, Any]:
        w3 = get_web3_client()
        if not w3:
            chain_mismatch = _last_chain_id is not None and _last_chain_id != settings.BLOCKCHAIN_CHAIN_ID
            return {
                "status": "chain_mismatch" if chain_mismatch else "disconnected",
                "chain_id": settings.BLOCKCHAIN_CHAIN_ID,
                "actual_chain_id": _last_chain_id,
                "contract_address": settings.CONTRACT_ADDRESS,
                "mode": "chain_mismatch" if chain_mismatch else "queued_for_delivery",
                "note": "Blockchain RPC is offline or its chain ID does not match configuration. "
                        "Evidence events stay queued in the transactional outbox until it recovers.",
            }

        contract = get_contract()
        if not contract:
            return {
                "status": "contract_unavailable",
                "chain_id": settings.BLOCKCHAIN_CHAIN_ID,
                "actual_chain_id": _last_chain_id,
                "contract_address": settings.CONTRACT_ADDRESS,
                "mode": "rpc_connected_contract_unavailable",
                "note": "RPC is reachable, but contract bytecode or its ABI is unavailable.",
            }

        try:
            latest_block = w3.eth.block_number
        except Exception as e:
            logger.warning("Blockchain RPC stopped responding during status check: %s", e)
            return {
                "status": "disconnected",
                "chain_id": settings.BLOCKCHAIN_CHAIN_ID,
                "actual_chain_id": _last_chain_id,
                "contract_address": settings.CONTRACT_ADDRESS,
                "mode": "rpc_unavailable",
                "note": "The blockchain RPC stopped responding during the status check.",
            }

        return {
            "status": "connected",
            "chain_id": settings.BLOCKCHAIN_CHAIN_ID,
            "actual_chain_id": _last_chain_id,
            "latest_block": latest_block,
            "contract_address": settings.CONTRACT_ADDRESS,
            "mode": "live_chain",
        }
