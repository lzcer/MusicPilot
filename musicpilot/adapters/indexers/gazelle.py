from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from typing import Any
from urllib.parse import parse_qs, urlencode, urljoin, urlparse

import httpx

from musicpilot.adapters.indexers.nexusphp import SiteAuthCheck
from musicpilot.core.events import SearchResult


@dataclass(frozen=True, slots=True)
class GazelleSiteConfig:
    name: str
    base_url: str
    cookie: str | None = None
    site_id: str | None = None
    max_concurrency: int = 2
    user_agent: str | None = None
    request_interval: float = 3.0


class GazelleCrawler:
    def __init__(
        self,
        config: GazelleSiteConfig,
        client: httpx.AsyncClient | None = None,
        proxy_url: str | None = None,
    ) -> None:
        self.config = config
        self._client = client
        self._proxy_url = proxy_url
        self._semaphore = asyncio.Semaphore(config.max_concurrency)
        self._request_lock = asyncio.Lock()
        self._next_request_at = 0.0

    @property
    def name(self) -> str:
        return self.config.name

    async def close(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def search(self, query: str, *, limit: int = 20) -> tuple[SearchResult, ...]:
        if not query.strip() or limit < 1:
            return ()

        results: list[SearchResult] = []
        page = 1
        while len(results) < limit:
            payload = await self._get_json(
                "ajax.php",
                {
                    "action": "browse",
                    "searchstr": query,
                    "filter_cat[1]": "1",
                    "page": str(page),
                    "order_by": "time",
                    "order_way": "desc",
                },
            )
            response = payload.get("response")
            if not isinstance(response, dict):
                raise RuntimeError(f"{self.name} 搜索响应格式无效。")
            groups = response.get("results", ())
            if not isinstance(groups, list):
                raise RuntimeError(f"{self.name} 搜索响应格式无效。")
            if not groups:
                break

            for group in groups:
                for result in self._search_results(group):
                    results.append(result)
                    if len(results) >= limit:
                        break
                if len(results) >= limit:
                    break

            if page >= _to_int(response.get("pages")):
                break
            page += 1
        return tuple(results)

    async def test_auth(self) -> SiteAuthCheck:
        if not self.config.cookie or not self.config.cookie.strip():
            return SiteAuthCheck(False, f"Cookie 不能为空，无法验证 {self.name} 连接。")
        try:
            payload = await self._get_json("ajax.php", {"action": "index"})
            response = payload.get("response")
            if not isinstance(response, dict) or not _text(response.get("username")):
                return SiteAuthCheck(False, f"{self.name} Cookie 无效或已过期。")
        except Exception as exc:  # noqa: BLE001
            return SiteAuthCheck(False, f"{self.name} 连接测试失败：{exc}")
        return SiteAuthCheck(True, f"{self.name} Cookie 有效，连接成功。")

    async def download_torrent(self, download_url: str) -> bytes:
        self._validate_download_url(download_url)
        try:
            response = await self._get(download_url, accept="application/x-bittorrent")
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code in {401, 403}:
                message = f"{self.name} Cookie 无效或已过期。"
            elif exc.response.status_code == 429:
                message = f"{self.name} 请求过于频繁，请稍后重试。"
            else:
                message = f"{self.name} 种子文件下载失败，HTTP {exc.response.status_code}。"
            raise RuntimeError(message) from exc
        except httpx.TimeoutException as exc:
            raise RuntimeError(f"{self.name} 种子文件下载超时。") from exc
        except httpx.ProxyError as exc:
            raise RuntimeError(f"{self.name} 种子文件代理连接失败。") from exc
        except httpx.RequestError as exc:
            raise RuntimeError(f"{self.name} 种子文件下载连接失败。") from exc
        return response.content

    async def _get_json(self, path: str, params: dict[str, str]) -> dict[str, Any]:
        try:
            response = await self._get(
                urljoin(self.config.base_url.rstrip("/") + "/", path), params=params
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code in {401, 403}:
                message = f"{self.name} Cookie 无效或已过期。"
            elif exc.response.status_code == 429:
                message = f"{self.name} 请求过于频繁，请稍后重试。"
            else:
                message = f"{self.name} 请求失败，HTTP {exc.response.status_code}。"
            raise RuntimeError(message) from exc
        except httpx.TimeoutException as exc:
            raise RuntimeError(f"{self.name} 连接超时。") from exc
        except httpx.ProxyError as exc:
            raise RuntimeError(f"{self.name} 代理连接失败。") from exc
        except httpx.RequestError as exc:
            raise RuntimeError(f"{self.name} 网络连接失败。") from exc
        try:
            payload = response.json()
        except ValueError as exc:
            raise RuntimeError(f"{self.name} 返回的不是有效 JSON。") from exc
        if not isinstance(payload, dict) or payload.get("status") != "success":
            raise RuntimeError(f"{self.name} API 返回错误：{_api_error(payload)}")
        return payload

    async def _get(
        self,
        url: str,
        *,
        params: dict[str, str] | None = None,
        accept: str = "application/json",
    ) -> httpx.Response:
        async with self._semaphore:
            for attempt in range(2):
                await self._wait_for_request_slot()
                response = await self._send_get(url, params=params, accept=accept)
                if response.status_code != 429 or attempt:
                    return response
                await self._apply_retry_after(response)
        raise AssertionError("unreachable")

    async def _send_get(
        self, url: str, *, params: dict[str, str] | None, accept: str
    ) -> httpx.Response:
        headers = {"Accept": accept}
        if self.config.cookie:
            headers["Cookie"] = self.config.cookie
        if self.config.user_agent:
            headers["User-Agent"] = self.config.user_agent
        if self._client is not None:
            return await self._client.get(url, params=params, headers=headers)
        async with httpx.AsyncClient(
            http2=True, timeout=30, follow_redirects=True, proxy=self._proxy_url
        ) as client:
            return await client.get(url, params=params, headers=headers)

    async def _wait_for_request_slot(self) -> None:
        async with self._request_lock:
            loop = asyncio.get_running_loop()
            wait_seconds = self._next_request_at - loop.time()
            if wait_seconds > 0:
                await asyncio.sleep(wait_seconds)
            self._next_request_at = loop.time() + self.config.request_interval

    async def _apply_retry_after(self, response: httpx.Response) -> None:
        retry_after = _retry_after_seconds(response.headers.get("Retry-After"))
        if retry_after is None:
            retry_after = self.config.request_interval
        async with self._request_lock:
            loop = asyncio.get_running_loop()
            self._next_request_at = max(self._next_request_at, loop.time() + retry_after)

    def _search_results(self, raw_group: object) -> tuple[SearchResult, ...]:
        if not isinstance(raw_group, dict):
            return ()
        group_id = _text(raw_group.get("groupId"))
        group_name = _text(raw_group.get("groupName"))
        torrents = raw_group.get("torrents")
        if not group_id or not group_name or not isinstance(torrents, list):
            return ()

        artist = _artist_name(raw_group)
        results: list[SearchResult] = []
        for torrent in torrents:
            if not isinstance(torrent, dict):
                continue
            torrent_id = _text(torrent.get("torrentId"))
            if not torrent_id:
                continue
            details_query = urlencode({"id": group_id, "torrentid": torrent_id})
            title = " - ".join(part for part in (artist, group_name) if part)
            edition = _edition(torrent)
            format_description = " / ".join(
                part
                for part in (
                    _text(torrent.get("media")),
                    _text(torrent.get("format")),
                    _text(torrent.get("encoding")),
                )
                if part
            )
            results.append(
                SearchResult(
                    title=title,
                    download_url=urljoin(
                        self.config.base_url.rstrip("/") + "/",
                        f"torrents.php?{urlencode({'action': 'download', 'id': torrent_id})}",
                    ),
                    details_url=urljoin(
                        self.config.base_url.rstrip("/") + "/", f"torrents.php?{details_query}"
                    ),
                    source=self.name,
                    seeders=_to_int(torrent.get("seeders")),
                    leechers=_to_int(torrent.get("leechers")),
                    size_bytes=_to_int(torrent.get("size")) or None,
                    subtitle=" / ".join(
                        part for part in (edition, format_description) if part
                    )
                    or None,
                    published_at=_text(torrent.get("time")) or None,
                    promotion=_promotion(torrent),
                    metadata={
                        "type": "music",
                        "category": _text(raw_group.get("releaseType")) or "Music",
                        "artist": artist,
                        "album": group_name,
                        "year": _to_int(raw_group.get("groupYear")) or None,
                        "media": _text(torrent.get("media")) or None,
                        "format": _text(torrent.get("format")) or None,
                        "encoding": _text(torrent.get("encoding")) or None,
                    },
                )
            )
        return tuple(results)

    def _validate_download_url(self, download_url: str) -> None:
        parsed = urlparse(download_url)
        base = urlparse(self.config.base_url)
        torrent_ids = parse_qs(parsed.query).get("id", ())
        if (
            parsed.scheme not in {"http", "https"}
            or parsed.hostname != base.hostname
            or parsed.path != "/torrents.php"
            or parse_qs(parsed.query).get("action") != ["download"]
            or len(torrent_ids) != 1
            or not torrent_ids[0].isdigit()
        ):
            raise RuntimeError(f"{self.name} 种子下载地址无效。")


def _text(value: object) -> str:
    return str(value or "").strip()


def _to_int(value: object) -> int:
    try:
        return int(str(value or "0"))
    except ValueError:
        return 0


def _api_error(payload: object) -> str:
    if isinstance(payload, dict):
        return _text(payload.get("error")) or "未知错误"
    return "响应格式无效"


def _retry_after_seconds(value: str | None) -> float | None:
    if not value:
        return None
    try:
        return max(0.0, float(value))
    except ValueError:
        try:
            retry_at = parsedate_to_datetime(value).astimezone(UTC)
            return max(0.0, (retry_at - datetime.now(UTC)).total_seconds())
        except (TypeError, ValueError):
            return None


def _artist_name(group: dict[str, Any]) -> str:
    artist = group.get("artist") or group.get("artists")
    if isinstance(artist, str):
        return artist.strip()
    if isinstance(artist, dict):
        return _text(artist.get("name"))
    if isinstance(artist, list):
        names = (_text(item.get("name")) for item in artist if isinstance(item, dict))
        return ", ".join(name for name in names if name)
    return ""


def _edition(torrent: dict[str, Any]) -> str:
    if not torrent.get("remastered"):
        return ""
    parts = (
        _text(torrent.get("remasterYear")),
        _text(torrent.get("remasterTitle")),
        _text(torrent.get("remasterRecordLabel")),
        _text(torrent.get("remasterCatalogueNumber")),
    )
    return " ".join(part for part in parts if part) or "Remaster"


def _promotion(torrent: dict[str, Any]) -> str | None:
    if torrent.get("isFreeload") or torrent.get("isNeutralLeech"):
        return "0X"
    if torrent.get("isPersonalFreeleech") or torrent.get("isFreeleech"):
        return "FREE"
    return None
