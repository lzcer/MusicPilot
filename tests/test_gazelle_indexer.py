from pathlib import Path

import httpx
import pytest

from musicpilot.adapters.indexers.config import build_indexers, load_parser_catalog
from musicpilot.adapters.indexers.gazelle import GazelleCrawler, GazelleSiteConfig


def _crawler(client: httpx.AsyncClient) -> GazelleCrawler:
    return GazelleCrawler(
        GazelleSiteConfig(
            name="Redacted",
            base_url="https://redacted.local",
            cookie="session=good",
        ),
        client=client,
    )


async def test_gazelle_search_parses_torrents_and_paginates() -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        assert request.headers["cookie"] == "session=good"
        page = request.url.params["page"]
        results = [
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
        ]
        return httpx.Response(
            200,
            json={"status": "success", "response": {"pages": 2, "results": results}},
        )

    client = httpx.AsyncClient(
        base_url="https://redacted.local",
        transport=httpx.MockTransport(handler),
    )
    results = await _crawler(client).search("Artist Album", limit=2)

    assert [request.url.params["page"] for request in requests] == ["1", "2"]
    assert requests[0].url.params["filter_cat[1]"] == "1"
    assert requests[0].url.params["order_by"] == "time"
    assert requests[0].url.params["order_way"] == "desc"
    assert len(results) == 2
    assert results[0].title == "Artist - Album"
    assert results[0].subtitle == "CD / FLAC / Lossless"
    assert results[0].promotion == "FREE"
    assert results[1].subtitle == "2025 Deluxe / CD / FLAC / Lossless"
    assert results[0].metadata["year"] == 2024
    await client.aclose()


async def test_gazelle_auth_detects_invalid_cookie() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(403)

    client = httpx.AsyncClient(
        base_url="https://redacted.local",
        transport=httpx.MockTransport(handler),
    )
    result = await _crawler(client).test_auth()

    assert result.ok is False
    assert "Cookie" in result.message
    await client.aclose()


async def test_gazelle_download_validates_url_and_returns_torrent() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/torrents.php"
        assert request.url.params == {"action": "download", "id": "42"}
        assert request.headers["accept"] == "application/x-bittorrent"
        return httpx.Response(200, content=b"d8:announce1:ae")

    client = httpx.AsyncClient(
        base_url="https://redacted.local",
        transport=httpx.MockTransport(handler),
    )
    crawler = _crawler(client)

    url = "https://redacted.local/torrents.php?action=download&id=42"
    assert await crawler.download_torrent(url) == b"d8:announce1:ae"
    with pytest.raises(RuntimeError, match="地址无效"):
        await crawler.download_torrent("https://other.local/torrents.php?action=download&id=42")
    await client.aclose()


def test_gazelle_promotion_uses_musicpilot_display_values() -> None:
    from musicpilot.adapters.indexers.gazelle import _promotion

    assert _promotion({"isFreeload": True}) == "FREE"
    assert _promotion({"isPersonalFreeleech": True}) == "FREE"
    assert _promotion({"isNeutralLeech": True}) == "0X"


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
