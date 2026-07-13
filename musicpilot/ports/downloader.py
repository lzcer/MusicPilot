from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Protocol


class DownloadState(StrEnum):
    QUEUED = "queued"
    DOWNLOADING = "downloading"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class DownloadStatus:
    torrent_hash: str
    name: str
    state: DownloadState
    progress: float
    save_path: Path | None = None
    content_path: Path | None = None
    tags: tuple[str, ...] = ()
    size_bytes: int | None = None


@dataclass(frozen=True, slots=True)
class TorrentFile:
    path: Path
    size: int = 0
    progress: float = 0.0


class Downloader(Protocol):
    @property
    def name(self) -> str: ...

    async def add_torrent(self, torrent_url: str, *, category: str) -> str: ...

    async def add_torrent_file(
        self,
        torrent_data: bytes,
        *,
        filename: str,
        category: str,
    ) -> str: ...

    async def get_status(self, torrent_hash: str) -> DownloadStatus: ...

    async def list_files(self, torrent_hash: str) -> tuple[TorrentFile, ...]: ...

    async def delete_torrent(self, torrent_hash: str, *, delete_files: bool) -> None: ...

    async def list_statuses(
        self,
        torrent_hashes: tuple[str, ...] = (),
    ) -> tuple[DownloadStatus, ...]: ...

    async def list_downloading_by_tag(self, tag: str) -> tuple[DownloadStatus, ...]: ...

    async def close(self) -> None: ...
