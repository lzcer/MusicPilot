from __future__ import annotations

import asyncio
from pathlib import Path

import httpx

from musicpilot.ports.downloader import DownloadState, DownloadStatus


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
            if body not in {"ok.", "ok"}:
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
        before = {str(item.get("hash", "")) for item in await self._list_info()}
        data = {"urls": torrent_url, "category": category, "tags": "MusicPilot"}
        save_path = getattr(self, "download_path", "")
        if save_path:
            data["savepath"] = save_path
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
                newest = max(new_items, key=lambda item: int(item.get("added_on") or 0))
                return str(newest.get("hash", ""))
            await asyncio.sleep(1)
        return ""

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
        progress = float(item.get("progress", 0.0))
        state = DownloadState.COMPLETED if progress >= 1 else DownloadState.DOWNLOADING
        save_path = item.get("save_path")
        return DownloadStatus(
            torrent_hash=torrent_hash,
            name=str(item.get("name", "")),
            state=state,
            progress=progress,
            save_path=Path(save_path) if save_path else None,
        )

    async def list_statuses(self) -> tuple[DownloadStatus, ...]:
        return tuple(_status_from_item(item) for item in await self._list_info())

    async def _list_info(self) -> list[dict[str, object]]:
        response = await self._request("GET", "/api/v2/torrents/info")
        response.raise_for_status()
        return list(response.json())


def _status_from_item(item: dict[str, object]) -> DownloadStatus:
    torrent_hash = str(item.get("hash", ""))
    progress = float(item.get("progress", 0.0))
    state = DownloadState.COMPLETED if progress >= 1 else DownloadState.DOWNLOADING
    save_path = item.get("save_path")
    return DownloadStatus(
        torrent_hash=torrent_hash,
        name=str(item.get("name", "")),
        state=state,
        progress=progress,
        save_path=Path(str(save_path)) if save_path else None,
    )
