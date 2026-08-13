from __future__ import annotations

import asyncio
import base64
import html
import json
import re
from collections.abc import Awaitable, Callable
from typing import Any, cast

import httpx

from musicpilot.ports.discovery import (
    DiscoveryChartItem,
    DiscoveryChartPage,
    DiscoveryItemDetail,
    DiscoveryResourceType,
    DiscoveryTrack,
)

LASTFM_API_URL = "https://ws.audioscrobbler.com/2.0/"
LASTFM_COUNTRY = "China"
LASTFM_DEFAULT_ARTWORK_ID = "2a96cbd8b46e442fc41c2b86b821562f"


class LastFmDiscoveryError(RuntimeError):
    pass


class LastFmNotConfigured(LastFmDiscoveryError):
    pass


class LastFmResourceNotFound(LastFmDiscoveryError):
    pass


class LastFmDiscoveryAdapter:
    def __init__(
        self,
        api_key_loader: Callable[[], Awaitable[str]],
        client: httpx.AsyncClient | None = None,
        proxy_loader: Callable[[], Awaitable[str | None]] | None = None,
    ) -> None:
        self._api_key_loader = api_key_loader
        self._proxy_loader = proxy_loader
        self._client = client or httpx.AsyncClient(
            timeout=30,
            follow_redirects=True,
            trust_env=False,
        )
        self._owns_client = client is None
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
        bounded_limit = max(1, min(limit, 50))
        page = offset // bounded_limit + 1
        if resource_type == "songs":
            payload = await self._request(
                "geo.getTopTracks",
                country=LASTFM_COUNTRY,
                limit=bounded_limit,
                page=page,
            )
            raw_items = _list_at(payload, "tracks", "track")
        elif resource_type == "artists":
            payload = await self._request(
                "chart.getTopArtists", limit=bounded_limit, page=page
            )
            raw_items = _list_at(payload, "artists", "artist")
        elif resource_type == "tags":
            payload = await self._request("chart.getTopTags", limit=50)
            all_items = _list_at(payload, "tags", "tag")
            raw_items = all_items[offset : offset + bounded_limit]
        else:
            raise ValueError(f"Unsupported Last.fm resource type: {resource_type}")
        parsed = [
            self._chart_item(item, resource_type, rank)
            for rank, item in enumerate(raw_items, start=offset + 1)
            if isinstance(item, dict)
        ]
        items = tuple(item for item in parsed if item is not None)
        parent = {"songs": "tracks", "artists": "artists", "tags": "tags"}[
            resource_type
        ]
        next_offset = offset + len(raw_items)
        if resource_type == "tags":
            has_more = next_offset < len(all_items)
        else:
            attributes = _mapping(_mapping(payload.get(parent)).get("@attr"))
            total_pages = _optional_int(attributes.get("totalPages"))
            total = _optional_int(attributes.get("total"))
            has_more = (
                page < total_pages
                if total_pages is not None
                else next_offset < total
                if total is not None
                else len(raw_items) == bounded_limit
            )
        return DiscoveryChartPage(
            items=items,
            next_offset=next_offset if has_more else None,
            has_more=has_more,
        )

    async def detail(
        self,
        resource_type: DiscoveryResourceType,
        item_id: str,
    ) -> DiscoveryItemDetail:
        identity = _decode_identity(item_id)
        if resource_type == "songs":
            return await self._track_detail(identity, item_id)
        if resource_type == "artists":
            return await self._artist_detail(identity, item_id)
        if resource_type == "tags":
            return await self._tag_detail(identity, item_id)
        raise ValueError(f"Unsupported Last.fm resource type: {resource_type}")

    async def configured(self) -> bool:
        return bool((await self._api_key_loader()).strip())

    async def _track_detail(
        self,
        identity: dict[str, str],
        item_id: str,
    ) -> DiscoveryItemDetail:
        params = _identity_params(identity, primary="track")
        payload = await self._request("track.getInfo", **params)
        track = _mapping(payload.get("track"))
        if not track:
            raise LastFmResourceNotFound("Last.fm track not found.")
        artist = _mapping(track.get("artist"))
        album = _mapping(track.get("album"))
        return DiscoveryItemDetail(
            id=item_id,
            resource_type="songs",
            name=_optional_string(track.get("name")) or identity.get("name", item_id),
            artist_name=_optional_string(artist.get("name")) or identity.get("artist"),
            album_name=_optional_string(album.get("title")),
            description=_wiki_summary(track.get("wiki")),
            artwork_url=_image_url(album.get("image")),
            genres=_tag_names(_mapping(track.get("toptags")).get("tag")),
            duration_seconds=_milliseconds_to_seconds(track.get("duration")),
            listeners=_optional_int(track.get("listeners")),
            playcount=_optional_int(track.get("playcount")),
        )

    async def _artist_detail(
        self,
        identity: dict[str, str],
        item_id: str,
    ) -> DiscoveryItemDetail:
        params = _identity_params(identity, primary="artist")
        info_payload = await self._request("artist.getInfo", **params)
        artist = _mapping(info_payload.get("artist"))
        if not artist:
            raise LastFmResourceNotFound("Last.fm artist not found.")
        artist_name = _optional_string(artist.get("name")) or identity.get("name", item_id)
        tracks_payload = await self._request(
            "artist.getTopTracks",
            artist=artist_name,
            limit=50,
        )
        tracks = _tracks(_list_at(tracks_payload, "toptracks", "track"), artist_name)
        stats = _mapping(artist.get("stats"))
        return DiscoveryItemDetail(
            id=item_id,
            resource_type="artists",
            name=artist_name,
            artist_name=artist_name,
            description=_wiki_summary(artist.get("bio")),
            artwork_url=_image_url(artist.get("image")),
            genres=_tag_names(_mapping(artist.get("tags")).get("tag")),
            track_count=len(tracks),
            listeners=_optional_int(stats.get("listeners")),
            playcount=_optional_int(stats.get("playcount")),
            tracks=tracks,
        )

    async def _tag_detail(
        self,
        identity: dict[str, str],
        item_id: str,
    ) -> DiscoveryItemDetail:
        tag_name = identity.get("name", "").strip()
        if not tag_name:
            raise LastFmResourceNotFound("Last.fm tag not found.")
        info_payload = await self._request("tag.getInfo", tag=tag_name)
        tag = _mapping(info_payload.get("tag"))
        tracks_payload = await self._request("tag.getTopTracks", tag=tag_name, limit=50)
        tracks = _tracks(_list_at(tracks_payload, "tracks", "track"))
        return DiscoveryItemDetail(
            id=item_id,
            resource_type="tags",
            name=_optional_string(tag.get("name")) or tag_name,
            description=_wiki_summary(tag.get("wiki")),
            track_count=len(tracks),
            tracks=tracks,
        )

    async def _request(self, method: str, **params: str | int) -> dict[str, Any]:
        api_key = (await self._api_key_loader()).strip()
        if not api_key:
            raise LastFmNotConfigured("Last.fm API Key is not configured.")
        client = await self._request_client()
        response = await client.get(
            LASTFM_API_URL,
            params={"method": method, "api_key": api_key, "format": "json", **params},
        )
        response.raise_for_status()
        try:
            payload = response.json()
        except ValueError as exc:
            raise LastFmDiscoveryError("Invalid Last.fm response.") from exc
        if not isinstance(payload, dict):
            raise LastFmDiscoveryError("Invalid Last.fm response.")
        error_code = _optional_int(payload.get("error"))
        if error_code is not None:
            message = _optional_string(payload.get("message")) or "Last.fm request failed."
            if error_code == 6:
                raise LastFmResourceNotFound(message)
            raise LastFmDiscoveryError(f"Last.fm error {error_code}: {message}")
        return cast(dict[str, Any], payload)

    async def _request_client(self) -> httpx.AsyncClient:
        proxy_url = await self._proxy_loader() if self._proxy_loader is not None else None
        if not proxy_url:
            async with self._proxy_client_lock:
                if self._proxy_client is not None:
                    await self._proxy_client.aclose()
                    self._proxy_client = None
                    self._proxy_url = None
            return self._client
        if self._proxy_client is not None and self._proxy_url == proxy_url:
            return self._proxy_client
        async with self._proxy_client_lock:
            if self._proxy_client is None or self._proxy_url != proxy_url:
                previous_client = self._proxy_client
                self._proxy_client = httpx.AsyncClient(
                    timeout=30,
                    follow_redirects=True,
                    proxy=proxy_url,
                    trust_env=False,
                )
                self._proxy_url = proxy_url
                if previous_client is not None:
                    await previous_client.aclose()
        assert self._proxy_client is not None
        return self._proxy_client

    @staticmethod
    def _chart_item(
        item: dict[str, Any],
        resource_type: DiscoveryResourceType,
        rank: int,
    ) -> DiscoveryChartItem | None:
        name = _optional_string(item.get("name"))
        if not name:
            return None
        artist = _mapping(item.get("artist"))
        artist_name = _optional_string(artist.get("name"))
        identity: dict[str, str] = {"name": name}
        mbid = _optional_string(item.get("mbid"))
        if mbid:
            identity["mbid"] = mbid
        if artist_name:
            identity["artist"] = artist_name
        return DiscoveryChartItem(
            id=_encode_identity(identity),
            resource_type=resource_type,
            rank=rank,
            name=name,
            artist_name=artist_name,
            artwork_url=_image_url(item.get("image")),
            listeners=_optional_int(item.get("listeners") or item.get("reach")),
            playcount=_optional_int(item.get("playcount") or item.get("taggings")),
        )


def _identity_params(identity: dict[str, str], *, primary: str) -> dict[str, str | int]:
    mbid = identity.get("mbid", "").strip()
    if mbid:
        return {"mbid": mbid, "autocorrect": 1}
    if primary == "track":
        return {
            "artist": identity.get("artist", ""),
            "track": identity.get("name", ""),
            "autocorrect": 1,
        }
    return {"artist": identity.get("name", ""), "autocorrect": 1}


def _encode_identity(value: dict[str, str]) -> str:
    raw = json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode()
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def _decode_identity(value: str) -> dict[str, str]:
    try:
        padding = "=" * (-len(value) % 4)
        decoded = json.loads(base64.urlsafe_b64decode(value + padding))
    except (ValueError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise LastFmResourceNotFound("Invalid Last.fm resource identity.") from exc
    if not isinstance(decoded, dict):
        raise LastFmResourceNotFound("Invalid Last.fm resource identity.")
    return {str(key): str(item) for key, item in decoded.items() if item is not None}


def _tracks(items: list[object], fallback_artist: str | None = None) -> tuple[DiscoveryTrack, ...]:
    tracks: list[DiscoveryTrack] = []
    for position, raw_item in enumerate(items, start=1):
        if not isinstance(raw_item, dict):
            continue
        item = cast(dict[str, Any], raw_item)
        name = _optional_string(item.get("name"))
        if not name:
            continue
        artist = _mapping(item.get("artist"))
        artist_name = _optional_string(artist.get("name")) or fallback_artist
        identity = {"name": name}
        if artist_name:
            identity["artist"] = artist_name
        mbid = _optional_string(item.get("mbid"))
        if mbid:
            identity["mbid"] = mbid
        tracks.append(
            DiscoveryTrack(
                id=_encode_identity(identity),
                position=position,
                name=name,
                artist_name=artist_name,
                artwork_url=_image_url(item.get("image")),
                duration_seconds=_seconds(item.get("duration")),
            )
        )
    return tuple(tracks)


def _mapping(value: object) -> dict[str, Any]:
    return cast(dict[str, Any], value) if isinstance(value, dict) else {}


def _list_at(payload: dict[str, Any], parent: str, child: str) -> list[object]:
    value = _mapping(payload.get(parent)).get(child)
    if isinstance(value, list):
        return cast(list[object], value)
    return [value] if isinstance(value, dict) else []


def _image_url(value: object) -> str | None:
    if not isinstance(value, list):
        return None
    for item in reversed(value):
        if isinstance(item, dict) and (url := _optional_string(item.get("#text"))):
            if LASTFM_DEFAULT_ARTWORK_ID in url:
                return None
            return url
    return None


def _tag_names(value: object) -> tuple[str, ...]:
    items = value if isinstance(value, list) else [value]
    return tuple(
        name
        for item in items
        if isinstance(item, dict)
        if (name := _optional_string(item.get("name")))
    )


def _wiki_summary(value: object) -> str | None:
    summary = _optional_string(_mapping(value).get("summary"))
    if not summary:
        return None
    without_links = re.sub(r'<a\b[^>]*>.*?</a>', "", summary, flags=re.IGNORECASE | re.DOTALL)
    return html.unescape(re.sub(r"<[^>]+>", "", without_links)).strip() or None


def _optional_string(value: object) -> str | None:
    text = str(value).strip() if value is not None else ""
    return text or None


def _optional_int(value: object) -> int | None:
    try:
        return int(value) if value not in (None, "") else None
    except (TypeError, ValueError):
        return None


def _milliseconds_to_seconds(value: object) -> int | None:
    milliseconds = _optional_int(value)
    return round(milliseconds / 1000) if milliseconds is not None else None


def _seconds(value: object) -> int | None:
    return _optional_int(value)
