from __future__ import annotations

import asyncio
import hashlib
from pathlib import Path

import httpx

from musicpilot.ports.downloader import (
    DownloadState,
    DownloadStatus,
    TorrentFile,
)

_COMPLETED_TORRENT_STATES = frozenset(
    {
        "forcedUP",
        "pausedUP",
        "queuedUP",
        "stalledUP",
        "stoppedUP",
        "uploading",
    }
)


class QBittorrentAuthError(RuntimeError):
    pass


class QBittorrentClient:
    def __init__(
        self,
        base_url: str,
        *,
        username: str,
        password: str,
        download_path: str = "",
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.username = username
        self.password = password
        self.download_path = download_path
        self._client = client or httpx.AsyncClient(base_url=self.base_url, timeout=20)
        self._owns_client = client is None
        self._authenticated = False
        self._login_lock = asyncio.Lock()

    @property
    def name(self) -> str:
        return "qbittorrent"

    async def close(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    async def login(self) -> None:
        async with self._login_lock:
            response = await self._client.post(
                "/api/v2/auth/login",
                data={"username": self.username, "password": self.password},
            )
            response.raise_for_status()
            body = response.text.strip().lower()
            if response.status_code != 204 and body not in {"ok.", "ok"}:
                self._authenticated = False
                raise QBittorrentAuthError(
                    f"qBittorrent authentication failed: {response.text[:120]}"
                )
            self._authenticated = True

    async def _ensure_login(self) -> None:
        if not self._authenticated:
            await self.login()

    async def _request(self, method: str, url: str, **kwargs: object) -> httpx.Response:
        await self._ensure_login()
        response = await self._client.request(method, url, **kwargs)
        if response.status_code not in {401, 403}:
            return response
        self._authenticated = False
        await self.login()
        return await self._client.request(method, url, **kwargs)

    async def test_connection(self) -> None:
        response = await self._request("GET", "/api/v2/torrents/info")
        response.raise_for_status()

    async def add_torrent(self, torrent_url: str, *, category: str) -> str:
        before_items = await self._list_info()
        before = _hashes_from_items(before_items)
        data = {"urls": torrent_url, "category": category, "tags": "MusicPilot"}
        save_path = getattr(self, "download_path", "")
        if save_path:
            data["savepath"] = save_path
            data["autoTMM"] = "false"
        response = await self._request(
            "POST",
            "/api/v2/torrents/add",
            data=data,
        )
        response.raise_for_status()
        for _ in range(5):
            after = await self._list_info()
            new_items = [
                item for item in after if str(item.get("hash", "")) not in before
            ]
            if len(new_items) == 1:
                return str(new_items[0].get("hash", ""))
            if len(new_items) > 1:
                newest = max(new_items, key=lambda item: _optional_int(item.get("added_on")))
                return str(newest.get("hash", ""))
            await asyncio.sleep(1)
        return ""

    async def add_torrent_file(
        self,
        torrent_data: bytes,
        *,
        filename: str,
        category: str,
    ) -> str:
        expected_hash = _torrent_info_hash(torrent_data)
        before = {str(item.get("hash", "")) for item in await self._list_info()}
        if expected_hash in before:
            return expected_hash
        data = {"category": category, "tags": "MusicPilot"}
        save_path = getattr(self, "download_path", "")
        if save_path:
            data["savepath"] = save_path
            data["autoTMM"] = "false"
        response = await self._request(
            "POST",
            "/api/v2/torrents/add",
            data=data,
            files={
                "torrents": (
                    filename or "musicpilot.torrent",
                    torrent_data,
                    "application/x-bittorrent",
                )
            },
        )
        response.raise_for_status()
        for _ in range(5):
            after = await self._list_info()
            if expected_hash in _hashes_from_items(after):
                return expected_hash
            new_items = [
                item for item in after if str(item.get("hash", "")).casefold() not in before
            ]
            if len(new_items) == 1:
                return str(new_items[0].get("hash", ""))
            if len(new_items) > 1:
                newest = max(new_items, key=lambda item: _optional_int(item.get("added_on")))
                return str(newest.get("hash", ""))
            await asyncio.sleep(1)
        raise RuntimeError("qBittorrent did not add the uploaded torrent.")

    async def get_status(self, torrent_hash: str) -> DownloadStatus:
        response = await self._request(
            "GET",
            "/api/v2/torrents/info",
            params={"hashes": torrent_hash},
        )
        response.raise_for_status()
        items = response.json()
        if not items:
            return DownloadStatus(torrent_hash, "", DownloadState.FAILED, 0.0)
        item = items[0]
        progress = _optional_float(item.get("progress"))
        state = _download_state(item, progress)
        save_path = item.get("save_path")
        content_path = item.get("content_path")
        return DownloadStatus(
            torrent_hash=torrent_hash,
            name=str(item.get("name", "")),
            state=state,
            progress=progress,
            save_path=Path(save_path) if save_path else None,
            content_path=Path(str(content_path)) if content_path else None,
        )

    async def list_statuses(
        self,
        torrent_hashes: tuple[str, ...] = (),
    ) -> tuple[DownloadStatus, ...]:
        params = {"hashes": "|".join(torrent_hashes)} if torrent_hashes else None
        return tuple(_status_from_item(item) for item in await self._list_info(params=params))

    async def list_downloading_by_tag(self, tag: str) -> tuple[DownloadStatus, ...]:
        return tuple(
            _status_from_item(item)
            for item in await self._list_info(
                params={"filter": "downloading", "tag": tag},
            )
        )

    async def list_files(self, torrent_hash: str) -> tuple[TorrentFile, ...]:
        response = await self._request(
            "GET",
            "/api/v2/torrents/files",
            params={"hash": torrent_hash},
        )
        response.raise_for_status()
        return tuple(_file_from_item(item) for item in response.json())

    async def delete_torrent(self, torrent_hash: str, *, delete_files: bool) -> None:
        response = await self._request(
            "POST",
            "/api/v2/torrents/delete",
            data={
                "hashes": torrent_hash,
                "deleteFiles": "true" if delete_files else "false",
            },
        )
        response.raise_for_status()

    async def _list_info(
        self,
        *,
        params: dict[str, str] | None = None,
    ) -> list[dict[str, object]]:
        response = await self._request("GET", "/api/v2/torrents/info", params=params)
        response.raise_for_status()
        return list(response.json())


def _status_from_item(item: dict[str, object]) -> DownloadStatus:
    torrent_hash = str(item.get("hash", ""))
    progress = _optional_float(item.get("progress"))
    state = _download_state(item, progress)
    save_path = item.get("save_path")
    content_path = item.get("content_path")
    return DownloadStatus(
        torrent_hash=torrent_hash,
        name=str(item.get("name", "")),
        state=state,
        progress=progress,
        save_path=Path(str(save_path)) if save_path else None,
        content_path=Path(str(content_path)) if content_path else None,
        tags=_tags_from_item(item.get("tags")),
        size_bytes=_optional_int(item.get("total_size")),
    )


def _download_state(item: dict[str, object], progress: float) -> DownloadState:
    native_state = str(item.get("state", ""))
    if progress >= 1 and native_state in _COMPLETED_TORRENT_STATES:
        return DownloadState.COMPLETED
    return DownloadState.DOWNLOADING


def _file_from_item(item: dict[str, object]) -> TorrentFile:
    return TorrentFile(
        path=Path(str(item.get("name", ""))),
        size=_optional_int(item.get("size")),
        progress=_optional_float(item.get("progress")),
    )


def _optional_int(value: object) -> int:
    try:
        return int(str(value))
    except (TypeError, ValueError):
        return 0


def _optional_float(value: object) -> float:
    try:
        return float(str(value))
    except (TypeError, ValueError):
        return 0.0


def _tags_from_item(value: object) -> tuple[str, ...]:
    return tuple(tag.strip() for tag in str(value or "").split(",") if tag.strip())


def _hashes_from_items(items: list[dict[str, object]]) -> set[str]:
    return {str(item.get("hash", "")).casefold() for item in items if item.get("hash")}


def _torrent_info_hash(torrent_data: bytes) -> str:
    start = _find_top_level_value(torrent_data, b"info")
    end = _skip_bencode_value(torrent_data, start)
    return hashlib.sha1(torrent_data[start:end]).hexdigest()


def _find_top_level_value(data: bytes, key: bytes) -> int:
    if not data or data[0:1] != b"d":
        raise ValueError("Invalid torrent file.")
    index = 1
    while index < len(data):
        if data[index : index + 1] == b"e":
            break
        parsed_key, index = _read_bencode_bytes(data, index)
        value_start = index
        if parsed_key == key:
            return value_start
        index = _skip_bencode_value(data, index)
    raise ValueError("Torrent info section is missing.")


def _skip_bencode_value(data: bytes, index: int) -> int:
    marker = data[index : index + 1]
    if marker == b"i":
        end = data.index(b"e", index)
        return end + 1
    if marker == b"l":
        index += 1
        while data[index : index + 1] != b"e":
            index = _skip_bencode_value(data, index)
        return index + 1
    if marker == b"d":
        index += 1
        while data[index : index + 1] != b"e":
            _, index = _read_bencode_bytes(data, index)
            index = _skip_bencode_value(data, index)
        return index + 1
    if marker.isdigit():
        _, next_index = _read_bencode_bytes(data, index)
        return next_index
    raise ValueError("Invalid bencode value.")


def _read_bencode_bytes(data: bytes, index: int) -> tuple[bytes, int]:
    colon = data.index(b":", index)
    length = int(data[index:colon])
    start = colon + 1
    end = start + length
    return data[start:end], end
