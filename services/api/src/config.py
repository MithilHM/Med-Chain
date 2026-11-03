from typing import List, Optional
from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import make_url
import os
from urllib.parse import urlsplit

DEVELOPMENT_SECRET_KEY = "medchain-development-secret-key-32-bytes-long-change-in-prod"
DEVELOPMENT_BLOCKCHAIN_PRIVATE_KEY = "0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80"
DEVELOPMENT_DOCUMENT_ENCRYPTION_KEY = "0000000000000000000000000000000000000000000000000000000000000000"


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
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 1440
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
    FALLBACK_SQLITE_URL: str = "sqlite+aiosqlite:///./medchain_local.db"
    FALLBACK_SQLITE_SYNC_URL: str = "sqlite:///./medchain_local.db"
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

    @model_validator(mode="after")
    def validate_production_security(self):
        environment = self.ENVIRONMENT.strip().lower()
        if environment not in {"development", "dev", "test", "testing"}:
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
            if any(origin.startswith(("http://localhost", "http://127.0.0.1")) for origin in self.cors_origin_list):
                raise ValueError("Non-development CORS_ORIGINS must not include localhost origins.")
        return self

    @property
    def cors_origin_list(self) -> List[str]:
        return [origin.strip() for origin in self.CORS_ORIGINS.split(",") if origin.strip()]

settings = Settings()
