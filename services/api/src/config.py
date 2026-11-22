from typing import List, Optional
from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import make_url
import os
from urllib.parse import urlsplit

DEVELOPMENT_SECRET_KEY = "medchain-development-secret-key-32-bytes-long-change-in-prod"
DEVELOPMENT_BLOCKCHAIN_PRIVATE_KEY = "0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80"
DEVELOPMENT_DOCUMENT_ENCRYPTION_KEY = "0000000000000000000000000000000000000000000000000000000000000000"
DEVELOPMENT_CHAIN_PSEUDONYM_KEY = "medchain-development-chain-pseudonym-key-change-me"
DEVELOPMENT_ENVIRONMENTS = {"development", "dev", "test", "testing"}


def _validate_postgres_url_overrides(async_url: Optional[str], sync_url: Optional[str]) -> None:
    if bool(async_url) != bool(sync_url):
        raise ValueError("DATABASE_URL and DATABASE_SYNC_URL must be configured together outside development and test.")
    if not async_url or not sync_url:
        return

    parsed_urls = []
    for configured_url in (async_url, sync_url):
        try:
            parsed = make_url(configured_url)
        except Exception as exc:
            raise ValueError("Configured database URLs must be valid PostgreSQL URLs.") from exc

        if parsed.drivername.split("+", 1)[0] not in {"postgres", "postgresql"}:
            raise ValueError("Non-development database URLs must use PostgreSQL.")
        if not parsed.host or not parsed.username or not parsed.password or not parsed.database:
            raise ValueError("Production database URLs must include a host, database, username, and password.")
        if parsed.password == "medchain_secret_pass" or len(parsed.password) < 24:
            raise ValueError("Passwords embedded in production database URLs must be unique and at least 24 characters.")
        parsed_urls.append(parsed)

    async_target, sync_target = parsed_urls
    if async_target.drivername != "postgresql+asyncpg":
        raise ValueError("DATABASE_URL must use the installed asyncpg PostgreSQL driver.")
    if sync_target.drivername not in {"postgresql", "postgresql+psycopg2"}:
        raise ValueError("DATABASE_SYNC_URL must use a supported synchronous PostgreSQL driver.")
    same_target = (
        async_target.host.lower() == sync_target.host.lower()
        and (async_target.port or 5432) == (sync_target.port or 5432)
        and async_target.database == sync_target.database
        and async_target.username == sync_target.username
        and async_target.password == sync_target.password
    )
    if not same_target:
        raise ValueError("DATABASE_URL and DATABASE_SYNC_URL must use matching PostgreSQL credentials and target the same database.")

class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=os.path.join(os.path.dirname(__file__), "../../../.env"),
        env_file_encoding="utf-8",
        extra="ignore"
    )

    ENVIRONMENT: str = "development"
    DEMO_MODE: bool = True
    API_PORT: int = 8000
    API_HOST: str = "0.0.0.0"
    CORS_ORIGINS: str = "http://localhost:3000,http://127.0.0.1:3000"
    SECRET_KEY: str = DEVELOPMENT_SECRET_KEY
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 15
    DOCUMENT_ENCRYPTION_KEY: str = DEVELOPMENT_DOCUMENT_ENCRYPTION_KEY

    # PostgreSQL
    POSTGRES_USER: str = "medchain_user"
    POSTGRES_PASSWORD: str = "medchain_secret_pass"
    POSTGRES_DB: str = "medchain_db"
    POSTGRES_HOST: str = "localhost"
    POSTGRES_PORT: int = 5432
    DATABASE_URL: Optional[str] = None
    DATABASE_SYNC_URL: Optional[str] = None

    # Fallback SQLite
    FALLBACK_SQLITE_URL: str = f"sqlite+aiosqlite:///{os.path.abspath(os.path.join(os.path.dirname(__file__), '../medchain_local.db')).replace(chr(92), '/')}"
    FALLBACK_SQLITE_SYNC_URL: str = f"sqlite:///{os.path.abspath(os.path.join(os.path.dirname(__file__), '../medchain_local.db')).replace(chr(92), '/')}"
    USE_SQLITE_FALLBACK: bool = False

    # MongoDB
    MONGO_URI: str = "mongodb://localhost:27017"
    MONGO_DB_NAME: str = "medchain_docs"
    MONGO_DOCUMENTS_COLLECTION: str = "medical_documents"

    # Neo4j
    NEO4J_URI: str = "bolt://localhost:7687"
    NEO4J_USER: str = "neo4j"
    NEO4J_PASSWORD: str = "medchain_graph_pass"

    # Blockchain
    BLOCKCHAIN_RPC_URL: str = "http://localhost:8545"
    CONTRACT_ADDRESS: str = "0x5FbDB2315678afecb367f032d93F642f64180aa3"
    BLOCKCHAIN_PRIVATE_KEY: str = "0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80"
    BLOCKCHAIN_CHAIN_ID: int = 31337
    BLOCKCHAIN_TX_TIMEOUT_SECONDS: int = 30
    # Keyed pseudonyms keep on-chain references unlinkable to internal UUIDs without this key.
    CHAIN_PSEUDONYM_KEY: str = DEVELOPMENT_CHAIN_PSEUDONYM_KEY

    # Transactional outbox delivery
    OUTBOX_WORKER_ENABLED: bool = True
    OUTBOX_POLL_SECONDS: float = 5.0
    OUTBOX_BATCH_SIZE: int = 25
    OUTBOX_MAX_RETRIES: int = 12
    OUTBOX_STALE_PROCESSING_SECONDS: int = 300

    # Sign-in protection
    LOGIN_MAX_FAILED_ATTEMPTS: int = 5
    LOGIN_LOCKOUT_MINUTES: int = 15
    LOGIN_RATE_LIMIT_PER_MINUTE: int = 20

    # Clinical integration (HL7 v2 / interface engine)
    INTEGRATION_API_KEYS: str = ""
    INTEGRATION_DEFAULT_FACILITY: str = ""
    MLLP_HOST: str = "127.0.0.1"
    MLLP_PORT: int = 2575
    MLLP_TLS_CERT_FILE: Optional[str] = None
    MLLP_TLS_KEY_FILE: Optional[str] = None
    MLLP_TLS_CLIENT_CA_FILE: Optional[str] = None
    MLLP_SOURCE_NAME: str = "mllp"

    # Break-the-glass emergency access window
    BREAK_GLASS_WINDOW_MINUTES: int = 240
    # Care-team access granted by an admission ends this many days after discharge (0 = at discharge).
    CARE_TEAM_POST_DISCHARGE_DAYS: int = 30
    # >0 limits access through an undischarged visit (e.g. outpatient) to visits this recent.
    VISIT_RELATIONSHIP_ACCESS_DAYS: int = 0
    # Single-hospital boundary: facility codes this installation accepts data for (empty = any registered).
    HOSPITAL_FACILITY_CODES: str = ""

    # Document / field encryption key ring ("kid:64hex,kid2:64hex"); empty = DOCUMENT_ENCRYPTION_KEY as "k1".
    DOCUMENT_ENCRYPTION_KEYS: str = ""
    DOCUMENT_ENCRYPTION_ACTIVE_KEY_ID: str = "k1"

    # Multi-factor authentication for local accounts (comma-separated roles)
    MFA_REQUIRED_ROLES: str = ""
    MFA_ISSUER: str = "MedChain"

    # Hospital single sign-on (OpenID Connect, authorization code + PKCE)
    OIDC_ENABLED: bool = False
    OIDC_ISSUER: str = ""
    OIDC_CLIENT_ID: str = ""
    OIDC_CLIENT_SECRET: str = ""
    OIDC_REDIRECT_URI: str = ""
    OIDC_SCOPES: str = "openid email profile"
    OIDC_ROLE_CLAIM: str = "groups"
    # "idp-group:medchain-role,..." e.g. "MedChain-Doctors:doctor,MedChain-Admins:admin"
    OIDC_ROLE_MAP: str = ""
    OIDC_ALLOW_JIT_PROVISIONING: bool = False
    OIDC_REQUIRE_MFA_CLAIM: bool = False
    OIDC_POST_LOGIN_REDIRECT: str = "/"

    # SCIM 2.0 provisioning (sha256 hex of the bearer token the identity provider presents)
    SCIM_BEARER_TOKEN_HASH: str = ""

    # Real-time event fan-out: "auto" uses PostgreSQL LISTEN/NOTIFY when available, "local" is per process
    EVENT_BUS_BACKEND: str = "auto"

    # Operational monitoring and alerting
    MONITOR_ENABLED: bool = True
    MONITOR_INTERVAL_SECONDS: int = 60
    ALERT_WEBHOOK_URL: str = ""
    OUTBOX_ALERT_AGE_SECONDS: int = 900
    INTEGRATION_SILENCE_ALERT_MINUTES: int = 0  # 0 disables feed-silence alerts
    BREAK_GLASS_REVIEW_SLA_HOURS: int = 24
    GRAPH_STALE_AFTER_SECONDS: int = 86400
    METRICS_BEARER_TOKEN_HASH: str = ""

    # Ledger transaction handling
    BLOCKCHAIN_PRIVATE_KEY_FILE: Optional[str] = None
    BLOCKCHAIN_CONFIRMATIONS: int = 1

    @property
    def is_development(self) -> bool:
        return self.ENVIRONMENT.strip().lower() in DEVELOPMENT_ENVIRONMENTS

    @staticmethod
    def _csv(value: str) -> List[str]:
        return [item.strip() for item in value.split(",") if item.strip()]

    @property
    def mfa_required_roles(self) -> set:
        return set(self._csv(self.MFA_REQUIRED_ROLES))

    @property
    def allowed_facility_codes(self) -> set:
        return set(self._csv(self.HOSPITAL_FACILITY_CODES))

    @property
    def oidc_role_map(self) -> dict:
        mapping = {}
        for item in self._csv(self.OIDC_ROLE_MAP):
            group, _, role = item.rpartition(":")
            if group and role:
                mapping[group.strip()] = role.strip()
        return mapping

    @property
    def encryption_key_ring(self) -> dict:
        """kid -> 32-byte key. Without DOCUMENT_ENCRYPTION_KEYS, DOCUMENT_ENCRYPTION_KEY is kid 'k1'."""
        ring = {}
        for item in self._csv(self.DOCUMENT_ENCRYPTION_KEYS):
            kid, _, hex_key = item.partition(":")
            ring[kid.strip()] = bytes.fromhex(hex_key.strip())
        if not ring:
            ring["k1"] = bytes.fromhex(self.DOCUMENT_ENCRYPTION_KEY)
        return ring

    @property
    def blockchain_private_key(self) -> str:
        if self.BLOCKCHAIN_PRIVATE_KEY_FILE:
            with open(self.BLOCKCHAIN_PRIVATE_KEY_FILE, "r", encoding="utf-8") as handle:
                return handle.read().strip()
        return self.BLOCKCHAIN_PRIVATE_KEY

    @property
    def integration_key_hashes(self) -> dict:
        """Map of sha256(api_key) hex -> source system name."""
        mapping = {}
        for item in self.INTEGRATION_API_KEYS.split(","):
            item = item.strip()
            if not item:
                continue
            source, _, key_hash = item.partition(":")
            if source and len(key_hash) == 64:
                mapping[key_hash.lower()] = source.strip()
        return mapping

    @model_validator(mode="after")
    def validate_production_security(self):
        environment = self.ENVIRONMENT.strip().lower()
        if self.ACCESS_TOKEN_EXPIRE_MINUTES < 1 or self.ACCESS_TOKEN_EXPIRE_MINUTES > 60:
            raise ValueError("ACCESS_TOKEN_EXPIRE_MINUTES must be between 1 and 60 minutes.")
        if self.LOGIN_MAX_FAILED_ATTEMPTS < 1 or self.LOGIN_LOCKOUT_MINUTES < 1:
            raise ValueError("Login lockout settings must be positive.")
        try:
            ring = self.encryption_key_ring
        except ValueError as exc:
            raise ValueError("DOCUMENT_ENCRYPTION_KEYS must be 'kid:64-hex-char-key' pairs.") from exc
        if any(len(key) != 32 for key in ring.values()):
            raise ValueError("Every document encryption key must be 32 bytes (64 hex characters).")
        if self.DOCUMENT_ENCRYPTION_ACTIVE_KEY_ID not in ring:
            raise ValueError("DOCUMENT_ENCRYPTION_ACTIVE_KEY_ID must name a key in the key ring.")
        if self.EVENT_BUS_BACKEND not in {"auto", "local"}:
            raise ValueError("EVENT_BUS_BACKEND must be 'auto' or 'local'.")
        if self.OIDC_ENABLED and not (self.OIDC_ISSUER and self.OIDC_CLIENT_ID and self.OIDC_REDIRECT_URI):
            raise ValueError("OIDC_ENABLED requires OIDC_ISSUER, OIDC_CLIENT_ID, and OIDC_REDIRECT_URI.")
        if environment not in DEVELOPMENT_ENVIRONMENTS:
            if not self.OIDC_ENABLED and "admin" not in self.mfa_required_roles:
                raise ValueError("Production requires hospital SSO (OIDC_ENABLED) or MFA for admins (MFA_REQUIRED_ROLES).")
            if self.OIDC_ENABLED and not self.OIDC_ISSUER.startswith("https://"):
                raise ValueError("OIDC_ISSUER must be an HTTPS URL outside development.")
            if bytes.fromhex(DEVELOPMENT_DOCUMENT_ENCRYPTION_KEY) in ring.values():
                raise ValueError("The development encryption key must not be in the production key ring.")
            if self.CHAIN_PSEUDONYM_KEY == DEVELOPMENT_CHAIN_PSEUDONYM_KEY or len(self.CHAIN_PSEUDONYM_KEY) < 32:
                raise ValueError("Non-development CHAIN_PSEUDONYM_KEY must be unique and at least 32 characters.")
            if (self.MLLP_TLS_CERT_FILE is None) != (self.MLLP_TLS_KEY_FILE is None):
                raise ValueError("MLLP_TLS_CERT_FILE and MLLP_TLS_KEY_FILE must be configured together.")
            if self.DEMO_MODE:
                raise ValueError("DEMO_MODE must be false outside development and test environments.")
            if self.SECRET_KEY == DEVELOPMENT_SECRET_KEY or len(self.SECRET_KEY) < 32:
                raise ValueError("Non-development SECRET_KEY must be unique and at least 32 characters.")
            if self.DOCUMENT_ENCRYPTION_KEY == DEVELOPMENT_DOCUMENT_ENCRYPTION_KEY:
                raise ValueError("Non-development DOCUMENT_ENCRYPTION_KEY must be unique.")
            try:
                document_key = bytes.fromhex(self.DOCUMENT_ENCRYPTION_KEY)
            except ValueError as exc:
                raise ValueError("DOCUMENT_ENCRYPTION_KEY must be a 64-character hexadecimal AES-256 key.") from exc
            if len(document_key) != 32:
                raise ValueError("DOCUMENT_ENCRYPTION_KEY must be a 64-character hexadecimal AES-256 key.")
            if self.POSTGRES_PASSWORD == "medchain_secret_pass" or len(self.POSTGRES_PASSWORD) < 24:
                raise ValueError("Non-development PostgreSQL password must be unique and at least 24 characters.")
            if self.NEO4J_PASSWORD == "medchain_graph_pass" or len(self.NEO4J_PASSWORD) < 24:
                raise ValueError("Non-development Neo4j password must be unique and at least 24 characters.")
            mongo_uri = urlsplit(self.MONGO_URI)
            if mongo_uri.scheme not in {"mongodb", "mongodb+srv"} or not mongo_uri.username or not mongo_uri.password:
                raise ValueError("Non-development MongoDB URI must use authenticated credentials.")
            if mongo_uri.password == "medchain_mongo_pass" or len(mongo_uri.password) < 24:
                raise ValueError("Non-development MongoDB password must be unique and at least 24 characters.")
            if self.BLOCKCHAIN_PRIVATE_KEY == DEVELOPMENT_BLOCKCHAIN_PRIVATE_KEY or self.BLOCKCHAIN_CHAIN_ID == 31337:
                raise ValueError("Non-development blockchain settings must not use the public Hardhat development account or chain.")
            if self.USE_SQLITE_FALLBACK:
                raise ValueError("SQLite fallback must be disabled outside development and test environments.")
            _validate_postgres_url_overrides(self.DATABASE_URL, self.DATABASE_SYNC_URL)
            if not self.cors_origin_list or "*" in self.cors_origin_list:
                raise ValueError("Non-development CORS_ORIGINS must list explicit HTTPS application origins.")
            if any(
                urlsplit(origin).scheme != "https"
                or not urlsplit(origin).netloc
                or urlsplit(origin).path
                for origin in self.cors_origin_list
            ):
                raise ValueError("Non-development CORS_ORIGINS must contain HTTPS origins without paths.")
        return self

    @property
    def cors_origin_list(self) -> List[str]:
        return [origin.strip() for origin in self.CORS_ORIGINS.split(",") if origin.strip()]

settings = Settings()
