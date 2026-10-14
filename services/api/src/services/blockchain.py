import logging
import json
import os
import time
from typing import Optional, Dict, Any, Tuple
from web3 import Web3
from src.config import settings

logger = logging.getLogger("medchain.blockchain")

_w3: Optional[Web3] = None
_contract = None
_last_check_time: float = 0.0
_is_connected_cache: bool = False

def get_contract_abi() -> Optional[list]:
    abi_path = os.path.join(
        os.path.dirname(__file__),
        "../../../../contracts/artifacts/contracts/MedChainAudit.sol/MedChainAudit.json"
    )
    if os.path.exists(abi_path):
        try:
            with open(abi_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                return data.get("abi")
        except Exception as e:
            logger.warning(f"Failed to read contract artifact: {e}")
    return None

def get_web3_client() -> Optional[Web3]:
    global _w3, _last_check_time, _is_connected_cache
    now = time.time()
    # Cache connection check result for 10 seconds to avoid repeating socket timeouts
    if now - _last_check_time < 10.0:
        return _w3 if _is_connected_cache else None

    _last_check_time = now
    try:
        w3 = Web3(Web3.HTTPProvider(settings.BLOCKCHAIN_RPC_URL, request_kwargs={'timeout': 0.5}))
        if w3.is_connected():
            _w3 = w3
            _is_connected_cache = True
            logger.info(f"Connected to local blockchain node at {settings.BLOCKCHAIN_RPC_URL}")
            return _w3
        else:
            _w3 = None
            _is_connected_cache = False
    except Exception:
        _w3 = None
        _is_connected_cache = False
    return None

def get_contract():
    global _contract
    w3 = get_web3_client()
    if w3 and _contract is None:
        abi = get_contract_abi()
        if abi and settings.CONTRACT_ADDRESS:
            try:
                checksum_address = Web3.to_checksum_address(settings.CONTRACT_ADDRESS)
                _contract = w3.eth.contract(address=checksum_address, abi=abi)
            except Exception as e:
                logger.warning(f"Failed to initialize contract instance: {e}")
    return _contract

def to_bytes32(text: str) -> bytes:
    return Web3.keccak(text=text)

class BlockchainService:
    @staticmethod
    async def anchor_record(record_ref: str, commitment_hex: str, version: int = 1) -> Tuple[str, str, Optional[int]]:
        w3 = get_web3_client()
        contract = get_contract()
        if not w3 or not contract:
            return "UNANCHORED", f"unanchored-{record_ref[:8]}", None

        try:
            account = w3.eth.account.from_key(settings.BLOCKCHAIN_PRIVATE_KEY)
            record_ref_hash = to_bytes32(record_ref)
            commitment_bytes = bytes.fromhex(commitment_hex.replace("0x", ""))
            
            tx = contract.functions.anchorRecord(
                record_ref_hash,
                commitment_bytes,
                version
            ).build_transaction({
                'from': account.address,
                'nonce': w3.eth.get_transaction_count(account.address),
                'gas': 200000,
                'gasPrice': w3.eth.gas_price
            })
            signed_tx = w3.eth.account.sign_transaction(tx, settings.BLOCKCHAIN_PRIVATE_KEY)
            tx_hash = w3.eth.send_raw_transaction(signed_tx.raw_transaction)
            receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=10)
            return "CONFIRMED", receipt.transactionHash.hex(), receipt.blockNumber
        except Exception as e:
            logger.error(f"Failed to anchor record to blockchain: {e}")
            return "FAILED", "", None

    @staticmethod
    async def record_consent_granted(consent_id: str, patient_id: str, project_id: str, valid_until_ts: int) -> Tuple[str, str, Optional[int]]:
        w3 = get_web3_client()
        contract = get_contract()
        if not w3 or not contract:
            return "UNANCHORED", f"unanchored-grant-{consent_id[:8]}", None

        try:
            account = w3.eth.account.from_key(settings.BLOCKCHAIN_PRIVATE_KEY)
            tx = contract.functions.grantConsent(
                to_bytes32(consent_id),
                to_bytes32(patient_id),
                to_bytes32(project_id),
                int(valid_until_ts)
            ).build_transaction({
                'from': account.address,
                'nonce': w3.eth.get_transaction_count(account.address),
                'gas': 200000,
                'gasPrice': w3.eth.gas_price
            })
            signed_tx = w3.eth.account.sign_transaction(tx, settings.BLOCKCHAIN_PRIVATE_KEY)
            tx_hash = w3.eth.send_raw_transaction(signed_tx.raw_transaction)
            receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=10)
            return "CONFIRMED", receipt.transactionHash.hex(), receipt.blockNumber
        except Exception as e:
            logger.error(f"Failed to record consent on-chain: {e}")
            return "FAILED", "", None

    @staticmethod
    async def record_consent_revoked(consent_id: str, patient_id: str) -> Tuple[str, str, Optional[int]]:
        w3 = get_web3_client()
        contract = get_contract()
        if not w3 or not contract:
            return "UNANCHORED", f"unanchored-revoked-{consent_id[:8]}", None

        try:
            account = w3.eth.account.from_key(settings.BLOCKCHAIN_PRIVATE_KEY)
            tx = contract.functions.revokeConsent(
                to_bytes32(consent_id),
                to_bytes32(patient_id)
            ).build_transaction({
                'from': account.address,
                'nonce': w3.eth.get_transaction_count(account.address),
                'gas': 200000,
                'gasPrice': w3.eth.gas_price
            })
            signed_tx = w3.eth.account.sign_transaction(tx, settings.BLOCKCHAIN_PRIVATE_KEY)
            tx_hash = w3.eth.send_raw_transaction(signed_tx.raw_transaction)
            receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=10)
            return "CONFIRMED", receipt.transactionHash.hex(), receipt.blockNumber
        except Exception as e:
            logger.error(f"Failed to record consent revocation on-chain: {e}")
            return "FAILED", "", None

    @staticmethod
    async def log_access_event(event_id: str, actor_id: str, resource_ref: str, action: str, decision: str) -> Tuple[str, str]:
        w3 = get_web3_client()
        contract = get_contract()
        if not w3 or not contract:
            return "UNANCHORED", f"unanchored-event-{event_id[:8]}"

        try:
            account = w3.eth.account.from_key(settings.BLOCKCHAIN_PRIVATE_KEY)
            tx = contract.functions.logAccessEvent(
                to_bytes32(event_id),
                to_bytes32(actor_id),
                to_bytes32(resource_ref),
                action,
                decision
            ).build_transaction({
                'from': account.address,
                'nonce': w3.eth.get_transaction_count(account.address),
                'gas': 200000,
                'gasPrice': w3.eth.gas_price
            })
            signed_tx = w3.eth.account.sign_transaction(tx, settings.BLOCKCHAIN_PRIVATE_KEY)
            tx_hash = w3.eth.send_raw_transaction(signed_tx.raw_transaction)
            receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=10)
            return "CONFIRMED", receipt.transactionHash.hex()
        except Exception as e:
            logger.error(f"Failed to log access event on-chain: {e}")
            return "FAILED", ""

    @staticmethod
    def get_status() -> Dict[str, Any]:
        w3 = get_web3_client()
        if w3 and w3.is_connected():
            return {
                "status": "connected",
                "chain_id": settings.BLOCKCHAIN_CHAIN_ID,
                "latest_block": w3.eth.block_number,
                "contract_address": settings.CONTRACT_ADDRESS,
                "mode": "live_local_chain"
            }
        return {
            "status": "disconnected",
            "chain_id": settings.BLOCKCHAIN_CHAIN_ID,
            "contract_address": settings.CONTRACT_ADDRESS,
            "mode": "unanchored_demo_mode",
            "note": "Local Hardhat node is offline. Events and commitments are recorded as unanchored without claiming confirmed on-chain status."
        }
