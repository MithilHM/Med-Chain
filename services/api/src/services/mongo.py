import logging
import json
import os
import base64
import secrets
from typing import Dict, Any, Optional, List
from motor.motor_asyncio import AsyncIOMotorClient
from src.config import settings
from src.services.crypto import decrypt_bytes, encrypt_bytes

logger = logging.getLogger("medchain.mongo")

_client: Optional[AsyncIOMotorClient] = None
_fallback_storage_file = os.path.join(os.path.dirname(__file__), "../../../mongo_documents_fallback.json")
_in_memory_docs: Dict[str, Dict[str, Any]] = {}


class DocumentStoreUnavailable(RuntimeError):
    """MongoDB is unreachable and no fallback is permitted; mapped to HTTP 503 by the API."""


def _local_fallback_enabled() -> bool:
    return settings.ENVIRONMENT.strip().lower() in {"development", "dev", "test", "testing"}

def _encrypt_document(doc_data: Dict[str, Any]) -> Dict[str, Any]:
    plaintext = json.dumps(doc_data, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    kid, payload = encrypt_bytes(plaintext, str(doc_data["_id"]).encode("utf-8"))
    return {
        "_id": doc_data["_id"],
        "encryption_version": 2,
        "key_id": kid,
        "encrypted_payload": payload,
    }

def _decrypt_document(stored: Dict[str, Any]) -> Dict[str, Any]:
    encrypted_payload = stored.get("encrypted_payload")
    if not encrypted_payload:
        # Read legacy documents during the transition to encrypted storage.
        return stored
    kid = stored.get("key_id") if stored.get("encryption_version") == 2 else None
    plaintext = decrypt_bytes(encrypted_payload, str(stored["_id"]).encode("utf-8"), kid)
    return json.loads(plaintext.decode("utf-8"))


def stored_key_id(stored: Dict[str, Any]) -> Optional[str]:
    return stored.get("key_id") if stored.get("encryption_version") == 2 else None

_loaded_mtime: Optional[float] = None


def _file_mtime() -> Optional[float]:
    try:
        return os.path.getmtime(_fallback_storage_file)
    except OSError:
        return None


def _load_fallback():
    global _in_memory_docs, _loaded_mtime
    if not _local_fallback_enabled():
        _in_memory_docs = {}
        return
    if os.path.exists(_fallback_storage_file):
        try:
            with open(_fallback_storage_file, "r", encoding="utf-8") as f:
                _in_memory_docs = json.load(f)
            _loaded_mtime = _file_mtime()
        except Exception as e:
            logger.warning(f"Failed to load fallback documents file: {e}")


def _reload_if_changed():
    """Another process (seed/reset script, MLLP listener) may have rewritten the file since we loaded it."""
    if _file_mtime() != _loaded_mtime:
        _load_fallback()


def _save_fallback():
    global _loaded_mtime
    try:
        with open(_fallback_storage_file, "w", encoding="utf-8") as f:
            json.dump(_in_memory_docs, f, indent=2, default=str)
        _loaded_mtime = _file_mtime()
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
            raise DocumentStoreUnavailable("MongoDB is unavailable and local document fallback is disabled outside development and test.")
        
        # Fallback
        _reload_if_changed()
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

        _reload_if_changed()
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
            raise DocumentStoreUnavailable("MongoDB is unavailable and local document fallback is disabled outside development and test.")

        _reload_if_changed()
        doc = _in_memory_docs.get(doc_id)
        if doc and not doc.get("encrypted_payload"):
            _in_memory_docs[doc_id] = _encrypt_document(doc)
            _save_fallback()
            doc = _in_memory_docs[doc_id]
        return _decrypt_document(doc) if doc else None

    @staticmethod
    async def update_document(doc_id: str, updates: Dict[str, Any]) -> bool:
        """Update multiple fields on an existing document by doc_id."""
        client = await get_mongo_client()
        if client:
            try:
                db = client[settings.MONGO_DB_NAME]
                collection = db[settings.MONGO_DOCUMENTS_COLLECTION]
                current = await collection.find_one({"_id": doc_id})
                if not current:
                    return False
                document = _decrypt_document(current)
                document.update(updates)
                result = await collection.replace_one({"_id": doc_id}, _encrypt_document(document))
                return result.matched_count == 1
            except Exception as e:
                logger.warning("MongoDB update failed: %s", e)

        if not _local_fallback_enabled():
            return False

        _reload_if_changed()
        if doc_id in _in_memory_docs:
            document = _decrypt_document(_in_memory_docs[doc_id])
            document.update(updates)
            _in_memory_docs[doc_id] = _encrypt_document(document)
            _save_fallback()
            return True
        return False

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

        _reload_if_changed()
        if doc_id in _in_memory_docs:
            document = _decrypt_document(_in_memory_docs[doc_id])
            document["content"] = new_content
            _in_memory_docs[doc_id] = _encrypt_document(document)
            _save_fallback()
            return True
        return False

    @staticmethod
    async def reencrypt_all() -> Dict[str, int]:
        """Re-encrypt every payload not already under the active key (key rotation)."""
        active = settings.DOCUMENT_ENCRYPTION_ACTIVE_KEY_ID
        counts = {"reencrypted": 0, "already_current": 0}
        client = await get_mongo_client()
        if client:
            collection = client[settings.MONGO_DB_NAME][settings.MONGO_DOCUMENTS_COLLECTION]
            async for stored in collection.find({}):
                if stored_key_id(stored) == active:
                    counts["already_current"] += 1
                    continue
                await collection.replace_one({"_id": stored["_id"]}, _encrypt_document(_decrypt_document(stored)))
                counts["reencrypted"] += 1
            return counts
        if not _local_fallback_enabled():
            raise DocumentStoreUnavailable("MongoDB is unavailable; key rotation cannot run.")
        _reload_if_changed()
        for doc_id, stored in list(_in_memory_docs.items()):
            if stored_key_id(stored) == active:
                counts["already_current"] += 1
                continue
            _in_memory_docs[doc_id] = _encrypt_document(_decrypt_document(stored))
            counts["reencrypted"] += 1
        _save_fallback()
        return counts

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
