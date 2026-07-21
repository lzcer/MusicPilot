from pathlib import Path

import httpx
import pytest

from musicpilot.adapters.indexers.config import build_indexers, load_parser_catalog
from musicpilot.adapters.indexers.gazelle import GazelleCrawler, GazelleSiteConfig, _promotion


def _crawler(client: httpx.AsyncClient, *, request_interval: float = 0) -> GazelleCrawler:
    return GazelleCrawler(
        GazelleSiteConfig(
            name="Redacted",
            base_url="https://redacted.local",
            cookie="session=good",
            request_interval=request_interval,
        ),
        client=client,
    )


async def test_gazelle_search_parses_torrents_and_paginates() -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        page = request.url.params["page"]
        return httpx.Response(
            200,
            json={
                "status": "success",
                "response": {
                    "pages": 2,
                    "results": [
                        {
                            "groupId": 1,
                            "groupName": "Album",
                            "groupYear": 2024,
                            "releaseType": "Album",
                            "artists": [{"name": "Artist"}],
                            "torrents": [
                                {
                                    "torrentId": page,
                                    "media": "CD",
                                    "format": "FLAC",
                                    "encoding": "Lossless",
                                    "remastered": page == "2",
                                    "remasterYear": 2025,
                                    "remasterTitle": "Deluxe",
                                    "size": 123,
                                    "seeders": 4,
                                    "leechers": 2,
                                    "time": "2025-01-01 00:00:00",
                                    "isFreeload": page == "1",
                                }
                            ],
                        }
                    ],
                },
            },
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    results = await _crawler(client).search("Artist Album", limit=2)

    assert [request.url.params["page"] for request in requests] == ["1", "2"]
    assert requests[0].url.params["filter_cat[1]"] == "1"
    assert requests[0].headers["cookie"] == "session=good"
    assert results[0].title == "Artist - Album"
    assert results[0].subtitle == "CD / FLAC / Lossless"
    assert results[0].promotion == "0X"
    assert results[1].subtitle == "2025 Deluxe / CD / FLAC / Lossless"
    await client.aclose()


async def test_gazelle_retries_rate_limited_request_after_retry_after() -> None:
    calls = 0

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            return httpx.Response(429, headers={"Retry-After": "0"})
        return httpx.Response(
            200, json={"status": "success", "response": {"pages": 0, "results": []}}
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    assert await _crawler(client).search("Artist") == ()
    assert calls == 2
    await client.aclose()


async def test_gazelle_auth_and_download() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        if request.url.params.get("action") == "index":
            return httpx.Response(200, json={"status": "success", "response": {"username": "user"}})
        assert request.headers["accept"] == "application/x-bittorrent"
        return httpx.Response(200, content=b"d8:announce1:ae")

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    crawler = _crawler(client)
    assert (await crawler.test_auth()).ok is True
    assert await crawler.download_torrent(
        "https://redacted.local/torrents.php?action=download&id=42"
    ) == b"d8:announce1:ae"
    with pytest.raises(RuntimeError, match="地址无效"):
        await crawler.download_torrent("https://other.local/torrents.php?action=download&id=42")
    await client.aclose()


def test_gazelle_promotion_uses_correct_display_values() -> None:
    assert _promotion({"isFreeload": True}) == "0X"
    assert _promotion({"isNeutralLeech": True}) == "0X"
    assert _promotion({"isPersonalFreeleech": True}) == "FREE"
    assert _promotion({"isFreeleech": True}) == "FREE"


def test_catalog_builds_gazelle_adapter(tmp_path: Path) -> None:
    path = tmp_path / "sites.yaml"
    path.write_text(
        "sites:\n  - name: Redacted\n    base_url: https://redacted.local\n    adapter: gazelle\n",
        encoding="utf-8",
    )

    crawlers = build_indexers(
        [{"name": "Redacted", "base_url": "https://redacted.local", "cookie": "session=good"}],
        load_parser_catalog(path),
    )

    assert len(crawlers) == 1
    assert isinstance(crawlers[0], GazelleCrawler)


def test_builtin_catalog_registers_supported_gazelle_music_sites() -> None:
    catalog = load_parser_catalog(Path("config/sites.parser.yaml"))

    assert [
        catalog.match(url).name if catalog.match(url) is not None else None
        for url in (
            "https://redacted.sh",
            "https://dicmusic.com",
            "https://orpheus.network",
            "https://desigaane.rocks",
        )
    ] == ["Redacted", "DicMusic", "Orpheus", "DesiGaane"]
