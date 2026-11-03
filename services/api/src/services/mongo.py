import logging
import json
import os
import base64
import secrets
from typing import Dict, Any, Optional, List
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from motor.motor_asyncio import AsyncIOMotorClient
from src.config import settings

logger = logging.getLogger("medchain.mongo")

_client: Optional[AsyncIOMotorClient] = None
_fallback_storage_file = os.path.join(os.path.dirname(__file__), "../../../mongo_documents_fallback.json")
_in_memory_docs: Dict[str, Dict[str, Any]] = {}


def _local_fallback_enabled() -> bool:
    return settings.ENVIRONMENT.strip().lower() in {"development", "dev", "test", "testing"}

def _encrypt_document(doc_data: Dict[str, Any]) -> Dict[str, Any]:
    key = bytes.fromhex(settings.DOCUMENT_ENCRYPTION_KEY)
    nonce = secrets.token_bytes(12)
    plaintext = json.dumps(doc_data, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    ciphertext = AESGCM(key).encrypt(nonce, plaintext, str(doc_data["_id"]).encode("utf-8"))
    return {
        "_id": doc_data["_id"],
        "encryption_version": 1,
        "encrypted_payload": base64.b64encode(nonce + ciphertext).decode("ascii"),
    }

def _decrypt_document(stored: Dict[str, Any]) -> Dict[str, Any]:
    encrypted_payload = stored.get("encrypted_payload")
    if not encrypted_payload:
        # Read legacy documents during the transition to encrypted storage.
        return stored
    raw = base64.b64decode(encrypted_payload, validate=True)
    nonce, ciphertext = raw[:12], raw[12:]
    key = bytes.fromhex(settings.DOCUMENT_ENCRYPTION_KEY)
    plaintext = AESGCM(key).decrypt(nonce, ciphertext, str(stored["_id"]).encode("utf-8"))
    return json.loads(plaintext.decode("utf-8"))

def _load_fallback():
    global _in_memory_docs
    if not _local_fallback_enabled():
        _in_memory_docs = {}
        return
    if os.path.exists(_fallback_storage_file):
        try:
            with open(_fallback_storage_file, "r", encoding="utf-8") as f:
                _in_memory_docs = json.load(f)
        except Exception as e:
            logger.warning(f"Failed to load fallback documents file: {e}")

def _save_fallback():
    try:
        with open(_fallback_storage_file, "w", encoding="utf-8") as f:
            json.dump(_in_memory_docs, f, indent=2, default=str)
    except Exception as e:
        logger.warning(f"Failed to save fallback documents file: {e}")

_load_fallback()

async def get_mongo_client() -> Optional[AsyncIOMotorClient]:
    global _client
    if _client is None:
        try:
            _client = AsyncIOMotorClient(settings.MONGO_URI, serverSelectionTimeoutMS=1000)
            # Ping database
            await _client.admin.command('ping')
            logger.info("Connected to live MongoDB instance.")
        except Exception as e:
            logger.warning("MongoDB connection failed: %s", e)
            _client = None
    return _client

class MongoDocumentService:
    @staticmethod
    async def insert_document(doc_data: Dict[str, Any]) -> str:
        doc_id = doc_data["_id"]
        client = await get_mongo_client()
        if client:
            try:
                db = client[settings.MONGO_DB_NAME]
                collection = db[settings.MONGO_DOCUMENTS_COLLECTION]
                await collection.replace_one({"_id": doc_id}, _encrypt_document(doc_data), upsert=True)
                return doc_id
            except Exception as e:
                logger.warning("MongoDB write failed: %s", e)

        if not _local_fallback_enabled():
            raise RuntimeError("MongoDB is unavailable and local document fallback is disabled outside development and test.")
        
        # Fallback
        _in_memory_docs[doc_id] = _encrypt_document(doc_data)
        _save_fallback()
        return doc_id

    @staticmethod
    async def delete_document(doc_id: str) -> bool:
        """Remove an unreferenced payload when its relational transaction fails."""
        deleted = False
        client = await get_mongo_client()
        if client:
            try:
                db = client[settings.MONGO_DB_NAME]
                result = await db[settings.MONGO_DOCUMENTS_COLLECTION].delete_one({"_id": doc_id})
                deleted = result.deleted_count == 1
            except Exception as e:
                logger.warning("MongoDB cleanup failed for document %s: %s", doc_id, e)

        if not _local_fallback_enabled():
            return False

        if doc_id in _in_memory_docs:
            _in_memory_docs.pop(doc_id, None)
            _save_fallback()
            deleted = True
        return deleted

    @staticmethod
    async def get_document(doc_id: str) -> Optional[Dict[str, Any]]:
        client = await get_mongo_client()
        if client:
            try:
                db = client[settings.MONGO_DB_NAME]
                collection = db[settings.MONGO_DOCUMENTS_COLLECTION]
                doc = await collection.find_one({"_id": doc_id})
                if doc:
                    if not doc.get("encrypted_payload"):
                        # Migrate older plaintext records the first time they are read.
                        await collection.replace_one({"_id": doc_id}, _encrypt_document(doc))
                    return _decrypt_document(doc)
                if not _local_fallback_enabled():
                    return None
            except Exception as e:
                logger.warning("MongoDB read failed: %s", e)

        if not _local_fallback_enabled():
            raise RuntimeError("MongoDB is unavailable and local document fallback is disabled outside development and test.")
        
        doc = _in_memory_docs.get(doc_id)
        if doc and not doc.get("encrypted_payload"):
            _in_memory_docs[doc_id] = _encrypt_document(doc)
            _save_fallback()
            doc = _in_memory_docs[doc_id]
        return _decrypt_document(doc) if doc else None

    @staticmethod
    async def update_document_content(doc_id: str, new_content: str) -> bool:
        """Used for normal updates or demo tampering"""
        client = await get_mongo_client()
        if client:
            try:
                db = client[settings.MONGO_DB_NAME]
                collection = db[settings.MONGO_DOCUMENTS_COLLECTION]
                current = await collection.find_one({"_id": doc_id})
                if not current:
                    return False
                document = _decrypt_document(current)
                document["content"] = new_content
                result = await collection.replace_one({"_id": doc_id}, _encrypt_document(document))
                return result.matched_count == 1
            except Exception as e:
                logger.warning("MongoDB update failed: %s", e)

        if not _local_fallback_enabled():
            return False
        
        if doc_id in _in_memory_docs:
            document = _decrypt_document(_in_memory_docs[doc_id])
            document["content"] = new_content
            _in_memory_docs[doc_id] = _encrypt_document(document)
            _save_fallback()
            return True
        return False

    @staticmethod
    async def clear_all():
        global _in_memory_docs
        if _local_fallback_enabled():
            _in_memory_docs = {}
            _save_fallback()
        client = await get_mongo_client()
        if client:
            try:
                db = client[settings.MONGO_DB_NAME]
                await db[settings.MONGO_DOCUMENTS_COLLECTION].delete_many({})
            except Exception as e:
                logger.warning(f"MongoDB clear failed: {e}")

    @staticmethod
    async def is_healthy() -> Dict[str, Any]:
        client = await get_mongo_client()
        if client:
            try:
                await client.admin.command('ping')
                return {"status": "up", "mode": "mongodb_live_encrypted", "count": await client[settings.MONGO_DB_NAME][settings.MONGO_DOCUMENTS_COLLECTION].count_documents({})}
            except Exception:
                pass
        if _local_fallback_enabled():
            return {"status": "up", "mode": "fallback_encrypted_document_store", "count": len(_in_memory_docs)}
        return {"status": "down", "mode": "mongodb_unavailable", "count": None}
