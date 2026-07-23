from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass(frozen=True, slots=True)
class MediaServerTrack:
    id: str
    title: str
    artist: str | None = None
    album: str | None = None
    duration: int | None = None
    size: int | None = None
    year: int | None = None
    suffix: str | None = None
    path: str | None = None
    content_type: str | None = None
    raw_payload: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class MediaServerAlbum:
    id: str
    name: str
    album_artist: str | None = None
    musicbrainz_album_id: str | None = None
    album_version: str | None = None
    release_date: str | None = None
    songs: tuple[MediaServerTrack, ...] = ()
    raw_payload: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class MediaServerPlaylistSyncResult:
    playlist_id: str | None
    synced_count: int
    mode: str = "updated"


class MediaServerClient(Protocol):
    @property
    def name(self) -> str: ...

    async def ping(self) -> None: ...

    async def list_tracks(self) -> list[MediaServerTrack]: ...

    async def get_album(self, album_id: str) -> MediaServerAlbum | None: ...

    async def start_scan(self) -> None: ...

    async def sync_playlist(
        self,
        *,
        name: str,
        song_ids: list[str],
        public: bool = False,
    ) -> MediaServerPlaylistSyncResult: ...
