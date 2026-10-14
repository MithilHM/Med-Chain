import logging
import json
import os
from typing import Dict, Any, Optional, List
from motor.motor_asyncio import AsyncIOMotorClient
from src.config import settings

logger = logging.getLogger("medchain.mongo")

_client: Optional[AsyncIOMotorClient] = None
_fallback_storage_file = os.path.join(os.path.dirname(__file__), "../../../mongo_documents_fallback.json")
_in_memory_docs: Dict[str, Dict[str, Any]] = {}

def _load_fallback():
    global _in_memory_docs
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
            logger.warning(f"MongoDB connection failed ({e}). Using local resilient document store fallback.")
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
                await collection.replace_one({"_id": doc_id}, doc_data, upsert=True)
                return doc_id
            except Exception as e:
                logger.warning(f"MongoDB write failed ({e}); falling back to local file storage.")
        
        # Fallback
        _in_memory_docs[doc_id] = doc_data
        _save_fallback()
        return doc_id

    @staticmethod
    async def get_document(doc_id: str) -> Optional[Dict[str, Any]]:
        client = await get_mongo_client()
        if client:
            try:
                db = client[settings.MONGO_DB_NAME]
                collection = db[settings.MONGO_DOCUMENTS_COLLECTION]
                doc = await collection.find_one({"_id": doc_id})
                if doc:
                    return doc
            except Exception as e:
                logger.warning(f"MongoDB read failed ({e}); checking local fallback.")
        
        return _in_memory_docs.get(doc_id)

    @staticmethod
    async def update_document_content(doc_id: str, new_content: str) -> bool:
        """Used for normal updates or demo tampering"""
        client = await get_mongo_client()
        if client:
            try:
                db = client[settings.MONGO_DB_NAME]
                collection = db[settings.MONGO_DOCUMENTS_COLLECTION]
                await collection.update_one({"_id": doc_id}, {"$set": {"content": new_content}})
            except Exception as e:
                logger.warning(f"MongoDB update failed ({e}); updating local fallback.")
        
        if doc_id in _in_memory_docs:
            _in_memory_docs[doc_id]["content"] = new_content
            _save_fallback()
            return True
        return False

    @staticmethod
    async def clear_all():
        global _in_memory_docs
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
                return {"status": "up", "mode": "mongodb_live", "count": await client[settings.MONGO_DB_NAME][settings.MONGO_DOCUMENTS_COLLECTION].count_documents({})}
            except Exception:
                pass
        return {"status": "up", "mode": "fallback_document_store", "count": len(_in_memory_docs)}
