from typing import List, Optional
from pydantic_settings import BaseSettings, SettingsConfigDict
import os

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
    SECRET_KEY: str = "medchain-development-secret-key-32-bytes-long-change-in-prod"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 1440

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

    @property
    def cors_origin_list(self) -> List[str]:
        return [origin.strip() for origin in self.CORS_ORIGINS.split(",") if origin.strip()]

settings = Settings()
