from __future__ import annotations

import base64
from pathlib import Path
from typing import Any

import httpx

from musicpilot.ports.downloader import DownloadState, DownloadStatus, TorrentFile


class TransmissionRpcError(RuntimeError):
    pass


class TransmissionClient:
    def __init__(
        self,
        base_url: str,
        *,
        username: str = "",
        password: str = "",
        download_path: str = "",
        client: httpx.AsyncClient | None = None,
    ) -> None:
        base_url = base_url.rstrip("/")
        self.rpc_url = (
            base_url if base_url.endswith("/transmission/rpc") else f"{base_url}/transmission/rpc"
        )
        self.download_path = download_path
        self._session_id = ""
        self._client = client or httpx.AsyncClient(
            timeout=20,
            auth=httpx.BasicAuth(username, password) if username or password else None,
        )
        self._owns_client = client is None

    @property
    def name(self) -> str:
        return "transmission"

    async def close(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    async def test_connection(self) -> None:
        await self._rpc("session-get")

    async def add_torrent(self, torrent_url: str, *, category: str) -> str:
        arguments: dict[str, Any] = {"filename": torrent_url}
        self._apply_add_options(arguments, category)
        return _added_torrent_hash(await self._rpc("torrent-add", arguments))

    async def add_torrent_file(
        self,
        torrent_data: bytes,
        *,
        filename: str,
        category: str,
    ) -> str:
        del filename
        arguments: dict[str, Any] = {
            "metainfo": base64.b64encode(torrent_data).decode("ascii")
        }
        self._apply_add_options(arguments, category)
        return _added_torrent_hash(await self._rpc("torrent-add", arguments))

    async def get_status(self, torrent_hash: str) -> DownloadStatus:
        torrents = await self._get_torrents([torrent_hash])
        if not torrents:
            return DownloadStatus(torrent_hash, "", DownloadState.FAILED, 0.0)
        return _status_from_torrent(torrents[0])

    async def list_statuses(
        self,
        torrent_hashes: tuple[str, ...] = (),
    ) -> tuple[DownloadStatus, ...]:
        ids = list(torrent_hashes) if torrent_hashes else None
        return tuple(_status_from_torrent(item) for item in await self._get_torrents(ids))

    async def list_downloading_by_tag(self, tag: str) -> tuple[DownloadStatus, ...]:
        del tag
        return ()

    async def list_files(self, torrent_hash: str) -> tuple[TorrentFile, ...]:
        result = await self._rpc(
            "torrent-get",
            {"ids": [torrent_hash], "fields": ["files", "fileStats"]},
        )
        torrents = result.get("torrents", [])
        if not isinstance(torrents, list) or not torrents or not isinstance(torrents[0], dict):
            return ()
        files = torrents[0].get("files", [])
        stats = torrents[0].get("fileStats", [])
        if not isinstance(files, list):
            return ()
        return tuple(
            _file_from_items(
                file,
                stats[index] if isinstance(stats, list) and index < len(stats) else {},
            )
            for index, file in enumerate(files)
            if isinstance(file, dict)
        )

    async def delete_torrent(self, torrent_hash: str, *, delete_files: bool) -> None:
        await self._rpc(
            "torrent-remove",
            {"ids": [torrent_hash], "delete-local-data": delete_files},
        )

    def _apply_add_options(self, arguments: dict[str, Any], category: str) -> None:
        if self.download_path:
            arguments["download-dir"] = self.download_path
        if category:
            arguments["labels"] = [category]

    async def _get_torrents(self, ids: list[str] | None = None) -> list[dict[str, Any]]:
        arguments: dict[str, Any] = {
            "fields": [
                "hashString",
                "name",
                "status",
                "percentDone",
                "downloadDir",
                "error",
                "totalSize",
            ]
        }
        if ids is not None:
            arguments["ids"] = ids
        result = await self._rpc("torrent-get", arguments)
        torrents = result.get("torrents", [])
        if not isinstance(torrents, list):
            return []
        return [item for item in torrents if isinstance(item, dict)]

    async def _rpc(
        self,
        method: str,
        arguments: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        payload = {"method": method, "arguments": arguments or {}}
        headers = {"X-Transmission-Session-Id": self._session_id} if self._session_id else {}
        response = await self._client.post(self.rpc_url, json=payload, headers=headers)
        if response.status_code == 409:
            session_id = response.headers.get("X-Transmission-Session-Id", "")
            if not session_id:
                response.raise_for_status()
            self._session_id = session_id
            response = await self._client.post(
                self.rpc_url,
                json=payload,
                headers={"X-Transmission-Session-Id": session_id},
            )
        response.raise_for_status()
        body = response.json()
        if not isinstance(body, dict):
            raise TransmissionRpcError("Transmission returned an invalid RPC response.")
        result = str(body.get("result", ""))
        if result != "success":
            raise TransmissionRpcError(f"Transmission RPC failed: {result or 'unknown error'}")
        rpc_arguments = body.get("arguments", {})
        return rpc_arguments if isinstance(rpc_arguments, dict) else {}


def _added_torrent_hash(result: dict[str, Any]) -> str:
    torrent = result.get("torrent-added") or result.get("torrent-duplicate")
    if not isinstance(torrent, dict):
        raise TransmissionRpcError("Transmission did not return the added torrent.")
    torrent_hash = str(torrent.get("hashString", ""))
    if not torrent_hash:
        raise TransmissionRpcError("Transmission did not return the torrent hash.")
    return torrent_hash


def _status_from_torrent(item: dict[str, Any]) -> DownloadStatus:
    progress = _optional_float(item.get("percentDone"))
    status = _optional_int(item.get("status"))
    error = _optional_int(item.get("error"))
    if error:
        state = DownloadState.FAILED
    elif progress >= 1 or status in {5, 6}:
        state = DownloadState.COMPLETED
    elif status in {0, 1, 3}:
        state = DownloadState.QUEUED
    else:
        state = DownloadState.DOWNLOADING
    download_dir = str(item.get("downloadDir", ""))
    name = str(item.get("name", ""))
    return DownloadStatus(
        torrent_hash=str(item.get("hashString", "")),
        name=name,
        state=state,
        progress=progress,
        save_path=Path(download_dir) if download_dir else None,
        content_path=Path(download_dir) / name if download_dir and name else None,
        size_bytes=_optional_int(item.get("totalSize")),
    )


def _file_from_items(file: dict[str, Any], stats: object) -> TorrentFile:
    size = _optional_int(file.get("length"))
    completed = _optional_int(stats.get("bytesCompleted")) if isinstance(stats, dict) else 0
    return TorrentFile(
        path=Path(str(file.get("name", ""))),
        size=size,
        progress=completed / size if size else 0.0,
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
