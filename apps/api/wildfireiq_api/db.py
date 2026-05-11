"""SQLite + DuckDB connection management."""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncIterator

import duckdb
import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from .paths import ensure_dirs
from .settings import get_settings


log = structlog.get_logger()

_engine: AsyncEngine | None = None
_sessionmaker: async_sessionmaker[AsyncSession] | None = None


def get_engine() -> AsyncEngine:
    global _engine, _sessionmaker
    if _engine is None:
        ensure_dirs()
        settings = get_settings()
        _engine = create_async_engine(settings.database_url, echo=False, future=True)
        _sessionmaker = async_sessionmaker(_engine, expire_on_commit=False)
    return _engine


def get_sessionmaker() -> async_sessionmaker[AsyncSession]:
    get_engine()
    assert _sessionmaker is not None
    return _sessionmaker


@asynccontextmanager
async def session_scope() -> AsyncIterator[AsyncSession]:
    sm = get_sessionmaker()
    async with sm() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


SCHEMA_DDL = [
    """
    CREATE TABLE IF NOT EXISTS ingest_runs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        job_name TEXT NOT NULL,
        started_at TEXT NOT NULL,
        finished_at TEXT,
        status TEXT NOT NULL,                -- ok | fail | partial
        rows_in INTEGER DEFAULT 0,
        rows_written INTEGER DEFAULT 0,
        bytes_written INTEGER DEFAULT 0,
        duration_ms INTEGER DEFAULT 0,
        note TEXT,
        error TEXT
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_ingest_runs_job_name ON ingest_runs (job_name, started_at DESC)",
    """
    CREATE TABLE IF NOT EXISTS http_cache (
        cache_key TEXT PRIMARY KEY,
        body BLOB NOT NULL,
        fetched_at TEXT NOT NULL,
        ttl_seconds INTEGER NOT NULL
    )
    """,
]


async def init_db() -> None:
    """Create the operational SQLite tables if they don't exist."""
    engine = get_engine()
    async with engine.begin() as conn:
        for ddl in SCHEMA_DDL:
            await conn.execute(text(ddl))
    log.info("db.init.complete")


# ─── DuckDB ──────────────────────────────────────────────────────────
# DuckDB is single-process; we keep one persistent connection on disk.

_duck: duckdb.DuckDBPyConnection | None = None


def get_duckdb() -> duckdb.DuckDBPyConnection:
    global _duck
    if _duck is None:
        ensure_dirs()
        settings = get_settings()
        _duck = duckdb.connect(settings.duckdb_path)
        # Predictable timestamp parsing for our Parquet/CSV imports.
        _duck.execute("SET TimeZone='UTC'")
    return _duck


def close_duckdb() -> None:
    global _duck
    if _duck is not None:
        _duck.close()
        _duck = None
