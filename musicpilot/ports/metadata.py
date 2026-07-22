from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol


@dataclass(frozen=True, slots=True)
class TrackMetadata:
    title: str
    artist: str | None = None
    album: str | None = None
    album_artist: str | None = None
    year: int | None = None
    track_number: int | None = None
    lyrics: str | None = None
    cover_url: str | None = None
    has_cover: bool = False
    extra: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class MediaCandidate:
    title: str
    artist: str | None = None
    album: str | None = None
    release_date: str | None = None
    cover_url: str | None = None
    source: str = ""
    external_id: str = ""


class MetadataProvider(Protocol):
    @property
    def name(self) -> str: ...

    async def lookup(self, *, title: str, artist: str | None = None) -> TrackMetadata | None: ...

    async def search_metadata(
        self,
        *,
        title: str,
        artist: str | None = None,
        limit: int = 5,
    ) -> tuple[TrackMetadata, ...]: ...
