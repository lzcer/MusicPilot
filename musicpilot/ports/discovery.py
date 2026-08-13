from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal, Protocol

DiscoveryResourceType = Literal["songs", "albums", "playlists", "artists", "tags"]


@dataclass(frozen=True, slots=True)
class DiscoveryChartItem:
    id: str
    resource_type: DiscoveryResourceType
    rank: int
    name: str
    artist_name: str | None = None
    artwork_url: str | None = None
    release_date: str | None = None
    genres: tuple[str, ...] = ()
    listeners: int | None = None
    playcount: int | None = None


@dataclass(frozen=True, slots=True)
class DiscoveryChartPage:
    items: tuple[DiscoveryChartItem, ...]
    next_offset: int | None
    has_more: bool


@dataclass(frozen=True, slots=True)
class DiscoveryTrack:
    id: str
    position: int
    name: str
    artist_name: str | None = None
    album_name: str | None = None
    artwork_url: str | None = None
    duration_seconds: int | None = None


@dataclass(frozen=True, slots=True)
class DiscoveryItemDetail:
    id: str
    resource_type: DiscoveryResourceType
    name: str
    artist_name: str | None = None
    album_name: str | None = None
    description: str | None = None
    artwork_url: str | None = None
    external_url: str | None = None
    release_date: str | None = None
    genres: tuple[str, ...] = ()
    duration_seconds: int | None = None
    track_count: int | None = None
    listeners: int | None = None
    playcount: int | None = None
    tracks: tuple[DiscoveryTrack, ...] = field(default_factory=tuple)


class DiscoveryProvider(Protocol):
    async def chart(
        self,
        resource_type: DiscoveryResourceType,
        *,
        offset: int = 0,
        limit: int = 20,
    ) -> DiscoveryChartPage: ...

    async def detail(
        self,
        resource_type: DiscoveryResourceType,
        item_id: str,
    ) -> DiscoveryItemDetail: ...
