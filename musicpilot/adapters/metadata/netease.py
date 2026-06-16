from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import httpx

from musicpilot.ports.metadata import TrackMetadata


class NetEaseMusicProvider:
    def __init__(self, client: httpx.AsyncClient | None = None) -> None:
        self._client = client or httpx.AsyncClient(
            base_url="https://music.163.com",
            timeout=20,
            headers={
                "Referer": "https://music.163.com/",
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/126.0 Safari/537.36"
                ),
            },
        )
        self._owns_client = client is None

    @property
    def name(self) -> str:
        return "netease"

    async def close(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    async def lookup(self, *, title: str, artist: str | None = None) -> TrackMetadata | None:
        candidates = await self.search_metadata(title=title, artist=artist, limit=1)
        return candidates[0] if candidates else None

    async def search_metadata(
        self,
        *,
        title: str,
        artist: str | None = None,
        limit: int = 5,
    ) -> tuple[TrackMetadata, ...]:
        keyword = f"{title} {artist or ''}".strip()
        response = await self._client.get(
            "/api/search/get/web",
            params={"s": keyword, "type": 1, "limit": max(1, min(limit, 10)), "offset": 0},
        )
        response.raise_for_status()
        songs = response.json().get("result", {}).get("songs", [])
        candidates: list[TrackMetadata] = []
        for song in songs[:limit]:
            metadata = await self._song_metadata(song)
            if metadata is not None:
                candidates.append(metadata)
        return tuple(candidates)

    async def _song_metadata(self, song: dict[str, Any]) -> TrackMetadata | None:
        song_id = song.get("id")
        title = str(song.get("name") or "").strip()
        if not song_id or not title:
            return None
        artists = song.get("artists") or []
        artist = ", ".join(
            str(item.get("name") or "").strip()
            for item in artists
            if item.get("name")
        )
        album = song.get("album") if isinstance(song.get("album"), dict) else {}
        cover_url = _optional_string(album.get("picUrl"))
        publish_time = _optional_int(album.get("publishTime"))
        lyrics = await self._lyrics(str(song_id))
        return TrackMetadata(
            title=title,
            artist=artist or None,
            album=_optional_string(album.get("name")),
            year=_timestamp_year(publish_time),
            lyrics=lyrics,
            cover_url=cover_url,
            extra={"source": self.name, "netease_id": str(song_id)},
        )

    async def _lyrics(self, song_id: str) -> str | None:
        response = await self._client.get(
            "/api/song/lyric",
            params={"id": song_id, "lv": -1, "kv": -1, "tv": -1},
        )
        response.raise_for_status()
        payload = response.json()
        lyric = payload.get("lrc", {}).get("lyric")
        translated = payload.get("tlyric", {}).get("lyric")
        if isinstance(translated, str) and translated.strip():
            return f"{lyric or ''}\n{translated}".strip()
        return lyric.strip() if isinstance(lyric, str) and lyric.strip() else None


def _optional_string(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _optional_int(value: object) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _timestamp_year(value: int | None) -> int | None:
    if not value:
        return None
    try:
        return datetime.fromtimestamp(value / 1000, UTC).year
    except (OSError, OverflowError, ValueError):
        return None
