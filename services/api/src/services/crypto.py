"""Shared symmetric encryption and keyed-hash helpers.

Ciphertext format: "v2:<key id>:<base64(nonce || ciphertext)>". The key id selects a key from
the ring (DOCUMENT_ENCRYPTION_KEYS), so keys can be rotated without making existing data
unreadable: add the new key, make it active, run the re-encryption job, then retire the old key.
Legacy "v1:" values (no key id) decrypt with the original DOCUMENT_ENCRYPTION_KEY.
"""
import base64
import hashlib
import hmac
import secrets
import unicodedata
from typing import Optional, Tuple

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from src.config import settings


class UnknownEncryptionKey(ValueError):
    pass


def active_key() -> Tuple[str, bytes]:
    kid = settings.DOCUMENT_ENCRYPTION_ACTIVE_KEY_ID
    return kid, settings.encryption_key_ring[kid]


def key_for(kid: Optional[str]) -> bytes:
    ring = settings.encryption_key_ring
    if kid is None:
        return bytes.fromhex(settings.DOCUMENT_ENCRYPTION_KEY)  # pre-key-ring data
    if kid not in ring:
        raise UnknownEncryptionKey(f"Encryption key '{kid}' is not in the configured key ring.")
    return ring[kid]


def encrypt_bytes(plaintext: bytes, associated_data: bytes) -> Tuple[str, str]:
    """Return (key id, base64 nonce||ciphertext) using the active key."""
    kid, key = active_key()
    nonce = secrets.token_bytes(12)
    return kid, base64.b64encode(nonce + AESGCM(key).encrypt(nonce, plaintext, associated_data)).decode("ascii")


def decrypt_bytes(payload_b64: str, associated_data: bytes, kid: Optional[str]) -> bytes:
    raw = base64.b64decode(payload_b64, validate=True)
    return AESGCM(key_for(kid)).decrypt(raw[:12], raw[12:], associated_data)


def encrypt_text(plaintext: str, associated_data: str) -> str:
    """AES-256-GCM encrypt; the associated data binds the ciphertext to its record."""
    kid, payload = encrypt_bytes(plaintext.encode("utf-8"), associated_data.encode("utf-8"))
    return f"v2:{kid}:{payload}"


def decrypt_text(token: str, associated_data: str) -> str:
    version, _, rest = token.partition(":")
    if version == "v1":
        return decrypt_bytes(rest, associated_data.encode("utf-8"), None).decode("utf-8")
    if version == "v2":
        kid, _, payload = rest.partition(":")
        return decrypt_bytes(payload, associated_data.encode("utf-8"), kid).decode("utf-8")
    raise ValueError("Unsupported ciphertext version.")


def ciphertext_key_id(token: Optional[str]) -> Optional[str]:
    if not token:
        return None
    version, _, rest = token.partition(":")
    return rest.partition(":")[0] if version == "v2" else None


def sha256_hex(data: str) -> str:
    return hashlib.sha256(data.encode("utf-8")).hexdigest()


def constant_time_lookup(candidate_hash: str, known_hashes: dict):
    """Return the value for a matching hash without short-circuiting on the first byte."""
    match = None
    for known_hash, value in known_hashes.items():
        if hmac.compare_digest(candidate_hash, known_hash):
            match = value
    return match


def constant_time_hash_equals(candidate: str, expected_hash: str) -> bool:
    return bool(expected_hash) and hmac.compare_digest(sha256_hex(candidate), expected_hash.lower())


def _index_key() -> bytes:
    # Derived from the pseudonym key so the blind index rotates independently of encryption keys.
    return hmac.new(settings.CHAIN_PSEUDONYM_KEY.encode("utf-8"), b"medchain-name-index-v1", hashlib.sha256).digest()


def normalize_name(value: str) -> str:
    folded = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    return "".join(ch for ch in folded.lower() if ch.isalnum())


def name_blind_index(value: Optional[str]) -> Optional[str]:
    """Keyed hash of a normalized name: supports exact search without storing searchable plaintext."""
    if not value or not normalize_name(value):
        return None
    return hmac.new(_index_key(), normalize_name(value).encode("utf-8"), hashlib.sha256).hexdigest()
