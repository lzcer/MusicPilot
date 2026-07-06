from __future__ import annotations

import httpx

from musicpilot.ports.metadata import MediaCandidate, TrackMetadata


class MusicBrainzProvider:
    def __init__(self, *, user_agent: str, client: httpx.AsyncClient | None = None) -> None:
        self.user_agent = user_agent
        self._client = client or httpx.AsyncClient(
            base_url="https://musicbrainz.org/ws/2",
            timeout=20,
            headers={"User-Agent": user_agent},
        )
        self._owns_client = client is None

    @property
    def name(self) -> str:
        return "musicbrainz"

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
        body = await self._recording_search(_recording_query(title, artist), limit=min(limit, 25))
        candidates: list[TrackMetadata] = []
        seen: set[tuple[str, str, str]] = set()
        for item in body.get("recordings", []):
            item_title = str(item.get("title") or title)
            artist_credit = item.get("artist-credit") or []
            artist_name = str(artist_credit[0].get("name")) if artist_credit else artist
            releases = item.get("releases") or [{}]
            for release in releases[:3]:
                album = str(release.get("title") or "")
                key = (item_title.casefold(), str(artist_name or "").casefold(), album.casefold())
                if key in seen:
                    continue
                seen.add(key)
                candidates.append(
                    TrackMetadata(
                        title=item_title,
                        artist=artist_name,
                        album=album or None,
                        year=_parse_year(release.get("date")),
                        cover_url=_cover_url(str(release.get("id"))) if release.get("id") else None,
                        extra={
                            "source": self.name,
                            "musicbrainz_recording_id": str(item.get("id") or ""),
                            "musicbrainz_release_id": str(release.get("id") or ""),
                        },
                    )
                )
                if len(candidates) >= limit:
                    return tuple(candidates)
        return tuple(candidates)

    async def search(
        self,
        query: str,
        *,
        artist: str | None = None,
        limit: int = 10,
    ) -> tuple[MediaCandidate, ...]:
        search_query = _recording_query(query, artist)
        body = await self._recording_search(search_query, limit=min(limit, 50))
        candidates = self._media_candidates(body, query=query, limit=limit)
        if candidates or not artist:
            return candidates

        fallback_body = await self._recording_search(_fallback_recording_query(query, artist), limit=min(limit, 50))
        return self._media_candidates(fallback_body, query=query, limit=limit)

    async def _recording_search(self, query: str, *, limit: int) -> dict[str, object]:
        response = await self._client.get(
            "/recording",
            params={
                "query": query,
                "fmt": "json",
                "limit": max(1, min(limit, 50)),
                "inc": "artist-credits+releases",
            },
        )
        response.raise_for_status()
        body = response.json()
        return body if isinstance(body, dict) else {}

    def _media_candidates(
        self,
        body: dict[str, object],
        *,
        query: str,
        limit: int,
    ) -> tuple[MediaCandidate, ...]:
        candidates: list[MediaCandidate] = []
        seen: set[tuple[str, str, str]] = set()
        recordings = body.get("recordings", [])
        if not isinstance(recordings, list):
            return ()
        for item in recordings:
            if not isinstance(item, dict):
                continue
            title = str(item.get("title") or query)
            artist_credit = item.get("artist-credit") or []
            artist_name = str(artist_credit[0].get("name")) if artist_credit else None
            releases = item.get("releases") or [{}]
            for release in releases[:3]:
                album = release.get("title")
                key = (title.lower(), str(artist_name or "").lower(), str(album or "").lower())
                if key in seen:
                    continue
                seen.add(key)
                candidates.append(
                    MediaCandidate(
                        title=title,
                        artist=artist_name,
                        album=str(album) if album else None,
                        release_date=release.get("date"),
                        cover_url=_cover_url(str(release.get("id"))) if release.get("id") else None,
                        source=self.name,
                        external_id=str(item.get("id") or ""),
                    )
                )
                if len(candidates) >= limit:
                    return tuple(candidates)
        return tuple(candidates)


def _parse_year(date_value: str | None) -> int | None:
    if not date_value:
        return None
    try:
        return int(date_value[:4])
    except ValueError:
        return None


def _cover_url(release_id: str) -> str:
    return f"https://coverartarchive.org/release/{release_id}/front-250"


def _recording_query(title: str, artist: str | None = None) -> str:
    query = f'recording:"{_lucene_phrase(title)}"'
    artist_values = _artist_query_values(artist)
    if not artist_values:
        return query
    artist_query = " OR ".join(
        f'{field}:"{_lucene_phrase(value)}"'
        for value in artist_values
        for field in ("artistname", "creditname", "artist")
    )
    return f"{query} AND ({artist_query})"


def _fallback_recording_query(title: str, artist: str) -> str:
    return f'"{_lucene_phrase(title)}" "{_lucene_phrase(artist)}"'


def _artist_query_values(artist: str | None) -> tuple[str, ...]:
    value = str(artist or "").strip()
    if not value:
        return ()
    values = [value]
    parts = [part.strip() for part in value.split(",", 1)]
    if len(parts) == 2 and all(parts):
        values.append(f"{parts[1]} {parts[0]}")
    return tuple(dict.fromkeys(values))


def _lucene_phrase(value: str) -> str:
    return str(value).strip().replace("\\", "\\\\").replace('"', '\\"')
