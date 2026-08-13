from __future__ import annotations

import asyncio
import base64
import json
import re
import time
from collections.abc import Awaitable, Callable
from typing import Any, cast
from urllib.parse import urljoin

import httpx

from musicpilot.ports.discovery import (
    DiscoveryChartItem,
    DiscoveryChartPage,
    DiscoveryItemDetail,
    DiscoveryResourceType,
    DiscoveryTrack,
)

APPLE_MUSIC_WEB_ORIGIN = "https://music.apple.com"
APPLE_MUSIC_CATALOG_ORIGIN = "https://amp-api.music.apple.com"
APPLE_MUSIC_RSS_ORIGIN = "https://rss.marketingtools.apple.com"
APPLE_MUSIC_STOREFRONT = "cn"


class AppleMusicDiscoveryError(RuntimeError):
    pass


class AppleMusicResourceNotFound(AppleMusicDiscoveryError):
    pass


class AppleMusicWebTokenProvider:
    def __init__(self, client: httpx.AsyncClient) -> None:
        self._client = client
        self._token: str | None = None
        self._expires_at = 0

    async def token(self, *, force_refresh: bool = False) -> str:
        if (
            not force_refresh
            and self._token
            and self._expires_at > int(time.time()) + 300
        ):
            return self._token
        response = await self._client.get(
            APPLE_MUSIC_WEB_ORIGIN,
            params={"l": "en-US"},
            headers={"User-Agent": apple_music_browser_user_agent()},
        )
        response.raise_for_status()
        asset_match = re.search(r'/(assets/index[~-][^/" ]+\.js)', response.text)
        if not asset_match:
            raise AppleMusicDiscoveryError("无法定位 Apple Music Web 入口脚本。")
        script_response = await self._client.get(
            f"{APPLE_MUSIC_WEB_ORIGIN}/{asset_match.group(1)}",
            headers={"User-Agent": apple_music_browser_user_agent()},
        )
        script_response.raise_for_status()
        token_match = re.search(
            r"(eyJ[A-Za-z0-9_-]+\.eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+)",
            script_response.text,
        )
        if not token_match:
            raise AppleMusicDiscoveryError("无法获取 Apple Music Web developer token。")
        self._token = token_match.group(1)
        self._expires_at = jwt_expiration(self._token) or int(time.time()) + 900
        return self._token

    def copy_cache_from(self, other: AppleMusicWebTokenProvider) -> None:
        if other._token and other._expires_at > self._expires_at:
            self._token = other._token
            self._expires_at = other._expires_at


class AppleMusicDiscoveryAdapter:
    def __init__(
        self,
        client: httpx.AsyncClient | None = None,
        token_provider: AppleMusicWebTokenProvider | None = None,
        proxy_loader: Callable[[], Awaitable[str | None]] | None = None,
    ) -> None:
        self._client = client or httpx.AsyncClient(
            timeout=30,
            follow_redirects=True,
            trust_env=False,
        )
        self._owns_client = client is None
        self._token_provider = token_provider or AppleMusicWebTokenProvider(self._client)
        self._proxy_loader = proxy_loader
        self._proxy_url: str | None = None
        self._proxy_client: httpx.AsyncClient | None = None
        self._proxy_adapter: AppleMusicDiscoveryAdapter | None = None
        self._proxy_client_lock = asyncio.Lock()

    async def close(self) -> None:
        if self._proxy_client is not None:
            await self._proxy_client.aclose()
            self._proxy_client = None
            self._proxy_adapter = None
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
        try:
            return await self._chart(resource_type, offset=offset, limit=limit)
        except httpx.TransportError:
            proxy_adapter = await self._proxy_fallback()
            if proxy_adapter is None:
                raise
            return await proxy_adapter._chart(resource_type, offset=offset, limit=limit)

    async def _chart(
        self,
        resource_type: DiscoveryResourceType,
        *,
        offset: int,
        limit: int,
    ) -> DiscoveryChartPage:
        if resource_type not in {"songs", "albums", "playlists"}:
            raise ValueError(f"Unsupported Apple Music resource type: {resource_type}")
        bounded_limit = max(1, min(limit, 50))
        response = await self._client.get(
            f"{APPLE_MUSIC_RSS_ORIGIN}/api/v2/{APPLE_MUSIC_STOREFRONT}/music/"
            f"most-played/50/{resource_type}.json"
        )
        response.raise_for_status()
        try:
            payload = response.json()
            results = payload["feed"]["results"]
        except (KeyError, TypeError, ValueError) as exc:
            raise AppleMusicDiscoveryError("Apple Music 榜单响应格式无效。") from exc
        if not isinstance(results, list):
            raise AppleMusicDiscoveryError("Apple Music 榜单响应格式无效。")
        page_results = results[offset : offset + bounded_limit]
        items = [
            self._chart_item(item, resource_type, rank)
            for rank, item in enumerate(page_results, start=offset + 1)
            if isinstance(item, dict)
        ]
        parsed = tuple(item for item in items if item is not None)
        next_offset = offset + len(page_results)
        has_more = next_offset < len(results)
        return DiscoveryChartPage(
            items=parsed,
            next_offset=next_offset if has_more else None,
            has_more=has_more,
        )

    async def detail(
        self,
        resource_type: DiscoveryResourceType,
        item_id: str,
    ) -> DiscoveryItemDetail:
        try:
            return await self._detail(resource_type, item_id)
        except httpx.TransportError:
            proxy_adapter = await self._proxy_fallback()
            if proxy_adapter is None:
                raise
            item = await proxy_adapter._detail(resource_type, item_id)
            self._token_provider.copy_cache_from(proxy_adapter._token_provider)
            return item

    async def _detail(
        self,
        resource_type: DiscoveryResourceType,
        item_id: str,
    ) -> DiscoveryItemDetail:
        if resource_type not in {"songs", "albums", "playlists"}:
            raise ValueError(f"Unsupported Apple Music resource type: {resource_type}")
        resource = await self._catalog_resource(resource_type, item_id)
        attributes = _mapping(resource.get("attributes"))
        tracks: tuple[DiscoveryTrack, ...] = ()
        if resource_type in {"albums", "playlists"}:
            tracks = await self._relationship_tracks(resource)
        track_count = _optional_int(attributes.get("trackCount"))
        if track_count is None and resource_type in {"albums", "playlists"}:
            track_count = len(tracks)
        return DiscoveryItemDetail(
            id=str(resource.get("id") or item_id),
            resource_type=resource_type,
            name=_optional_string(attributes.get("name")) or item_id,
            artist_name=_optional_string(
                attributes.get("artistName") or attributes.get("curatorName")
            ),
            album_name=_optional_string(attributes.get("albumName")),
            description=apple_music_description(attributes.get("description")),
            artwork_url=apple_music_artwork_url(attributes.get("artwork")),
            external_url=_optional_string(attributes.get("url")),
            release_date=_optional_string(attributes.get("releaseDate")),
            genres=_string_tuple(attributes.get("genreNames")),
            duration_seconds=_millis_to_seconds(attributes.get("durationInMillis")),
            track_count=track_count,
            tracks=tracks,
        )

    async def _proxy_fallback(self) -> AppleMusicDiscoveryAdapter | None:
        proxy_url = await self._proxy_loader() if self._proxy_loader is not None else None
        if not proxy_url:
            return None
        if self._proxy_adapter is not None and self._proxy_url == proxy_url:
            self._proxy_adapter._token_provider.copy_cache_from(self._token_provider)
            return self._proxy_adapter
        async with self._proxy_client_lock:
            if self._proxy_adapter is None or self._proxy_url != proxy_url:
                previous_client = self._proxy_client
                self._proxy_client = httpx.AsyncClient(
                    timeout=30,
                    follow_redirects=True,
                    proxy=proxy_url,
                    trust_env=False,
                )
                proxy_token_provider = AppleMusicWebTokenProvider(self._proxy_client)
                proxy_token_provider.copy_cache_from(self._token_provider)
                self._proxy_adapter = AppleMusicDiscoveryAdapter(
                    self._proxy_client,
                    proxy_token_provider,
                )
                self._proxy_url = proxy_url
                if previous_client is not None:
                    await previous_client.aclose()
        return self._proxy_adapter

    async def _catalog_resource(
        self,
        resource_type: DiscoveryResourceType,
        item_id: str,
    ) -> dict[str, Any]:
        params: dict[str, str | int] = {}
        if resource_type in {"albums", "playlists"}:
            params = {"include": "tracks", "limit[tracks]": 100}
        response = await self._catalog_get(
            f"/v1/catalog/{APPLE_MUSIC_STOREFRONT}/{resource_type}/{item_id}",
            params=params,
        )
        if response.status_code == 404:
            raise AppleMusicResourceNotFound("Apple Music 资源不存在。")
        response.raise_for_status()
        try:
            data = response.json()["data"]
            resource = data[0]
        except (KeyError, IndexError, TypeError, ValueError) as exc:
            raise AppleMusicDiscoveryError("Apple Music 详情响应格式无效。") from exc
        if not isinstance(resource, dict):
            raise AppleMusicDiscoveryError("Apple Music 详情响应格式无效。")
        return cast(dict[str, Any], resource)

    async def _relationship_tracks(
        self,
        resource: dict[str, Any],
    ) -> tuple[DiscoveryTrack, ...]:
        relationship = _mapping(_mapping(resource.get("relationships")).get("tracks"))
        raw_tracks = relationship.get("data")
        tracks = list(raw_tracks) if isinstance(raw_tracks, list) else []
        next_url = _optional_string(relationship.get("next"))
        visited: set[str] = set()
        while next_url and next_url not in visited:
            visited.add(next_url)
            response = await self._catalog_get(next_url)
            response.raise_for_status()
            try:
                page = response.json()
            except ValueError as exc:
                raise AppleMusicDiscoveryError("Apple Music 曲目分页响应格式无效。") from exc
            page_tracks = page.get("data") if isinstance(page, dict) else None
            if isinstance(page_tracks, list):
                tracks.extend(page_tracks)
            next_url = _optional_string(page.get("next")) if isinstance(page, dict) else None
        parsed = [
            self._track(item, position)
            for position, item in enumerate(tracks, start=1)
            if isinstance(item, dict)
        ]
        return tuple(item for item in parsed if item is not None)

    async def _catalog_get(
        self,
        path: str,
        *,
        params: dict[str, str | int] | None = None,
    ) -> httpx.Response:
        token = await self._token_provider.token()
        response = await self._client.get(
            urljoin(APPLE_MUSIC_CATALOG_ORIGIN, path),
            headers=apple_music_headers(token),
            params=params,
        )
        if response.status_code == 401:
            token = await self._token_provider.token(force_refresh=True)
            response = await self._client.get(
                urljoin(APPLE_MUSIC_CATALOG_ORIGIN, path),
                headers=apple_music_headers(token),
                params=params,
            )
        return response

    @staticmethod
    def _chart_item(
        item: dict[str, Any],
        resource_type: DiscoveryResourceType,
        rank: int,
    ) -> DiscoveryChartItem | None:
        item_id = _optional_string(item.get("id"))
        name = _optional_string(item.get("name"))
        if not item_id or not name:
            return None
        return DiscoveryChartItem(
            id=item_id,
            resource_type=resource_type,
            rank=rank,
            name=name,
            artist_name=_optional_string(item.get("artistName")),
            artwork_url=_optional_string(item.get("artworkUrl100")),
            release_date=_optional_string(item.get("releaseDate")),
            genres=_rss_genres(item.get("genres")),
        )

    @staticmethod
    def _track(item: dict[str, Any], position: int) -> DiscoveryTrack | None:
        attributes = _mapping(item.get("attributes"))
        item_id = _optional_string(item.get("id"))
        name = _optional_string(attributes.get("name"))
        if not item_id or not name:
            return None
        return DiscoveryTrack(
            id=item_id,
            position=position,
            name=name,
            artist_name=_optional_string(attributes.get("artistName")),
            album_name=_optional_string(attributes.get("albumName")),
            artwork_url=apple_music_artwork_url(attributes.get("artwork")),
            duration_seconds=_millis_to_seconds(attributes.get("durationInMillis")),
        )


def apple_music_headers(token: str) -> dict[str, str]:
    return {
        "Accept": "application/json",
        "Authorization": f"Bearer {token}",
        "Origin": APPLE_MUSIC_WEB_ORIGIN,
        "Referer": f"{APPLE_MUSIC_WEB_ORIGIN}/",
        "User-Agent": apple_music_browser_user_agent(),
    }


def apple_music_browser_user_agent() -> str:
    return (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36"
    )


def apple_music_artwork_url(value: object, *, size: int = 800) -> str | None:
    if not isinstance(value, dict):
        return None
    url = _optional_string(value.get("url"))
    if not url:
        return None
    return url.replace("{w}", str(size)).replace("{h}", str(size)).replace("{f}", "jpg")


def apple_music_description(value: object) -> str | None:
    if isinstance(value, dict):
        return _optional_string(value.get("standard") or value.get("short"))
    return _optional_string(value)


def jwt_expiration(token: str) -> int | None:
    try:
        payload = token.split(".")[1]
        padding = "=" * (-len(payload) % 4)
        decoded = json.loads(base64.urlsafe_b64decode(payload + padding))
        return int(decoded.get("exp")) if decoded.get("exp") else None
    except (IndexError, TypeError, ValueError, json.JSONDecodeError):
        return None


def _mapping(value: object) -> dict[str, Any]:
    return cast(dict[str, Any], value) if isinstance(value, dict) else {}


def _optional_string(value: object) -> str | None:
    text = str(value).strip() if value is not None else ""
    return text or None


def _optional_int(value: object) -> int | None:
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _millis_to_seconds(value: object) -> int | None:
    millis = _optional_int(value)
    return round(millis / 1000) if millis is not None else None


def _string_tuple(value: object) -> tuple[str, ...]:
    if not isinstance(value, list):
        return ()
    return tuple(text for item in value if (text := _optional_string(item)))


def _rss_genres(value: object) -> tuple[str, ...]:
    if not isinstance(value, list):
        return ()
    genres: list[str] = []
    for item in value:
        name = _optional_string(item.get("name")) if isinstance(item, dict) else None
        if name:
            genres.append(name)
    return tuple(genres)
