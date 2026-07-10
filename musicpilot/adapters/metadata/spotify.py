from __future__ import annotations

import time
from dataclasses import dataclass

import httpx


@dataclass(frozen=True, slots=True)
class SpotifyMetadataConfig:
    client_id: str = ""
    client_secret: str = ""
    markets: tuple[str, ...] = ("JP", "KR")

    @property
    def enabled(self) -> bool:
        return bool(self.client_id.strip() and self.client_secret.strip())


@dataclass(frozen=True, slots=True)
class SpotifyTrack:
    track_id: str
    title: str
    artist: str
    album: str
    cover_url: str | None
    year: str | None


class SpotifyMetadataClient:
    accounts_base_url = "https://accounts.spotify.com"
    api_base_url = "https://api.spotify.com/v1"

    def __init__(
        self,
        config: SpotifyMetadataConfig | None = None,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._config = config or SpotifyMetadataConfig()
        self._client = client or httpx.AsyncClient(timeout=20, follow_redirects=True)
        self._owns_client = client is None
        self._access_token: str | None = None
        self._access_token_expires_at = 0.0

    async def close(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    def update_config(self, config: SpotifyMetadataConfig) -> None:
        if config == self._config:
            return
        self._config = config
        self._access_token = None
        self._access_token_expires_at = 0.0

    async def search_tracks(
        self,
        *,
        title: str,
        artist: str | None = None,
        limit: int = 5,
    ) -> tuple[SpotifyTrack, ...]:
        if not self._config.enabled:
            return ()

        query = _search_query(title, artist)
        if not query:
            return ()

        tracks: list[SpotifyTrack] = []
        seen: set[str] = set()
        for market in self._config.markets:
            payload = await self._search_market(query=query, market=market, limit=limit)
            for item in _track_items(payload):
                track = _spotify_track(item)
                if track is None or track.track_id in seen:
                    continue
                seen.add(track.track_id)
                tracks.append(track)
                if len(tracks) >= limit:
                    return tuple(tracks)
        return tuple(tracks)

    async def _search_market(self, *, query: str, market: str, limit: int) -> object:
        response = await self._client.get(
            f"{self.api_base_url}/search",
            headers={"Authorization": f"Bearer {await self._token()}"},
            params={
                "q": query,
                "type": "track",
                "market": market,
                "limit": max(1, min(limit, 10)),
            },
        )
        if response.status_code == 401:
            self._access_token = None
            self._access_token_expires_at = 0.0
            response = await self._client.get(
                f"{self.api_base_url}/search",
                headers={"Authorization": f"Bearer {await self._token()}"},
                params={
                    "q": query,
                    "type": "track",
                    "market": market,
                    "limit": max(1, min(limit, 10)),
                },
            )
        response.raise_for_status()
        return response.json()

    async def _token(self) -> str:
        if self._access_token and time.monotonic() < self._access_token_expires_at:
            return self._access_token

        response = await self._client.post(
            f"{self.accounts_base_url}/api/token",
            data={"grant_type": "client_credentials"},
            auth=(self._config.client_id, self._config.client_secret),
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict) or not isinstance(payload.get("access_token"), str):
            raise RuntimeError("Spotify token response is missing an access token.")
        self._access_token = payload["access_token"]
        try:
            expires_in = int(payload.get("expires_in", 3600))
        except (TypeError, ValueError):
            expires_in = 3600
        self._access_token_expires_at = time.monotonic() + max(60, expires_in - 60)
        return self._access_token


def spotify_metadata_config_from_mapping(value: object) -> SpotifyMetadataConfig:
    raw = value if isinstance(value, dict) else {}
    markets = tuple(
        dict.fromkeys(
            market.strip().upper()
            for market in str(raw.get("markets") or "JP,KR").split(",")
            if len(market.strip()) == 2 and market.strip().isalpha()
        )
    )
    return SpotifyMetadataConfig(
        client_id=str(raw.get("client_id") or "").strip(),
        client_secret=str(raw.get("client_secret") or "").strip(),
        markets=markets or ("JP", "KR"),
    )


def _search_query(title: str, artist: str | None) -> str:
    values = [f'track:"{title.strip()}"'] if title.strip() else []
    if artist and artist.strip():
        values.append(f'artist:"{artist.strip()}"')
    return " ".join(values)


def _track_items(payload: object) -> tuple[dict[str, object], ...]:
    if not isinstance(payload, dict):
        return ()
    tracks = payload.get("tracks")
    if not isinstance(tracks, dict):
        return ()
    items = tracks.get("items")
    if not isinstance(items, list):
        return ()
    return tuple(item for item in items if isinstance(item, dict))


def _spotify_track(item: dict[str, object]) -> SpotifyTrack | None:
    track_id = str(item.get("id") or "")
    title = str(item.get("name") or "")
    artists = item.get("artists")
    artist = ", ".join(
        str(value.get("name") or "")
        for value in artists
        if isinstance(value, dict) and value.get("name")
    ) if isinstance(artists, list) else ""
    album_data = item.get("album")
    album = album_data if isinstance(album_data, dict) else {}
    album_name = str(album.get("name") or "")
    release_date = str(album.get("release_date") or "")
    images = album.get("images")
    cover_url = next(
        (
            str(image.get("url"))
            for image in images
            if isinstance(image, dict) and image.get("url")
        ),
        None,
    ) if isinstance(images, list) else None
    if not track_id or not title:
        return None
    return SpotifyTrack(
        track_id=track_id,
        title=title,
        artist=artist,
        album=album_name,
        cover_url=cover_url,
        year=release_date[:4] if len(release_date) >= 4 else None,
    )
