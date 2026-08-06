import asyncio
import json
from pathlib import Path

import httpx
import pytest

from musicpilot.adapters.indexers.gazelle import (
    GazelleCrawler,
    GazelleSiteConfig,
    _to_bool,
    _to_int,
)


async def test_gazelle_search_maps_group_and_torrent_metadata() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/ajax.php"
        assert dict(request.url.params) == {
            "action": "browse",
            "searchstr": "Kind of Blue",
            "filter_cat[1]": "1",
            "page": "1",
            "order_by": "time",
            "order_way": "desc",
        }
        assert request.headers["cookie"] == "session=valid"
        return httpx.Response(
            200,
            json={
                "status": "success",
                "response": {
                    "results": [
                        {
                            "groupId": 12,
                            "groupName": "Kind of Blue",
                            "groupYear": 1959,
                            "groupCategory": 1,
                            "releaseType": 1,
                            "tags": ["jazz", "modal.jazz"],
                            "artists": [{"name": "Miles Davis"}],
                            "torrents": [
                                {
                                    "torrentId": 34,
                                    "media": "CD",
                                    "format": "FLAC",
                                    "encoding": "Lossless",
                                    "hasLog": True,
                                    "logScore": 100,
                                    "hasCue": True,
                                    "remasterRecordLabel": "Columbia",
                                    "remasterCatalogueNumber": "CL 1355",
                                    "size": 1234,
                                    "seeders": 5,
                                    "leechers": 2,
                                    "time": "2026-08-06 01:02:03",
                                    "isFreeleech": True,
                                    "canUseToken": True,
                                }
                            ],
                        }
                    ]
                },
            },
        )

    client = httpx.AsyncClient(
        base_url="https://dicmusic.local",
        transport=httpx.MockTransport(handler),
    )
    crawler = GazelleCrawler(
        GazelleSiteConfig(
            name="DicMusic",
            base_url="https://dicmusic.local/",
            cookie="session=valid",
        ),
        client=client,
    )

    results = await crawler.search("Kind of Blue")

    assert len(results) == 1
    assert results[0].title == "Miles Davis - Kind of Blue - 1959"
    assert results[0].download_url == "https://dicmusic.local/torrents.php?action=download&id=34"
    assert results[0].details_url == "https://dicmusic.local/torrents.php?id=12"
    assert results[0].subtitle == (
        "Music / Columbia / CL 1355 / CD\nFLAC / Lossless / Log (100%) / Cue"
    )
    assert results[0].metadata["format"] == "FLAC"
    assert results[0].metadata["category"] == "Music"
    assert results[0].metadata["adapter"] == "gazelle"
    assert results[0].metadata["tags"] == ["jazz", "modal.jazz"]
    assert results[0].metadata["can_use_token"] is True
    assert results[0].promotion == "免费"
    await client.aclose()


async def test_gazelle_auth_test_requires_username() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        assert dict(request.url.params) == {"action": "index"}
        return httpx.Response(200, json={"status": "success", "response": {}})

    client = httpx.AsyncClient(
        base_url="https://dicmusic.local",
        transport=httpx.MockTransport(handler),
    )
    crawler = GazelleCrawler(
        GazelleSiteConfig(
            name="DicMusic",
            base_url="https://dicmusic.local/",
            cookie="session=valid",
        ),
        client=client,
    )

    result = await crawler.test_auth()

    assert result.ok is False
    await client.aclose()


def test_gazelle_promotion_prioritizes_freeload_and_personal_freeleech() -> None:
    crawler = GazelleCrawler(GazelleSiteConfig(name="DicMusic", base_url="https://dicmusic.local/"))
    group = {"groupId": 1, "groupName": "Album", "groupCategory": 1}

    freeload = crawler._search_result(group, {"torrentId": 2, "isFreeload": "true"})
    personal = crawler._search_result(group, {"torrentId": 3, "isPersonalFreeleech": True})

    assert freeload is not None and freeload.promotion == "0X"
    assert personal is not None and personal.promotion == "免费"


def test_gazelle_decodes_html_entities_in_release_metadata() -> None:
    crawler = GazelleCrawler(GazelleSiteConfig(name="DicMusic", base_url="https://dicmusic.local/"))

    result = crawler._search_result(
        {
            "groupId": 1,
            "groupName": "&#26469;&#26085;&#26041;&#38271;",
            "artist": "&#40644;&#40836;",
            "groupYear": 2017,
            "tags": ["&#21326;&#35821;"],
        },
        {"torrentId": 2},
    )

    assert result is not None
    assert result.title == "黄龄 - 来日方长 - 2017"
    assert result.metadata["tags"] == ["华语"]


async def test_gazelle_auth_test_rejects_invalid_cookie() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        assert dict(request.url.params) == {"action": "index"}
        return httpx.Response(403, json={"status": "failure"})

    client = httpx.AsyncClient(
        base_url="https://dicmusic.local",
        transport=httpx.MockTransport(handler),
    )
    crawler = GazelleCrawler(
        GazelleSiteConfig(
            name="DicMusic",
            base_url="https://dicmusic.local/",
            cookie="session=expired",
        ),
        client=client,
    )

    result = await crawler.test_auth()

    assert result.ok is False
    assert "Cookie" in result.message
    await client.aclose()


async def test_gazelle_download_uses_cookie_and_accepts_token_url() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/torrents.php"
        assert dict(request.url.params) == {"action": "download", "id": "34", "usetoken": "1"}
        assert request.headers["cookie"] == "session=valid"
        return httpx.Response(200, content=b"torrent")

    client = httpx.AsyncClient(
        base_url="https://dicmusic.local",
        transport=httpx.MockTransport(handler),
    )
    crawler = GazelleCrawler(
        GazelleSiteConfig(
            name="DicMusic",
            base_url="https://dicmusic.local/",
            cookie="session=valid",
        ),
        client=client,
    )

    assert (
        await crawler.download_torrent(
            "https://dicmusic.local/torrents.php?action=download&id=34&usetoken=1"
        )
        == b"torrent"
    )
    await client.aclose()


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (True, True),
        (False, False),
        (1, True),
        (0, False),
        (1.0, True),
        (0.0, False),
        ("1", True),
        ("0", False),
        ("true", True),
        ("True", True),
        ("yes", True),
        ("on", True),
        ("false", False),
        ("", False),
        (None, False),
    ],
)
def test_gazelle_to_bool_handles_int_and_string_forms(value: object, expected: bool) -> None:
    assert _to_bool(value) is expected


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (5, 5),
        (5.9, 5),
        ("5", 5),
        ("5.0", 5),
        ("5.9", 5),
        ("1,234", 1234),
        ("1 234", 1234),
        ("", 0),
        (None, 0),
        ("abc", 0),
        (True, 1),
    ],
)
def test_gazelle_to_int_handles_floats_and_separators(value: object, expected: int) -> None:
    assert _to_int(value) == expected


@pytest.mark.parametrize(
    "download_url",
    [
        "https://evil.local/torrents.php?action=download&id=34",
        "ftp://dicmusic.local/torrents.php?action=download&id=34",
        "https://dicmusic.local/other.php?action=download&id=34",
        "https://dicmusic.local/torrents.php?action=view&id=34",
        "https://dicmusic.local/torrents.php?action=download&id=abc",
        "https://dicmusic.local/torrents.php?action=download&id=1&id=2",
        "https://dicmusic.local/torrents.php?action=download&id=34&evil=1",
        "https://dicmusic.local/torrents.php?action=download",
    ],
)
async def test_gazelle_download_rejects_unsafe_url(download_url: str) -> None:
    crawler = GazelleCrawler(
        GazelleSiteConfig(name="DicMusic", base_url="https://dicmusic.local/", cookie="s=1")
    )

    with pytest.raises(RuntimeError, match="种子下载地址无效"):
        await crawler.download_torrent(download_url)


async def test_gazelle_enforces_min_request_interval_between_requests() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"status": "success", "response": {"username": "u"}})

    client = httpx.AsyncClient(
        base_url="https://dicmusic.local",
        transport=httpx.MockTransport(handler),
    )
    crawler = GazelleCrawler(
        GazelleSiteConfig(
            name="DicMusic",
            base_url="https://dicmusic.local/",
            cookie="session=valid",
            min_request_interval=0.2,
        ),
        client=client,
    )

    loop = asyncio.get_running_loop()
    started = loop.time()
    await crawler.test_auth()
    await crawler.test_auth()
    elapsed = loop.time() - started

    assert elapsed >= 0.2
    await client.aclose()


async def test_gazelle_rate_limiter_does_not_hold_lock_while_sleeping() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"status": "success", "response": {"username": "u"}})

    client = httpx.AsyncClient(
        base_url="https://dicmusic.local",
        transport=httpx.MockTransport(handler),
    )
    crawler = GazelleCrawler(
        GazelleSiteConfig(
            name="DicMusic",
            base_url="https://dicmusic.local/",
            cookie="session=valid",
            max_concurrency=4,
            min_request_interval=0.1,
        ),
        client=client,
    )

    loop = asyncio.get_running_loop()
    started = loop.time()
    await asyncio.gather(*(crawler.test_auth() for _ in range(4)))
    elapsed = loop.time() - started

    # 4 serialized requests => at least 3 intervals, and the lock must not
    # serialize them any worse than that.
    assert 0.3 <= elapsed < 1.5
    await client.aclose()


async def test_gazelle_retries_after_429_and_honours_retry_after_header() -> None:
    calls: list[float] = []
    loop_holder: dict[str, object] = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        loop = loop_holder["loop"]
        calls.append(loop.time())  # type: ignore[union-attr]
        if len(calls) == 1:
            return httpx.Response(429, headers={"Retry-After": "0.3"}, json={"status": "failure"})
        return httpx.Response(200, json={"status": "success", "response": {"username": "u"}})

    client = httpx.AsyncClient(
        base_url="https://dicmusic.local",
        transport=httpx.MockTransport(handler),
    )
    crawler = GazelleCrawler(
        GazelleSiteConfig(
            name="DicMusic",
            base_url="https://dicmusic.local/",
            cookie="session=valid",
            min_request_interval=0.0,
        ),
        client=client,
    )
    loop_holder["loop"] = asyncio.get_running_loop()

    result = await crawler.test_auth()

    assert result.ok is True
    assert len(calls) == 2
    assert calls[1] - calls[0] >= 0.3
    await client.aclose()


async def test_gazelle_raises_when_429_persists() -> None:
    calls = 0

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(429, headers={"Retry-After": "0"}, json={"status": "failure"})

    client = httpx.AsyncClient(
        base_url="https://dicmusic.local",
        transport=httpx.MockTransport(handler),
    )
    crawler = GazelleCrawler(
        GazelleSiteConfig(
            name="DicMusic",
            base_url="https://dicmusic.local/",
            cookie="session=valid",
            min_request_interval=0.0,
        ),
        client=client,
    )

    with pytest.raises(RuntimeError, match="请求过于频繁"):
        await crawler._get_json("ajax.php", {"action": "index"})

    assert calls == crawler._MAX_RATE_LIMIT_RETRIES + 1
    await client.aclose()


def _browse_page(page: int, pages: int, torrent_id: int) -> dict[str, object]:
    return {
        "status": "success",
        "response": {
            "pages": pages,
            "results": [
                {
                    "groupId": torrent_id,
                    "groupName": f"Album {torrent_id}",
                    "groupCategory": 1,
                    "torrents": [{"torrentId": torrent_id}],
                }
            ],
        },
    }


async def test_gazelle_search_returns_partial_results_when_later_page_fails() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        page = int(request.url.params["page"])
        if page == 1:
            return httpx.Response(200, json=_browse_page(1, 5, 1))
        return httpx.Response(500, json={"status": "failure"})

    client = httpx.AsyncClient(
        base_url="https://dicmusic.local",
        transport=httpx.MockTransport(handler),
    )
    crawler = GazelleCrawler(
        GazelleSiteConfig(
            name="DicMusic",
            base_url="https://dicmusic.local/",
            cookie="session=valid",
            min_request_interval=0.0,
        ),
        client=client,
    )

    results = await crawler.search("album", limit=10)

    assert len(results) == 1
    await client.aclose()


async def test_gazelle_search_propagates_first_page_failure() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"status": "failure"})

    client = httpx.AsyncClient(
        base_url="https://dicmusic.local",
        transport=httpx.MockTransport(handler),
    )
    crawler = GazelleCrawler(
        GazelleSiteConfig(
            name="DicMusic",
            base_url="https://dicmusic.local/",
            cookie="session=valid",
            min_request_interval=0.0,
        ),
        client=client,
    )

    with pytest.raises(RuntimeError):
        await crawler.search("album", limit=10)

    await client.aclose()


async def test_gazelle_search_stops_when_page_yields_no_usable_result() -> None:
    calls = 0

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(
            200,
            json={
                "status": "success",
                "response": {
                    "pages": 999,
                    # Group with no torrents => parses to zero results.
                    "results": [{"groupId": 1, "groupName": "Album", "torrents": []}],
                },
            },
        )

    client = httpx.AsyncClient(
        base_url="https://dicmusic.local",
        transport=httpx.MockTransport(handler),
    )
    crawler = GazelleCrawler(
        GazelleSiteConfig(
            name="DicMusic",
            base_url="https://dicmusic.local/",
            cookie="session=valid",
            min_request_interval=0.0,
        ),
        client=client,
    )

    results = await crawler.search("album", limit=10)

    assert results == ()
    assert calls == 1
    await client.aclose()


async def test_gazelle_search_uses_configured_music_category_id() -> None:
    seen: list[str] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        seen.extend(k for k in request.url.params if k.startswith("filter_cat"))
        return httpx.Response(200, json=_browse_page(1, 1, 1))

    client = httpx.AsyncClient(
        base_url="https://dicmusic.local",
        transport=httpx.MockTransport(handler),
    )
    crawler = GazelleCrawler(
        GazelleSiteConfig(
            name="DicMusic",
            base_url="https://dicmusic.local/",
            cookie="session=valid",
            min_request_interval=0.0,
            music_category_id=7,
        ),
        client=client,
    )

    await crawler.search("album", limit=1)

    assert seen == ["filter_cat[7]"]
    await client.aclose()


async def test_gazelle_error_messages_use_configured_site_name() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(403, json={"status": "failure"})

    client = httpx.AsyncClient(
        base_url="https://other.local",
        transport=httpx.MockTransport(handler),
    )
    crawler = GazelleCrawler(
        GazelleSiteConfig(
            name="OtherGazelle",
            base_url="https://other.local/",
            cookie="session=expired",
        ),
        client=client,
    )

    result = await crawler.test_auth()

    assert "OtherGazelle" in result.message
    assert "DicMusic" not in result.message
    await client.aclose()


_FIXTURES = Path(__file__).parent / "fixtures"


def _load_fixture(name: str) -> dict[str, object]:
    return json.loads((_FIXTURES / name).read_text(encoding="utf-8"))


def _dicmusic_crawler(**kwargs: object) -> GazelleCrawler:
    return GazelleCrawler(
        GazelleSiteConfig(name="DicMusic", base_url="https://dicmusic.com/", **kwargs)  # type: ignore[arg-type]
    )


@pytest.mark.parametrize("fixture", ["dicmusic_browse.json", "dicmusic_search.json"])
def test_gazelle_parses_real_dicmusic_response_without_dropping_torrents(fixture: str) -> None:
    payload = _load_fixture(fixture)
    groups = payload["response"]["results"]  # type: ignore[index]
    expected = sum(len(g["torrents"]) for g in groups)  # type: ignore[index,union-attr]

    results = _dicmusic_crawler()._parse_results(groups, 10**6)  # type: ignore[arg-type]

    assert len(results) == expected
    for result in results:
        assert result.title
        assert result.download_url.startswith("https://dicmusic.com/torrents.php?action=download&")
        assert result.size_bytes and result.size_bytes > 0
        assert result.seeders is not None
        assert result.published_at
        assert result.metadata["category"] == "Music"
        assert result.metadata["adapter"] == "gazelle"


def test_gazelle_real_response_decodes_cjk_and_keeps_edition_metadata() -> None:
    groups = _load_fixture("dicmusic_browse.json")["response"]["results"]  # type: ignore[index]
    results = _dicmusic_crawler()._parse_results(groups, 10**6)  # type: ignore[arg-type]

    # HTML entities in real payloads must be decoded, never leaked as "&#...;".
    assert not any("&#" in result.title for result in results)
    assert any(any("\u4e00" <= ch <= "\u9fff" for ch in result.title) for result in results)

    # DicMusic returns remasterCatalogueNumber/remasterYear (no remasterRecordLabel).
    editions = [r for r in results if r.metadata.get("catalogue_number")]
    assert editions, "fixture should contain at least one remastered edition"
    for result in editions:
        assert result.metadata["catalogue_number"] in (result.subtitle or "")
        assert result.metadata["remaster_year"]


def test_gazelle_real_response_has_no_freeleech_but_freeload_still_supported() -> None:
    groups = _load_fixture("dicmusic_browse.json")["response"]["results"]  # type: ignore[index]
    results = _dicmusic_crawler()._parse_results(groups, 10**6)  # type: ignore[arg-type]

    # DicMusic never returns isFreeload; promotion must not crash on its absence.
    assert all(r.metadata["freeload"] is False for r in results)

    # isFreeload is retained for other Gazelle sites.
    crawler = _dicmusic_crawler()
    result = crawler._search_result(
        {"groupId": 1, "groupName": "Album"}, {"torrentId": 2, "isFreeload": True}
    )
    assert result is not None
    assert result.promotion == "0X"
    assert result.metadata["freeload"] is True


def test_gazelle_real_response_pages_field_drives_pagination_stop() -> None:
    search = _load_fixture("dicmusic_search.json")
    browse = _load_fixture("dicmusic_browse.json")

    # Real payloads expose an int "pages"; _to_int must read it unchanged.
    assert _to_int(search["response"]["pages"]) == 1  # type: ignore[index]
    assert _to_int(browse["response"]["pages"]) == browse["response"]["pages"]  # type: ignore[index]
