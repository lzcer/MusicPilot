from __future__ import annotations

import json
import zipfile
from datetime import UTC, date, datetime
from io import BytesIO
from pathlib import Path
from typing import Any, BinaryIO

from sqlalchemy import DateTime, Integer, delete, insert, select, text
from sqlalchemy.exc import SQLAlchemyError

from musicpilot.infra.db.models import Base
from musicpilot.infra.db.session import Database

EXPORT_FORMAT_VERSION = 1
EXPORT_MANIFEST_NAME = "manifest.json"
EXPORT_DATA_NAME = "data.json"
EXPORT_BATCH_SIZE = 500


class DatabaseMigrationError(ValueError):
    pass


class DatabaseMigrationService:
    def __init__(self, database: Database) -> None:
        self.database = database

    async def export_zip(self) -> bytes:
        archive = BytesIO()
        await self._write_export_zip(archive)
        return archive.getvalue()

    async def export_zip_to_path(self, path: Path) -> None:
        await self._write_export_zip(path)

    async def _write_export_zip(self, target: Path | BytesIO) -> None:
        manifest = {
            "app": "MusicPilot",
            "format_version": EXPORT_FORMAT_VERSION,
            "exported_at": datetime.now(UTC).isoformat(),
            "tables": [table.name for table in _migration_tables()],
        }
        with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            zf.writestr(
                EXPORT_MANIFEST_NAME,
                json.dumps(manifest, ensure_ascii=False, indent=2),
            )
            with zf.open(EXPORT_DATA_NAME, "w") as data_file:
                await self._write_data_json(data_file)

    async def _write_data_json(self, data_file: BinaryIO) -> None:
        data_file.write(b"{")
        first_table = True
        async with self.database.engine.connect() as conn:
            for table in _migration_tables():
                if first_table:
                    first_table = False
                else:
                    data_file.write(b",")
                data_file.write(_json_bytes(table.name))
                data_file.write(b":[")
                first_row = True
                async with conn.stream(select(table)) as result:
                    async for partition in result.mappings().partitions(EXPORT_BATCH_SIZE):
                        for row in partition:
                            if first_row:
                                first_row = False
                            else:
                                data_file.write(b",")
                            data_file.write(
                                _json_bytes(
                                    {
                                        column.name: _serialize_value(row[column.name])
                                        for column in table.columns
                                    }
                                )
                            )
                data_file.write(b"]")
        data_file.write(b"}")

    async def import_zip(self, content: bytes) -> dict[str, int]:
        manifest, data = _read_export_zip(content)
        _validate_export_payload(manifest, data)
        table_by_name = {table.name: table for table in _migration_tables()}
        imported_counts: dict[str, int] = {}
        try:
            async with self.database.engine.begin() as conn:
                for table in reversed(_migration_tables()):
                    await conn.execute(delete(table))
                for table in _migration_tables():
                    rows = data.get(table.name, [])
                    prepared = [_prepare_row(table, row) for row in rows]
                    if prepared:
                        await conn.execute(insert(table), prepared)
                    imported_counts[table.name] = len(prepared)
                await _sync_postgresql_sequences(conn, table_by_name)
        except SQLAlchemyError as exc:
            raise DatabaseMigrationError(f"Database import failed: {exc}") from exc
        return imported_counts


def _migration_tables() -> list[Any]:
    return list(Base.metadata.sorted_tables)


def _read_export_zip(content: bytes) -> tuple[dict[str, Any], dict[str, list[dict[str, Any]]]]:
    try:
        with zipfile.ZipFile(BytesIO(content)) as zf:
            names = set(zf.namelist())
            if EXPORT_MANIFEST_NAME not in names or EXPORT_DATA_NAME not in names:
                raise DatabaseMigrationError(
                    "Import archive must contain manifest.json and data.json."
                )
            manifest = json.loads(zf.read(EXPORT_MANIFEST_NAME).decode("utf-8"))
            data = json.loads(zf.read(EXPORT_DATA_NAME).decode("utf-8"))
    except zipfile.BadZipFile as exc:
        raise DatabaseMigrationError("Import file is not a valid zip archive.") from exc
    except json.JSONDecodeError as exc:
        raise DatabaseMigrationError("Import archive contains invalid JSON.") from exc
    if not isinstance(manifest, dict) or not isinstance(data, dict):
        raise DatabaseMigrationError("Import archive format is invalid.")
    return manifest, data


def _validate_export_payload(
    manifest: dict[str, Any],
    data: dict[str, list[dict[str, Any]]],
) -> None:
    if manifest.get("format_version") != EXPORT_FORMAT_VERSION:
        raise DatabaseMigrationError("Import archive version is not supported.")
    known_tables = {table.name for table in _migration_tables()}
    manifest_tables = manifest.get("tables")
    if not isinstance(manifest_tables, list):
        raise DatabaseMigrationError("Import archive table manifest is invalid.")
    unknown_tables = set(manifest_tables) - known_tables
    if unknown_tables:
        names = ", ".join(sorted(unknown_tables))
        raise DatabaseMigrationError(f"Import archive contains unsupported tables: {names}")
    for table_name, rows in data.items():
        if table_name not in known_tables:
            raise DatabaseMigrationError(
                f"Import archive contains an unsupported table: {table_name}"
            )
        if not isinstance(rows, list):
            raise DatabaseMigrationError(f"Import archive table data is invalid: {table_name}")
        if not all(isinstance(row, dict) for row in rows):
            raise DatabaseMigrationError(f"Import archive table rows are invalid: {table_name}")


def _prepare_row(table: Any, row: dict[str, Any]) -> dict[str, Any]:
    column_by_name = {column.name: column for column in table.columns}
    unknown_columns = set(row) - set(column_by_name)
    if unknown_columns:
        names = ", ".join(sorted(unknown_columns))
        raise DatabaseMigrationError(
            f"Import archive contains unsupported columns: {table.name}.{names}"
        )
    return {
        column.name: _deserialize_value(column, row.get(column.name))
        for column in table.columns
        if column.name in row
    }


def _serialize_value(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    return value


def _json_bytes(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def _deserialize_value(column: Any, value: Any) -> Any:
    if value is None:
        return None
    if isinstance(column.type, DateTime) and isinstance(value, str):
        normalized = value.replace("Z", "+00:00")
        return datetime.fromisoformat(normalized)
    return value


async def _sync_postgresql_sequences(conn: Any, table_by_name: dict[str, Any]) -> None:
    if conn.dialect.name != "postgresql":
        return
    for table in table_by_name.values():
        integer_primary_keys = [
            column
            for column in table.primary_key.columns
            if isinstance(column.type, Integer)
        ]
        if len(integer_primary_keys) != 1:
            continue
        column = integer_primary_keys[0]
        sequence_result = await conn.execute(
            text("SELECT pg_get_serial_sequence(:table_name, :column_name)"),
            {"table_name": table.name, "column_name": column.name},
        )
        sequence_name = sequence_result.scalar_one_or_none()
        if not sequence_name:
            continue
        max_result = await conn.execute(
            text(f'SELECT COALESCE(MAX("{column.name}"), 0) FROM "{table.name}"')
        )
        max_id = int(max_result.scalar_one() or 0)
        await conn.execute(
            text("SELECT setval(:sequence_name, :value, :is_called)"),
            {
                "sequence_name": sequence_name,
                "value": max(max_id, 1),
                "is_called": max_id > 0,
            },
        )
