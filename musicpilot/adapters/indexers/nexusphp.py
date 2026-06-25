from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass, field
from urllib.parse import urljoin

import httpx
from bs4 import BeautifulSoup
from bs4.element import Tag

from musicpilot.core.events import SearchResult


@dataclass(frozen=True, slots=True)
class FieldRule:
    selector: str
    attribute: str = "text"
    regex: str | None = None
    index: int | None = None
    remove: tuple[str, ...] = ()
    filters: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class NexusPHPParserConfig:
    list_selector: str = (
        "table.torrents tr:has(a[href*='details.php']):has(a[href*='download.php'])"
    )
    fields: dict[str, FieldRule] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class NexusPHPSiteConfig:
    name: str
    base_url: str
    parser: NexusPHPParserConfig
    site_id: str | None = None
    cookie: str | None = None
    max_concurrency: int = 2
    user_agent: str | None = None


@dataclass(frozen=True, slots=True)
class SiteAuthCheck:
    ok: bool
    message: str


class NexusPHPCrawler:
    def __init__(self, config: NexusPHPSiteConfig, client: httpx.AsyncClient | None = None) -> None:
        self.config = config
        self._client = client
        self._semaphore = asyncio.Semaphore(config.max_concurrency)

    @property
    def name(self) -> str:
        return self.config.name

    async def close(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def search(self, query: str, *, limit: int = 20) -> tuple[SearchResult, ...]:
        headers = self._headers()

        async with self._semaphore:
            if self._client is None:
                async with httpx.AsyncClient(http2=True, timeout=20) as client:
                    html = await self._fetch(client, query, headers)
            else:
                html = await self._fetch(self._client, query, headers)

        return self._parse_results(html, limit)

    async def test_auth(self) -> SiteAuthCheck:
        if not self.config.cookie or not self.config.cookie.strip():
            return SiteAuthCheck(False, "Cookie 不能为空，无法验证站点登录状态。")

        try:
            if self._client is None:
                async with httpx.AsyncClient(
                    http2=True,
                    timeout=20,
                    follow_redirects=True,
                ) as client:
                    response = await client.get(
                        urljoin(self.config.base_url, "torrents.php"),
                        headers=self._headers(),
                    )
            else:
                response = await self._client.get(
                    urljoin(self.config.base_url, "torrents.php"),
                    headers=self._headers(),
                )
            response.raise_for_status()
        except Exception as exc:  # noqa: BLE001
            return SiteAuthCheck(False, f"站点连接失败：{exc}")

        html = response.text
        if _looks_like_login_page(str(response.url), html):
            return SiteAuthCheck(False, "站点返回登录页，Cookie 无效或已过期。")

        soup = BeautifulSoup(html, "lxml")
        if self._has_authenticated_marker(soup):
            return SiteAuthCheck(True, f"站点登录状态有效，状态码 {response.status_code}。")

        if soup.select_one(self.config.parser.list_selector):
            return SiteAuthCheck(True, f"站点页面可解析，状态码 {response.status_code}。")

        return SiteAuthCheck(
            False,
            "站点可访问，但无法确认已登录。请检查 Cookie、UA 或站点解析配置。",
        )

    async def _fetch(
        self,
        client: httpx.AsyncClient,
        query: str,
        headers: dict[str, str],
    ) -> str:
        url = urljoin(self.config.base_url, "torrents.php")
        response = await client.get(url, params={"search": query}, headers=headers)
        response.raise_for_status()
        return response.text

    def _headers(self) -> dict[str, str]:
        headers = {}
        if self.config.cookie:
            headers["Cookie"] = self.config.cookie
        if self.config.user_agent:
            headers["User-Agent"] = self.config.user_agent
        return headers

    def _has_authenticated_marker(self, soup: BeautifulSoup) -> bool:
        authenticated_hrefs = (
            "logout.php",
            "userdetails.php",
            "usercp.php",
            "messages.php",
            "mybonus.php",
            "attendance.php",
        )
        for anchor in soup.select("a[href]"):
            href = str(anchor.get("href", "")).lower()
            if any(marker in href for marker in authenticated_hrefs):
                return True

        fields = self.config.parser.fields
        return bool(
            _first_selected(soup, fields["title"])
            and _first_selected(soup, fields["download"])
        )

    def _parse_results(self, html: str, limit: int) -> tuple[SearchResult, ...]:
        parser = self.config.parser
        fields = parser.fields
        required_fields = ("title", "download")
        missing = [name for name in required_fields if name not in fields]
        if missing:
            raise ValueError(f"NexusPHP parser missing required field(s): {', '.join(missing)}")

        soup = BeautifulSoup(html, "lxml")
        results: list[SearchResult] = []
        seen: set[str] = set()

        for row in soup.select(parser.list_selector):
            if not isinstance(row, Tag):
                continue
            title = _extract_field(row, fields["title"])
            download_href = _extract_field(row, fields["download"])
            if not title or not download_href:
                continue

            details_href = _extract_field(row, fields.get("details"))
            subtitle = _extract_field(row, fields.get("subtitle"))
            if subtitle:
                subtitle = _clean_subtitle(subtitle, title)

            result = SearchResult(
                title=title,
                download_url=urljoin(self.config.base_url, download_href),
                details_url=urljoin(self.config.base_url, details_href)
                if details_href
                else None,
                source=self.config.name,
                seeders=_parse_int(_extract_field(row, fields.get("seeders")) or ""),
                leechers=_parse_int(_extract_field(row, fields.get("leechers")) or ""),
                size_bytes=_parse_size(_extract_field(row, fields.get("size")) or ""),
                subtitle=subtitle,
                published_at=_extract_field(row, fields.get("published_at")),
                promotion=_normalize_promotion(_extract_field(row, fields.get("promotion"))),
            )
            key = result.details_url or result.download_url
            if key in seen:
                continue
            seen.add(key)
            results.append(result)
            if len(results) >= limit:
                break

        return tuple(results)


def _extract_field(row: Tag | BeautifulSoup, rule: FieldRule | None) -> str | None:
    if rule is None:
        return None
    nodes = row.select(rule.selector)
    if not nodes:
        return None
    candidates = [_select_index(nodes, rule.index)] if rule.index is not None else nodes
    for node in candidates:
        if node is None:
            continue
        value = _read_node_value(node, rule.attribute)
        for selector in rule.remove:
            for removable in node.select(selector):
                removable.extract()
            value = _read_node_value(node, rule.attribute)
        value = _apply_filters(value, rule.filters)
        if rule.regex:
            match = re.search(rule.regex, value, re.IGNORECASE)
            if not match:
                continue
            value = match.group(1) if match.groups() else match.group(0)
        if value.strip():
            return value.strip()
    return None


def _first_selected(row: Tag | BeautifulSoup, rule: FieldRule) -> Tag | None:
    nodes = row.select(rule.selector)
    node = _select_index(nodes, rule.index)
    return node if isinstance(node, Tag) else None


def _select_index(nodes: list[Tag], index: int | None) -> Tag | None:
    if not nodes:
        return None
    selected_index = 0 if index is None else index
    try:
        return nodes[selected_index]
    except IndexError:
        return None


def _read_node_value(node: Tag, attribute: str) -> str:
    if attribute == "text":
        return node.get_text(" ", strip=True)
    if attribute == "text+attrs":
        parts = [node.get_text(" ", strip=True)]
        for candidate in [node, *node.select("[title], [alt], [datetime], [class], img[src]")]:
            for key in ("title", "alt", "datetime", "class", "src"):
                value = candidate.get(key)
                if isinstance(value, list):
                    parts.append(" ".join(str(item) for item in value))
                elif isinstance(value, str):
                    parts.append(value)
        return " ".join(part for part in parts if part)
    value = node.get(attribute)
    if isinstance(value, list):
        return " ".join(str(item) for item in value)
    return str(value or "")


def _apply_filters(value: str, filters: tuple[str, ...]) -> str:
    result = value
    for name in filters:
        if name == "strip_brackets":
            result = re.sub(r"^\s*[\[銆怾.*?[\]銆慮\s*", "", result)
        elif name == "collapse_space":
            result = re.sub(r"\s+", " ", result)
        elif name == "date":
            result = _first_match(result, _DATE_PATTERN, _SHORT_DATE_PATTERN)
        elif name == "promotion":
            result = _first_promotion_marker(result)
    return result.strip()


def _first_match(value: str, *patterns: re.Pattern[str]) -> str:
    for pattern in patterns:
        match = pattern.search(value)
        if match:
            return match.group(0)
    return ""


def _first_promotion_marker(value: str) -> str:
    lowered = value.lower()
    for marker, label in _PROMOTION_MARKERS:
        if marker in lowered:
            return label
    return ""


def _clean_subtitle(subtitle: str, title: str) -> str | None:
    cleaned = subtitle.replace(title, "", 1).strip(" -\n\t")
    return cleaned[:300] or None


def _normalize_promotion(value: str | None) -> str | None:
    if not value:
        return None
    normalized = _first_promotion_marker(value) or value.strip()
    return normalized or None


def _parse_int(value: str) -> int:
    match = re.search(r"\d[\d,]*", value)
    if not match:
        return 0
    return int(match.group(0).replace(",", ""))


def _parse_size(value: str) -> int | None:
    match = re.search(r"(\d+(?:\.\d+)?)\s*([KMGT]i?B|[KMGT]B)", value, re.IGNORECASE)
    if not match:
        return None
    amount = float(match.group(1))
    unit = match.group(2).upper().replace("IB", "B")
    factor = {
        "KB": 1024,
        "MB": 1024**2,
        "GB": 1024**3,
        "TB": 1024**4,
    }.get(unit)
    return int(amount * factor) if factor else None


def _looks_like_login_page(url: str, html: str) -> bool:
    lowered_url = url.lower()
    lowered_html = html.lower()
    if any(marker in lowered_url for marker in ("login", "takelogin", "signup")):
        return True
    login_markers = (
        'type="password"',
        'name="password"',
        "name='password'",
        "takelogin.php",
        "login.php",
        "用户名",
        "密码",
    )
    success_markers = ("logout.php", "userdetails.php", "usercp.php", "messages.php")
    return any(marker in lowered_html for marker in login_markers) and not any(
        marker in lowered_html for marker in success_markers
    )


_DATE_PATTERN = re.compile(
    r"\b\d{4}[-/]\d{1,2}[-/]\d{1,2}(?:\s+\d{1,2}:\d{2}(?::\d{2})?)?\b"
)
_SHORT_DATE_PATTERN = re.compile(r"\b\d{1,2}[-/]\d{1,2}\s+\d{1,2}:\d{2}\b")
_PROMOTION_MARKERS = (
    ("热门", "热门"),
    ("hot", "热门"),
    ("推荐", "推荐"),
    ("置顶", "置顶"),
    ("pro_free2up", "免费 / 2X"),
    ("free2up", "免费 / 2X"),
    ("2xfree", "免费 / 2X"),
    ("twoupfree", "免费 / 2X"),
    ("pro_free", "免费"),
    ("免费", "免费"),
    ("free", "免费"),
    ("pro_2up", "2X"),
    ("twoup", "2X"),
    ("2x", "2X"),
    ("2up", "2X"),
    ("pro_50pctdown", "50%"),
    ("halfdown", "50%"),
    ("50%", "50%"),
    ("促销", "促销"),
)
