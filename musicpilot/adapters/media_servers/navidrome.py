from __future__ import annotations

import hashlib
from typing import Any
from uuid import uuid4

import httpx

from musicpilot.ports.media_server import (
    MediaServerPlaylistSyncResult,
    MediaServerTrack,
)


class NavidromeAuthorizationError(RuntimeError):
    pass


class NavidromeMediaServerClient:
    def __init__(
        self,
        base_url: str,
        *,
        api_key: str = "",
        username: str = "",
        password: str = "",
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.username = username
        self.password = password

    @property
    def name(self) -> str:
        return "navidrome"

    async def ping(self) -> None:
        async with httpx.AsyncClient(base_url=self.base_url, timeout=20) as client:
            response = await client.get("/rest/ping.view", params=self._params())
            _validate_navidrome_json_response(response)

    async def list_tracks(self) -> list[MediaServerTrack]:
        tracks: list[MediaServerTrack] = []
        page_size = 500
        offset = 0
        async with httpx.AsyncClient(base_url=self.base_url, timeout=30) as client:
            while True:
                params = {
                    **self._params(),
                    "query": "",
                    "artistCount": "0",
                    "albumCount": "0",
                    "songCount": str(page_size),
                    "songOffset": str(offset),
                }
                response = await client.get("/rest/search3.view", params=params)
                payload = _validate_navidrome_json_response(response)
                search_result = payload.get("searchResult3")
                songs = search_result.get("song", []) if isinstance(search_result, dict) else []
                if not isinstance(songs, list) or not songs:
                    break
                tracks.extend(_track_from_payload(item) for item in songs if isinstance(item, dict))
                if len(songs) < page_size:
                    break
                offset += page_size
        return tracks

    async def start_scan(self) -> None:
        async with httpx.AsyncClient(base_url=self.base_url, timeout=30) as client:
            response = await client.get("/rest/startScan.view", params=self._params())
            _validate_navidrome_scan_response(response)

    async def sync_playlist(
        self,
        *,
        name: str,
        song_ids: list[str],
        public: bool = False,
    ) -> MediaServerPlaylistSyncResult:
        if not song_ids:
            raise ValueError("song_ids must not be empty.")
        async with httpx.AsyncClient(base_url=self.base_url, timeout=30) as client:
            existing_playlist_id = await self._find_playlist_id(client, name)
            mode = "updated" if existing_playlist_id else "created"
            try:
                playlist_id = await self._save_playlist(
                    client,
                    name=name,
                    song_ids=song_ids,
                    playlist_id=existing_playlist_id,
                )
            except NavidromeAuthorizationError:
                if not existing_playlist_id:
                    raise
                playlist_id = await self._save_playlist(
                    client,
                    name=name,
                    song_ids=song_ids,
                    playlist_id=None,
                )
                mode = "created"
            if playlist_id:
                await self._update_playlist_visibility(client, playlist_id, public=public)
        return MediaServerPlaylistSyncResult(
            playlist_id=playlist_id,
            synced_count=len(song_ids),
            mode=mode,
        )

    async def _save_playlist(
        self,
        client: httpx.AsyncClient,
        *,
        name: str,
        song_ids: list[str],
        playlist_id: str | None,
    ) -> str | None:
        params = list(self._params().items())
        if playlist_id:
            params.append(("playlistId", playlist_id))
        else:
            params.append(("name", name))
        params.extend(("songId", song_id) for song_id in song_ids)
        response = await client.get("/rest/createPlaylist.view", params=params)
        body = _validate_navidrome_json_response(response)
        return _playlist_id_from_body(body) or playlist_id

    async def _update_playlist_visibility(
        self,
        client: httpx.AsyncClient,
        playlist_id: str,
        *,
        public: bool,
    ) -> None:
        try:
            response = await client.get(
                "/rest/updatePlaylist.view",
                params={
                    **self._params(),
                    "playlistId": playlist_id,
                    "public": "true" if public else "false",
                },
            )
            _validate_navidrome_json_response(response)
        except NavidromeAuthorizationError as exc:
            raise NavidromeAuthorizationError(
                "当前 Navidrome 用户无权更新该歌单的公开状态，"
                "请确认同步账号拥有该歌单，或换一个歌单名称后重试。"
            ) from exc

    async def _find_playlist_id(
        self,
        client: httpx.AsyncClient,
        name: str,
    ) -> str | None:
        response = await client.get("/rest/getPlaylists.view", params=self._params())
        body = _validate_navidrome_json_response(response)
        playlists = body.get("playlists")
        if not isinstance(playlists, dict):
            return None
        items = playlists.get("playlist")
        if isinstance(items, dict):
            items = [items]
        if not isinstance(items, list):
            return None
        for item in items:
            if not isinstance(item, dict):
                continue
            if str(item.get("name") or "") == name:
                if not self._playlist_belongs_to_current_user(item):
                    continue
                playlist_id = _optional_string(item.get("id"))
                if playlist_id:
                    return playlist_id
        return None

    def _playlist_belongs_to_current_user(self, item: dict[str, Any]) -> bool:
        if not self.username:
            return True
        owner = (
            _optional_string(item.get("owner"))
            or _optional_string(item.get("username"))
            or _optional_string(item.get("userName"))
        )
        if owner is None:
            return True
        return owner.casefold() == self.username.casefold()

    def _params(self) -> dict[str, str]:
        params = {"v": "1.16.1", "c": "MusicPilot", "f": "json"}
        if self.username and self.password:
            salt = uuid4().hex
            auth_token = hashlib.md5(f"{self.password}{salt}".encode()).hexdigest()
            params.update({"u": self.username, "t": auth_token, "s": salt})
        elif self.api_key:
            params["token"] = self.api_key
        return params


def _track_from_payload(payload: dict[str, Any]) -> MediaServerTrack:
    return MediaServerTrack(
        id=str(payload.get("id") or "").strip(),
        title=str(payload.get("title") or payload.get("name") or "-"),
        artist=_optional_string(payload.get("artist")),
        album=_optional_string(payload.get("album")),
        duration=_optional_int(payload.get("duration")),
        size=_optional_int(payload.get("size")),
        year=_optional_int(payload.get("year")),
        suffix=_optional_string(payload.get("suffix")),
        path=_optional_string(payload.get("path")),
        content_type=_optional_string(payload.get("contentType")),
        raw_payload=payload,
    )


def _playlist_id_from_body(body: dict[str, object]) -> str | None:
    playlist = body.get("playlist")
    if not isinstance(playlist, dict):
        return None
    return _optional_string(playlist.get("id"))


def _validate_navidrome_scan_response(response: httpx.Response) -> None:
    body = _validate_navidrome_json_response(response)
    status = str(body.get("status") or "").casefold()
    if status == "ok":
        return
    raise RuntimeError(f"Navidrome scan failed: {_navidrome_error_message(body, status)}")


def _validate_navidrome_json_response(response: httpx.Response) -> dict[str, object]:
    response.raise_for_status()
    try:
        payload = response.json()
    except ValueError as exc:
        raise RuntimeError("Navidrome returned a non-JSON response.") from exc
    if not isinstance(payload, dict):
        raise RuntimeError("Navidrome returned an invalid response.")
    body = payload.get("subsonic-response")
    if not isinstance(body, dict):
        raise RuntimeError("Navidrome response is missing subsonic-response.")
    status = str(body.get("status") or "").casefold()
    if status == "ok":
        return body
    error_message = _navidrome_error_message(body, status)
    if _navidrome_error_code(body) == "50":
        raise NavidromeAuthorizationError(f"Navidrome request failed: {error_message}")
    raise RuntimeError(f"Navidrome request failed: {error_message}")


def _navidrome_error_code(body: dict[str, object]) -> str | None:
    error = body.get("error")
    if not isinstance(error, dict):
        return None
    code = error.get("code")
    return str(code) if code is not None else None


def _navidrome_error_message(body: dict[str, object], status: str) -> str:
    error = body.get("error")
    message = ""
    if isinstance(error, dict):
        code = error.get("code")
        detail = error.get("message")
        if code and detail:
            message = f"{code}: {detail}"
        elif detail:
            message = str(detail)
    if not message:
        message = f"unexpected status {status or '<missing>'}"
    return message


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
