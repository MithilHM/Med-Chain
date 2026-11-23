"""Encryption key rotation for every application-encrypted field.

Procedure (see docs/OPERATIONS.md):
1. Add the new key to DOCUMENT_ENCRYPTION_KEYS (keep the old one) and set
   DOCUMENT_ENCRYPTION_ACTIVE_KEY_ID to it; restart. New writes use the new key.
2. Run `python scripts/rotate_encryption_key.py` to re-encrypt existing data.
3. When `status()` reports zero values under the old key, remove it from the ring.
"""
from collections import Counter
from typing import Dict

from sqlalchemy import select

from src import database
from src.config import settings
from src.models import AppUser, InboundMessage, Patient
from src.services.crypto import ciphertext_key_id, decrypt_text, encrypt_text
from src.services.mongo import MongoDocumentService

# (model, column attribute, associated-data builder)
_FIELDS = (
    (InboundMessage, "raw_encrypted", lambda row: f"inbound:{row.id}"),
    (Patient, "name_encrypted", lambda row: f"patient-name:{row.id}"),
    (AppUser, "mfa_secret_encrypted", lambda row: f"mfa:{row.id}"),
)


async def status() -> Dict[str, Dict[str, int]]:
    report: Dict[str, Dict[str, int]] = {}
    async with database.AsyncSessionLocal() as db:
        for model, attribute, _ in _FIELDS:
            column = getattr(model, attribute)
            values = (await db.execute(select(column).where(column.is_not(None)))).scalars().all()
            report[f"{model.__tablename__}.{attribute}"] = dict(Counter(ciphertext_key_id(v) or "legacy" for v in values))
    return report


async def rotate(batch_size: int = 500) -> Dict[str, int]:
    active = settings.DOCUMENT_ENCRYPTION_ACTIVE_KEY_ID
    counts: Dict[str, int] = {}
    for model, attribute, aad in _FIELDS:
        column = getattr(model, attribute)
        rotated = 0
        while True:
            async with database.AsyncSessionLocal() as db:
                rows = (await db.execute(
                    select(model).where(column.is_not(None), ~column.like(f"v2:{active}:%")).limit(batch_size)
                )).scalars().all()
                if not rows:
                    break
                for row in rows:
                    setattr(row, attribute, encrypt_text(decrypt_text(getattr(row, attribute), aad(row)), aad(row)))
                await db.commit()
                rotated += len(rows)
        counts[f"{model.__tablename__}.{attribute}"] = rotated
    documents = await MongoDocumentService.reencrypt_all()
    counts["documents.reencrypted"] = documents["reencrypted"]
    return counts
