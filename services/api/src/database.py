import logging
import asyncio
from typing import AsyncGenerator
from contextlib import asynccontextmanager
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import declarative_base
from src.config import settings

logger = logging.getLogger("medchain.database")

Base = declarative_base()

async_engine = None
AsyncSessionLocal = None
is_fallback_active = False

def get_async_url(force_fallback: bool = False) -> str:
    if force_fallback or settings.USE_SQLITE_FALLBACK:
        return settings.FALLBACK_SQLITE_URL
    if settings.DATABASE_URL:
        return settings.DATABASE_URL
    return f"postgresql+asyncpg://{settings.POSTGRES_USER}:{settings.POSTGRES_PASSWORD}@{settings.POSTGRES_HOST}:{settings.POSTGRES_PORT}/{settings.POSTGRES_DB}"

def setup_engine(force_fallback: bool = False):
    global async_engine, AsyncSessionLocal, is_fallback_active
    url = get_async_url(force_fallback=force_fallback)
    is_fallback_active = ("sqlite" in url)

    engine_kwargs = {"echo": False, "future": True}
    if is_fallback_active:
        engine_kwargs["connect_args"] = {"check_same_thread": False}
    else:
        engine_kwargs["pool_pre_ping"] = True
        engine_kwargs["pool_size"] = 10
        engine_kwargs["max_overflow"] = 20

    async_engine = create_async_engine(url, **engine_kwargs)
    AsyncSessionLocal = async_sessionmaker(
        bind=async_engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autoflush=False
    )
    return async_engine

# Default setup
setup_engine(force_fallback=False)

async def check_connection() -> bool:
    global async_engine, is_fallback_active
    if async_engine is None:
        setup_engine()
    try:
        async with async_engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
            return True
    except Exception as e:
        logger.warning(f"Primary PostgreSQL connection failed ({e}). Activating SQLite fallback.")
        setup_engine(force_fallback=True)
        return True

async def init_db():
    import src.models
    await check_connection()
    async with async_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("Database schema initialized successfully.")

async def reset_db():
    import src.models
    await check_connection()
    async with async_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    logger.info("Database reset completed successfully.")

@asynccontextmanager
async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    global AsyncSessionLocal
    await check_connection()
    async with AsyncSessionLocal() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()

async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with get_db_session() as session:
        yield session
