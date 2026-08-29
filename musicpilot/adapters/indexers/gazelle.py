from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from html import unescape
from typing import Any
from urllib.parse import parse_qs, urlencode, urljoin, urlparse

import httpx

from musicpilot.adapters.indexers.nexusphp import SiteAuthCheck
from musicpilot.core.events import SearchResult

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class GazelleSiteConfig:
    name: str
    base_url: str
    cookie: str | None = None
    site_id: str | None = None
    max_concurrency: int = 2
    user_agent: str | None = None
    min_request_interval: float = 3.0
    music_category_id: int = 1


class GazelleCrawler:
    _MAX_RATE_LIMIT_RETRIES = 2
    _DEFAULT_RETRY_AFTER = 10.0

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
        self._last_request_at: float | None = None
        self._retry_after_until: float = 0.0

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
            try:
                payload = await self._get_json(
                    "ajax.php",
                    {
                        "action": "browse",
                        "searchstr": query,
                        f"filter_cat[{self.config.music_category_id}]": "1",
                        "page": str(page),
                        "order_by": "time",
                        "order_way": "desc",
                    },
                )
            except RuntimeError:
                if page == 1:
                    raise
                logger.warning(
                    "%s search page %s failed, returning %s result(s) collected so far.",
                    self.config.name,
                    page,
                    len(results),
                )
                break
            response = payload.get("response")
            if not isinstance(response, dict):
                raise RuntimeError(f"{self.config.name} 搜索响应格式无效。")
            group_results = response.get("results")
            if not isinstance(group_results, list):
                raise RuntimeError(f"{self.config.name} 搜索响应格式无效。")
            if not group_results:
                break
            before = len(results)
            results.extend(self._parse_results(group_results, limit - len(results)))
            if len(results) == before:
                logger.warning(
                    "%s search page %s yielded no usable result, stopping pagination.",
                    self.config.name,
                    page,
                )
                break
            if page >= _to_int(response.get("pages")):
                break
            page += 1
        return tuple(results[:limit])

    async def test_auth(self) -> SiteAuthCheck:
        site = self.config.name
        if not self.config.cookie or not self.config.cookie.strip():
            return SiteAuthCheck(False, "Cookie 不能为空，无法验证站点登录状态。")
        try:
            payload = await self._get_json("ajax.php", {"action": "index"})
        except RuntimeError as exc:
            return SiteAuthCheck(False, f"{site} 连接测试失败：{exc}")
        response = payload.get("response")
        if isinstance(response, dict) and _optional_text(response.get("username")):
            return SiteAuthCheck(True, f"{site} Cookie 有效，连接成功。")
        return SiteAuthCheck(False, f"{site} 未返回登录用户信息，Cookie 无效或已过期。")

    async def download_torrent(self, download_url: str) -> bytes:
        site = self.config.name
        self._validate_download_url(download_url)
        try:
            response = await self._get(download_url, accept="application/x-bittorrent")
            if response.status_code == 429:
                delay = await self._register_rate_limit(response)
                logger.warning(
                    "%s torrent download rate limited (HTTP 429), retry after %.1fs.",
                    site,
                    delay,
                )
                raise RuntimeError(f"{site} 请求过于频繁，请稍后重试。")
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code in {401, 403}:
                message = f"{site} Cookie 无效或已过期。"
            else:
                message = f"{site} 种子文件下载失败，HTTP {exc.response.status_code}。"
            raise RuntimeError(message) from exc
        except httpx.TimeoutException as exc:
            raise RuntimeError(f"{site} 种子文件下载超时。") from exc
        except httpx.ProxyError as exc:
            raise RuntimeError(f"{site} 种子文件代理连接失败。") from exc
        except httpx.RequestError as exc:
            raise RuntimeError(f"{site} 种子文件下载连接失败。") from exc
        return response.content

    async def _get_json(self, path: str, params: dict[str, str]) -> dict[str, Any]:
        site = self.config.name
        url = urljoin(self.config.base_url, path)
        for attempt in range(self._MAX_RATE_LIMIT_RETRIES + 1):
            try:
                response = await self._get(url, params=params)
                if response.status_code == 429:
                    delay = await self._register_rate_limit(response)
                    if attempt < self._MAX_RATE_LIMIT_RETRIES:
                        logger.warning(
                            "%s rate limited (HTTP 429), backing off %.1fs before retry %s/%s.",
                            site,
                            delay,
                            attempt + 1,
                            self._MAX_RATE_LIMIT_RETRIES,
                        )
                        continue
                    raise RuntimeError(f"{site} 请求过于频繁，请稍后重试。")
                response.raise_for_status()
            except httpx.HTTPStatusError as exc:
                if exc.response.status_code in {401, 403}:
                    raise RuntimeError(f"{site} Cookie 无效、已过期或请求受限。") from exc
                raise RuntimeError(
                    f"{site} 请求失败，HTTP {exc.response.status_code}。"
                ) from exc
            except httpx.TimeoutException as exc:
                raise RuntimeError(f"{site} 连接超时。") from exc
            except httpx.ProxyError as exc:
                raise RuntimeError(f"{site} 代理连接失败。") from exc
            except httpx.RequestError as exc:
                raise RuntimeError(f"{site} 网络连接失败。") from exc

            try:
                payload = response.json()
            except ValueError as exc:
                raise RuntimeError(f"{site} 返回的不是有效 JSON。") from exc
            if not isinstance(payload, dict):
                raise RuntimeError(f"{site} 响应格式无效。")
            if payload.get("status") != "success":
                raise RuntimeError(str(payload.get("error") or f"{site} 返回错误。"))
            return payload
        raise RuntimeError(f"{site} 请求过于频繁，请稍后重试。")

    async def _get(
        self,
        url: str,
        *,
        params: dict[str, str] | None = None,
        accept: str = "application/json",
    ) -> httpx.Response:
        async with self._semaphore:
            await self._wait_for_request_slot()
            headers = self._headers()
            headers["Accept"] = accept
            if self._client is not None:
                return await self._client.get(url, params=params, headers=headers)
            async with httpx.AsyncClient(
                http2=True,
                timeout=30,
                follow_redirects=True,
                proxy=self._proxy_url,
            ) as client:
                return await client.get(url, params=params, headers=headers)

    async def _wait_for_request_slot(self) -> None:
        loop = asyncio.get_running_loop()
        while True:
            async with self._request_lock:
                now = loop.time()
                interval_wait = (
                    0.0
                    if self._last_request_at is None
                    else self.config.min_request_interval - (now - self._last_request_at)
                )
                wait_seconds = max(interval_wait, self._retry_after_until - now)
                if wait_seconds <= 0:
                    self._last_request_at = now
                    return
            await asyncio.sleep(wait_seconds)

    async def _register_rate_limit(self, response: httpx.Response) -> float:
        delay = _retry_after_seconds(response.headers.get("Retry-After"))
        if delay is None:
            delay = self._DEFAULT_RETRY_AFTER
        loop = asyncio.get_running_loop()
        async with self._request_lock:
            self._retry_after_until = max(self._retry_after_until, loop.time() + delay)
        return delay

    def _headers(self) -> dict[str, str]:
        headers = {"Accept": "application/json"}
        if self.config.cookie:
            headers["Cookie"] = self.config.cookie
        if self.config.user_agent:
            headers["User-Agent"] = self.config.user_agent
        return headers

    def _parse_results(self, group_results: list[object], limit: int) -> tuple[SearchResult, ...]:
        results: list[SearchResult] = []
        for group in group_results:
            if not isinstance(group, dict):
                continue
            for torrent in group.get("torrents", []):
                result = self._search_result(group, torrent)
                if result is not None:
                    results.append(result)
                if len(results) >= limit:
                    return tuple(results)
        return tuple(results)

    def _validate_download_url(self, download_url: str) -> None:
        parsed = urlparse(download_url)
        base = urlparse(self.config.base_url)
        query = parse_qs(parsed.query)
        torrent_ids = query.get("id", [])
        if (
            parsed.scheme not in {"http", "https"}
            or parsed.hostname != base.hostname
            or parsed.path != "/torrents.php"
            or query.get("action") != ["download"]
            or len(torrent_ids) != 1
            or not torrent_ids[0].isdigit()
            or set(query) - {"action", "id", "usetoken"}
        ):
            raise RuntimeError(f"{self.config.name} 种子下载地址无效。")

    def _search_result(self, group: dict[str, Any], torrent: object) -> SearchResult | None:
        if not isinstance(torrent, dict):
            return None
        torrent_id = _optional_text(torrent.get("torrentId") or torrent.get("id"))
        group_id = _optional_text(group.get("groupId") or group.get("id"))
        group_name = _optional_text(group.get("groupName") or group.get("name"))
        if not torrent_id or not group_name:
            return None

        artist = _artists(group)
        year = _optional_text(group.get("groupYear") or group.get("year"))
        release = " - ".join(part for part in (artist, group_name, year) if part)
        attributes = _subtitle(torrent)
        query = urlencode({"action": "download", "id": torrent_id})
        details_url = (
            urljoin(self.config.base_url, f"torrents.php?id={group_id}") if group_id else None
        )
        return SearchResult(
            title=release,
            download_url=urljoin(self.config.base_url, f"torrents.php?{query}"),
            details_url=details_url,
            source=self.config.name,
            seeders=_to_int(torrent.get("seeders")),
            leechers=_to_int(torrent.get("leechers")),
            size_bytes=_to_int(torrent.get("size")) or None,
            subtitle=attributes or None,
            published_at=_optional_text(torrent.get("time")),
            metadata={
                "adapter": "gazelle",
                "type": "music",
                "artist": artist,
                "album": group_name,
                "year": year,
                "category": "Music",
                "release_type": _optional_text(group.get("releaseType")),
                "tags": _string_list(group.get("tags")),
                "media": _optional_text(torrent.get("media")),
                "format": _optional_text(torrent.get("format")),
                "encoding": _optional_text(torrent.get("encoding")),
                "record_label": _optional_text(torrent.get("remasterRecordLabel")),
                "remaster_title": _optional_text(torrent.get("remasterTitle")),
                "remaster_year": _to_int(torrent.get("remasterYear")) or None,
                "catalogue_number": _optional_text(torrent.get("remasterCatalogueNumber")),
                "has_log": _to_bool(torrent.get("hasLog")),
                "log_score": _to_int(torrent.get("logScore")),
                "has_cue": _to_bool(torrent.get("hasCue")),
                "can_use_token": _to_bool(torrent.get("canUseToken")),
                "freeleech": _to_bool(torrent.get("isFreeleech")),
                "personal_freeleech": _to_bool(torrent.get("isPersonalFreeleech")),
                "freeload": _to_bool(torrent.get("isFreeload")),
                "neutral_leech": _to_bool(torrent.get("isNeutralLeech")),
            },
            promotion=_promotion(torrent),
        )


def _retry_after_seconds(value: str | None) -> float | None:
    if value is None:
        return None
    text = value.strip()
    if not text:
        return None
    try:
        return max(0.0, float(text))
    except ValueError:
        pass
    try:
        parsed = parsedate_to_datetime(text)
    except (TypeError, ValueError):
        return None
    if parsed is None:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return max(0.0, (parsed - datetime.now(UTC)).total_seconds())


def _artists(group: dict[str, Any]) -> str | None:
    artists = group.get("artists") or group.get("extendedArtists")
    if not isinstance(artists, list):
        return _optional_text(group.get("artist"))
    names = [
        _optional_text(artist.get("name"))
        for artist in artists
        if isinstance(artist, dict) and _optional_text(artist.get("name"))
    ]
    return ", ".join(names) or None


def _optional_text(value: object) -> str | None:
    text = unescape(str(value or "")).strip()
    return text or None


def _to_int(value: object) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    text = str(value or "").strip().replace(",", "").replace(" ", "")
    if not text:
        return 0
    try:
        return int(float(text))
    except ValueError:
        return 0


def _to_bool(value: object) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, int | float):
        return value != 0
    return str(value).strip().lower() in {"true", "1", "yes", "on"}


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [text for item in value if (text := _optional_text(item))]


def _subtitle(torrent: dict[str, Any]) -> str | None:
    release_parts = [
        "Music",
        _optional_text(torrent.get("remasterRecordLabel")),
        _optional_text(torrent.get("remasterTitle")),
        _optional_text(torrent.get("remasterCatalogueNumber")),
        _optional_text(torrent.get("media")),
    ]
    quality_parts = [
        _optional_text(torrent.get("format")),
        _optional_text(torrent.get("encoding")),
    ]
    if _to_bool(torrent.get("hasLog")):
        quality_parts.append(f"Log ({_to_int(torrent.get('logScore'))}%)")
    if _to_bool(torrent.get("hasCue")):
        quality_parts.append("Cue")
    lines = [
        " / ".join(part for part in release_parts if part),
        " / ".join(part for part in quality_parts if part),
    ]
    return "\n".join(line for line in lines if line) or None


def _promotion(torrent: dict[str, Any]) -> str | None:
    # DicMusic 只返回 isFreeleech / isPersonalFreeleech / isNeutralLeech，
    # 不返回 isFreeload；isFreeload 保留以便适配其它 Gazelle 站点。
    if _to_bool(torrent.get("isFreeload")) or _to_bool(torrent.get("isNeutralLeech")):
        return "0X"
    if _to_bool(torrent.get("isPersonalFreeleech")):
        return "免费"
    if _to_bool(torrent.get("isFreeleech")):
        return "免费"
    return None
