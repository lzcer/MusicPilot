from __future__ import annotations

import logging
import os
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from sqlalchemy import event
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from musicpilot.infra.db.models import Base

logger = logging.getLogger(__name__)
SQLITE_BUSY_TIMEOUT_SECONDS = float(os.getenv("MP_SQLITE_BUSY_TIMEOUT_SECONDS", "60"))
SLOW_SQL_OPERATION_SECONDS = float(os.getenv("MP_SLOW_SQL_OPERATION_SECONDS", "0.5"))


class Database:
    def __init__(self, database_url: str) -> None:
        self.database_url = database_url
        if database_url.startswith("sqlite"):
            _ensure_sqlite_parent_dir(database_url)
        connect_args = (
            {"timeout": SQLITE_BUSY_TIMEOUT_SECONDS}
            if database_url.startswith("sqlite")
            else {}
        )
        self.engine = create_async_engine(
            database_url,
            pool_pre_ping=True,
            connect_args=connect_args,
        )
        self.session_factory = async_sessionmaker(self.engine, expire_on_commit=False)
        if database_url.startswith("sqlite"):
            _install_sqlite_pragmas(self.engine)
            _install_sqlite_timing(engine=self.engine)

    async def create_all(self) -> None:
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    async def migrate_phase_one_schema(self) -> None:
        if not self.database_url.startswith("sqlite"):
            return
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
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
                "downloaders",
                {
                    "local_path": "TEXT NOT NULL DEFAULT ''",
                },
            )
            await _add_sqlite_columns(
                conn,
                "indexer_sites",
                {
                    "enabled": "BOOLEAN NOT NULL DEFAULT 1",
                    "use_proxy": "BOOLEAN NOT NULL DEFAULT 0",
                },
            )
            await _add_sqlite_columns(
                conn,
                "media_files",
                {
                    "status": "VARCHAR(64) NOT NULL DEFAULT 'success'",
                    "error_message": "TEXT",
                },
            )
            await _ensure_media_files_library_path_nullable(conn)
            await conn.exec_driver_sql(
                "UPDATE media_files SET library_path = NULL WHERE status != 'success'"
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
        cursor.execute(f"PRAGMA busy_timeout={int(SQLITE_BUSY_TIMEOUT_SECONDS * 1000)}")
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


def _install_sqlite_timing(*, engine: AsyncEngine) -> None:
    @event.listens_for(engine.sync_engine, "before_cursor_execute")
    def before_cursor_execute(
        conn: object,
        cursor: object,
        statement: str,
        parameters: object,
        context: Any,
        executemany: bool,
    ) -> None:
        del conn, cursor, statement, parameters, executemany
        context._musicpilot_query_started_at = time.perf_counter()

    @event.listens_for(engine.sync_engine, "after_cursor_execute")
    def after_cursor_execute(
        conn: object,
        cursor: object,
        statement: str,
        parameters: object,
        context: Any,
        executemany: bool,
    ) -> None:
        del conn, cursor, parameters, executemany
        started_at = getattr(context, "_musicpilot_query_started_at", None)
        if started_at is None:
            return
        elapsed_ms = (time.perf_counter() - started_at) * 1000
        if elapsed_ms < SLOW_SQL_OPERATION_SECONDS * 1000:
            return
        logger.warning(
            "Slow SQL operation: elapsed_ms=%.1f statement=%r",
            elapsed_ms,
            _compact_sql(statement),
        )


def _compact_sql(statement: str) -> str:
    return " ".join(statement.split())


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


async def _ensure_media_files_library_path_nullable(conn: object) -> None:
    result = await conn.exec_driver_sql("PRAGMA table_info(media_files)")
    columns = result.fetchall()
    if not columns:
        return
    library_path = next((row for row in columns if str(row[1]) == "library_path"), None)
    if library_path is None or int(library_path[3]) == 0:
        return
    await conn.exec_driver_sql("ALTER TABLE media_files RENAME TO media_files_old")
    await conn.exec_driver_sql(
        """
        CREATE TABLE media_files (
            id INTEGER NOT NULL,
            torrent_hash VARCHAR(64),
            source_path TEXT NOT NULL,
            library_path TEXT,
            title VARCHAR(512),
            artist VARCHAR(512),
            album VARCHAR(512),
            year INTEGER,
            track_number INTEGER,
            status VARCHAR(64) NOT NULL,
            error_message TEXT,
            metadata JSON NOT NULL,
            created_at DATETIME NOT NULL,
            updated_at DATETIME NOT NULL,
            PRIMARY KEY (id),
            UNIQUE (library_path)
        )
        """
    )
    await conn.exec_driver_sql(
        """
        INSERT INTO media_files (
            id,
            torrent_hash,
            source_path,
            library_path,
            title,
            artist,
            album,
            year,
            track_number,
            status,
            error_message,
            metadata,
            created_at,
            updated_at
        )
        SELECT
            id,
            torrent_hash,
            source_path,
            CASE WHEN status = 'success' THEN library_path ELSE NULL END,
            title,
            artist,
            album,
            year,
            track_number,
            status,
            error_message,
            metadata,
            created_at,
            updated_at
        FROM media_files_old
        """
    )
    await conn.exec_driver_sql("DROP TABLE media_files_old")
    await conn.exec_driver_sql(
        "CREATE INDEX ix_media_files_torrent_hash ON media_files (torrent_hash)"
    )
