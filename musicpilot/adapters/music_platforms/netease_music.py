from __future__ import annotations

import asyncio
import json
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Any, cast

import httpx

from musicpilot.ports.discovery import (
    DiscoveryChartItem,
    DiscoveryChartPage,
    DiscoveryItemDetail,
    DiscoveryResourceType,
    DiscoveryTrack,
)

NETEASE_MUSIC_URL = "https://music.163.com"
NETEASE_HOT_SONGS_PLAYLIST_ID = "3778678"


class NeteaseMusicDiscoveryError(RuntimeError):
    pass


class NeteaseMusicResourceNotFound(NeteaseMusicDiscoveryError):
    pass


class NeteaseMusicDiscoveryAdapter:
    def __init__(
        self,
        client: httpx.AsyncClient | None = None,
        proxy_loader: Callable[[], Awaitable[str | None]] | None = None,
    ) -> None:
        self._client = client or httpx.AsyncClient(
            base_url=NETEASE_MUSIC_URL,
            timeout=30,
            follow_redirects=True,
            trust_env=False,
            headers=_headers(),
        )
        self._owns_client = client is None
        self._proxy_loader = proxy_loader
        self._proxy_url: str | None = None
        self._proxy_client: httpx.AsyncClient | None = None
        self._proxy_client_lock = asyncio.Lock()

    async def close(self) -> None:
        if self._proxy_client is not None:
            await self._proxy_client.aclose()
            self._proxy_client = None
            self._proxy_url = None
        if self._owns_client:
            await self._client.aclose()

    async def chart(
        self,
        resource_type: DiscoveryResourceType,
        *,
        offset: int = 0,
        limit: int = 20,
    ) -> DiscoveryChartPage:
        if resource_type == "songs":
            return await self._song_chart(offset, limit)
        if resource_type == "albums":
            return await self._album_chart(offset, limit)
        if resource_type == "playlists":
            return await self._playlist_chart(offset, limit)
        raise ValueError(f"Unsupported Netease Music resource type: {resource_type}")

    async def detail(
        self,
        resource_type: DiscoveryResourceType,
        item_id: str,
    ) -> DiscoveryItemDetail:
        if resource_type == "songs":
            return await self._song_detail(item_id)
        if resource_type == "albums":
            return await self._album_detail(item_id)
        if resource_type == "playlists":
            return await self._playlist_detail(item_id)
        raise ValueError(f"Unsupported Netease Music resource type: {resource_type}")

    async def _song_chart(self, offset: int, limit: int) -> DiscoveryChartPage:
        payload = await self._get_json(
            "/api/playlist/detail",
            params={"id": NETEASE_HOT_SONGS_PLAYLIST_ID},
        )
        playlist = _mapping(payload.get("result"))
        tracks = _list(playlist.get("tracks"))
        bounded_limit = max(1, min(limit, 50))
        raw_items = tracks[offset : offset + bounded_limit]
        items: list[DiscoveryChartItem] = []
        for rank, raw in enumerate(raw_items, start=offset + 1):
            track = _mapping(raw)
            item_id = _optional_string(track.get("id"))
            name = _optional_string(track.get("name"))
            if not item_id or not name:
                continue
            album = _track_album(track)
            items.append(
                DiscoveryChartItem(
                    id=item_id,
                    resource_type="songs",
                    rank=rank,
                    name=name,
                    artist_name=_artist_names(track),
                    artwork_url=_https_url(album.get("picUrl")),
                    release_date=_timestamp_date(
                        album.get("publishTime") or track.get("publishTime")
                    ),
                )
            )
        next_offset = offset + len(raw_items)
        has_more = next_offset < len(tracks)
        return DiscoveryChartPage(
            items=tuple(items),
            next_offset=next_offset if has_more else None,
            has_more=has_more,
        )

    async def _album_chart(self, offset: int, limit: int) -> DiscoveryChartPage:
        bounded_limit = max(1, min(limit, 50))
        payload = await self._get_json(
            "/api/album/new",
            params={
                "area": "ALL",
                "limit": bounded_limit,
                "offset": offset,
                "total": "true",
            },
        )
        raw_items = _list(payload.get("albums"))
        items: list[DiscoveryChartItem] = []
        for rank, raw in enumerate(raw_items, start=offset + 1):
            album = _mapping(raw)
            item_id = _optional_string(album.get("id"))
            name = _optional_string(album.get("name"))
            if not item_id or not name:
                continue
            items.append(
                DiscoveryChartItem(
                    id=item_id,
                    resource_type="albums",
                    rank=rank,
                    name=name,
                    artist_name=_artist_names(album),
                    artwork_url=_https_url(album.get("picUrl")),
                    release_date=_timestamp_date(album.get("publishTime")),
                )
            )
        next_offset = offset + len(raw_items)
        total = _optional_int(payload.get("total"))
        has_more = next_offset < total if total is not None else len(raw_items) == bounded_limit
        return DiscoveryChartPage(
            items=tuple(items),
            next_offset=next_offset if has_more else None,
            has_more=has_more,
        )

    async def _playlist_chart(self, offset: int, limit: int) -> DiscoveryChartPage:
        bounded_limit = max(1, min(limit, 50))
        payload = await self._get_json(
            "/api/playlist/list",
            params={
                "cat": "全部",
                "order": "hot",
                "limit": bounded_limit,
                "offset": offset,
            },
        )
        raw_items = _list(payload.get("playlists"))
        items: list[DiscoveryChartItem] = []
        for rank, raw in enumerate(raw_items, start=offset + 1):
            playlist = _mapping(raw)
            item_id = _optional_string(playlist.get("id"))
            name = _optional_string(playlist.get("name"))
            if not item_id or not name:
                continue
            items.append(
                DiscoveryChartItem(
                    id=item_id,
                    resource_type="playlists",
                    rank=rank,
                    name=name,
                    artist_name=_optional_string(
                        _mapping(playlist.get("creator")).get("nickname")
                    ),
                    artwork_url=_https_url(playlist.get("coverImgUrl")),
                    playcount=_optional_int(playlist.get("playCount")),
                )
            )
        next_offset = offset + len(raw_items)
        more = payload.get("more")
        has_more = bool(more) if isinstance(more, bool) else len(raw_items) == bounded_limit
        return DiscoveryChartPage(
            items=tuple(items),
            next_offset=next_offset if has_more else None,
            has_more=has_more,
        )

    async def _song_detail(self, item_id: str) -> DiscoveryItemDetail:
        numeric_id = _numeric_id(item_id)
        payload = await self._get_json(
            "/api/song/detail",
            params={"ids": json.dumps([numeric_id])},
        )
        songs = _list(payload.get("songs"))
        track = _mapping(songs[0]) if songs else {}
        if not track or _optional_int(track.get("id")) is None:
            raise NeteaseMusicResourceNotFound("网易云音乐歌曲不存在。")
        album = _track_album(track)
        return DiscoveryItemDetail(
            id=_optional_string(track.get("id")) or item_id,
            resource_type="songs",
            name=_optional_string(track.get("name")) or item_id,
            artist_name=_artist_names(track),
            album_name=_optional_string(album.get("name")),
            artwork_url=_https_url(album.get("picUrl")),
            external_url=f"https://music.163.com/song?id={numeric_id}",
            release_date=_timestamp_date(
                album.get("publishTime") or track.get("publishTime")
            ),
            duration_seconds=_millis_to_seconds(track.get("duration") or track.get("dt")),
        )

    async def _album_detail(self, item_id: str) -> DiscoveryItemDetail:
        numeric_id = _numeric_id(item_id)
        payload = await self._get_json(f"/api/v1/album/{numeric_id}")
        album = _mapping(payload.get("album"))
        if not album or _optional_int(album.get("id")) is None:
            raise NeteaseMusicResourceNotFound("网易云音乐专辑不存在。")
        tracks = _tracks(payload.get("songs"))
        return DiscoveryItemDetail(
            id=_optional_string(album.get("id")) or item_id,
            resource_type="albums",
            name=_optional_string(album.get("name")) or item_id,
            artist_name=_artist_names(album),
            description=_optional_string(album.get("description") or album.get("briefDesc")),
            artwork_url=_https_url(album.get("picUrl")),
            external_url=f"https://music.163.com/album?id={numeric_id}",
            release_date=_timestamp_date(album.get("publishTime")),
            genres=_string_values(album.get("tags")),
            track_count=_optional_int(album.get("size")) or len(tracks),
            tracks=tracks,
        )

    async def _playlist_detail(self, item_id: str) -> DiscoveryItemDetail:
        numeric_id = _numeric_id(item_id)
        payload = await self._post_json(
            "/api/v6/playlist/detail",
            data={"id": str(numeric_id), "n": "1000", "s": "0"},
        )
        playlist = _mapping(payload.get("playlist"))
        if not playlist or _optional_int(playlist.get("id")) is None:
            raise NeteaseMusicResourceNotFound("网易云音乐歌单不存在。")
        track_ids = [
            item_id
            for raw in _list(playlist.get("trackIds"))
            if (item_id := _optional_int(_mapping(raw).get("id"))) is not None
        ]
        raw_tracks = (
            await self._track_details(track_ids)
            if track_ids
            else [_mapping(raw) for raw in _list(playlist.get("tracks"))]
        )
        tracks = _tracks(raw_tracks)
        return DiscoveryItemDetail(
            id=_optional_string(playlist.get("id")) or item_id,
            resource_type="playlists",
            name=_optional_string(playlist.get("name")) or item_id,
            artist_name=_optional_string(
                _mapping(playlist.get("creator")).get("nickname")
            ),
            description=_optional_string(playlist.get("description")),
            artwork_url=_https_url(playlist.get("coverImgUrl")),
            external_url=f"https://music.163.com/playlist?id={numeric_id}",
            genres=_string_values(playlist.get("tags")),
            track_count=_optional_int(playlist.get("trackCount")) or len(tracks),
            playcount=_optional_int(playlist.get("playCount")),
            tracks=tracks,
        )

    async def _track_details(self, track_ids: list[int]) -> list[dict[str, Any]]:
        tracks: list[dict[str, Any]] = []
        for offset in range(0, len(track_ids), 500):
            ids = track_ids[offset : offset + 500]
            payload = await self._post_json(
                "https://interface3.music.163.com/api/v3/song/detail",
                data={"c": json.dumps([{"id": item, "v": 0} for item in ids])},
            )
            tracks.extend(_mapping(raw) for raw in _list(payload.get("songs")))
        return tracks

    async def _get_json(self, url: str, **kwargs: Any) -> dict[str, Any]:
        return await self._request_json("GET", url, **kwargs)

    async def _post_json(self, url: str, **kwargs: Any) -> dict[str, Any]:
        return await self._request_json("POST", url, **kwargs)

    async def _request_json(self, method: str, url: str, **kwargs: Any) -> dict[str, Any]:
        try:
            response = await self._client.request(method, url, **kwargs)
        except httpx.TransportError:
            proxy_client = await self._proxy_fallback_client()
            if proxy_client is None:
                raise
            response = await proxy_client.request(method, url, **kwargs)
        response.raise_for_status()
        try:
            payload = response.json()
        except ValueError as exc:
            raise NeteaseMusicDiscoveryError("网易云音乐接口响应格式无效。") from exc
        if not isinstance(payload, dict):
            raise NeteaseMusicDiscoveryError("网易云音乐接口响应格式无效。")
        code = _optional_int(payload.get("code"))
        if code not in {None, 200}:
            raise NeteaseMusicDiscoveryError(f"网易云音乐接口返回错误：{code}")
        return cast(dict[str, Any], payload)

    async def _proxy_fallback_client(self) -> httpx.AsyncClient | None:
        proxy_url = await self._proxy_loader() if self._proxy_loader is not None else None
        if not proxy_url:
            return None
        if self._proxy_client is not None and self._proxy_url == proxy_url:
            return self._proxy_client
        async with self._proxy_client_lock:
            if self._proxy_client is None or self._proxy_url != proxy_url:
                previous_client = self._proxy_client
                self._proxy_client = httpx.AsyncClient(
                    base_url=NETEASE_MUSIC_URL,
                    timeout=30,
                    follow_redirects=True,
                    proxy=proxy_url,
                    trust_env=False,
                    headers=_headers(),
                )
                self._proxy_url = proxy_url
                if previous_client is not None:
                    await previous_client.aclose()
        return self._proxy_client


def _tracks(value: object) -> tuple[DiscoveryTrack, ...]:
    tracks: list[DiscoveryTrack] = []
    for position, raw in enumerate(_list(value), start=1):
        item = _mapping(raw)
        item_id = _optional_string(item.get("id"))
        name = _optional_string(item.get("name"))
        if not item_id or not name:
            continue
        album = _track_album(item)
        tracks.append(
            DiscoveryTrack(
                id=item_id,
                position=position,
                name=name,
                artist_name=_artist_names(item),
                album_name=_optional_string(album.get("name")),
                artwork_url=_https_url(album.get("picUrl")),
                duration_seconds=_millis_to_seconds(
                    item.get("dt") or item.get("duration")
                ),
            )
        )
    return tuple(tracks)


def _track_album(track: dict[str, Any]) -> dict[str, Any]:
    return _mapping(track.get("al") or track.get("album"))


def _artist_names(value: dict[str, Any]) -> str | None:
    artists = value.get("ar") or value.get("artists")
    if not artists:
        artist = value.get("artist")
        artists = [artist] if isinstance(artist, dict) else []
    names = [
        name
        for raw in _list(artists)
        if (name := _optional_string(_mapping(raw).get("name")))
    ]
    return " / ".join(names) or None


def _string_values(value: object) -> tuple[str, ...]:
    if isinstance(value, str):
        return tuple(part.strip() for part in value.split(";") if part.strip())
    return tuple(text for raw in _list(value) if (text := _optional_string(raw)))


def _timestamp_date(value: object) -> str | None:
    timestamp = _optional_int(value)
    if not timestamp:
        return None
    try:
        return datetime.fromtimestamp(timestamp / 1000, UTC).date().isoformat()
    except (OSError, OverflowError, ValueError):
        return None


def _millis_to_seconds(value: object) -> int | None:
    millis = _optional_int(value)
    if millis is None:
        return None
    return int(millis / 1000) if millis > 10_000 else millis


def _https_url(value: object) -> str | None:
    url = _optional_string(value)
    if not url:
        return None
    if url.startswith("//"):
        return f"https:{url}"
    if url.startswith("http://"):
        return url.replace("http://", "https://", 1)
    return url


def _numeric_id(value: str) -> int:
    try:
        return int(value)
    except ValueError as exc:
        raise NeteaseMusicResourceNotFound("网易云音乐资源 ID 无效。") from exc


def _mapping(value: object) -> dict[str, Any]:
    return cast(dict[str, Any], value) if isinstance(value, dict) else {}


def _list(value: object) -> list[Any]:
    return cast(list[Any], value) if isinstance(value, list) else []


def _optional_string(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _optional_int(value: object) -> int | None:
    if value is None:
        return None
    try:
        return int(float(str(value).strip()))
    except (TypeError, ValueError):
        return None


def _headers() -> dict[str, str]:
    return {
        "Referer": "https://music.163.com/",
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/145.0 Safari/537.36"
        ),
    }
