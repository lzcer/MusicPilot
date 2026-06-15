from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from sqlalchemy import event
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from musicpilot.infra.db.models import Base


class Database:
    def __init__(self, database_url: str) -> None:
        self.database_url = database_url
        if database_url.startswith("sqlite"):
            _ensure_sqlite_parent_dir(database_url)
        self.engine = create_async_engine(database_url, pool_pre_ping=True)
        self.session_factory = async_sessionmaker(self.engine, expire_on_commit=False)
        if database_url.startswith("sqlite"):
            _install_sqlite_pragmas(self.engine)

    async def create_all(self) -> None:
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    async def migrate_phase_one_schema(self) -> None:
        if not self.database_url.startswith("sqlite"):
            return
        async with self.engine.begin() as conn:
            await _add_sqlite_columns(
                conn,
                "torrent_records",
                {
                    "downloader_id": "VARCHAR(32)",
                    "media_metadata": "JSON NOT NULL DEFAULT '{}'",
                    "resource_payload": "JSON NOT NULL DEFAULT '{}'",
                    "selected_site_ids": "JSON NOT NULL DEFAULT '[]'",
                    "submitted_at": "DATETIME",
                    "download_started_at": "DATETIME",
                    "completed_at": "DATETIME",
                    "library_refreshed_at": "DATETIME",
                    "last_error": "TEXT",
                },
            )
            await _add_sqlite_columns(
                conn,
                "indexer_sites",
                {
                    "enabled": "BOOLEAN NOT NULL DEFAULT 1",
                },
            )

    async def dispose(self) -> None:
        await self.engine.dispose()

    @asynccontextmanager
    async def session(self) -> AsyncIterator[AsyncSession]:
        async with self.session_factory() as session:
            yield session


def _install_sqlite_pragmas(engine: AsyncEngine) -> None:
    @event.listens_for(engine.sync_engine, "connect")
    def set_sqlite_pragma(dbapi_connection: object, connection_record: object) -> None:
        del connection_record
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


def _ensure_sqlite_parent_dir(database_url: str) -> None:
    database = make_url(database_url).database
    if not database or database == ":memory:":
        return
    path = Path(database)
    if path.parent == Path("."):
        return
    path.parent.mkdir(parents=True, exist_ok=True)


async def dispose_engine(engine: AsyncEngine) -> None:
    await engine.dispose()


async def _add_sqlite_columns(
    conn: object,
    table: str,
    columns: dict[str, str],
) -> None:
    result = await conn.exec_driver_sql(f"PRAGMA table_info({table})")
    existing = {str(row[1]) for row in result.fetchall()}
    for name, definition in columns.items():
        if name not in existing:
            await conn.exec_driver_sql(f"ALTER TABLE {table} ADD COLUMN {name} {definition}")
