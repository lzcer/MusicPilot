import httpx
import pytest

from musicpilot.adapters.downloaders.qbittorrent import QBittorrentAuthError, QBittorrentClient
from musicpilot.adapters.indexers.config import parser_config_from_mapping
from musicpilot.adapters.indexers.nexusphp import NexusPHPCrawler, NexusPHPSiteConfig
from musicpilot.infra.api.app import _validate_navidrome_scan_response

PARSER = parser_config_from_mapping(
    {
        "list_selector": "tr",
        "fields": {
            "title": {"selector": "a[href*='details.php']"},
            "download": {"selector": "a[href*='download.php']", "attribute": "href"},
        },
    }
)


async def test_qbittorrent_login_rejects_non_ok_body() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/v2/auth/login"
        return httpx.Response(200, text="Fails.")

    client = httpx.AsyncClient(
        base_url="http://qbittorrent.local",
        transport=httpx.MockTransport(handler),
    )
    qbittorrent = QBittorrentClient(
        "http://qbittorrent.local",
        username="admin",
        password="wrong",
        client=client,
    )

    try:
        await qbittorrent.login()
    except QBittorrentAuthError:
        pass
    else:
        raise AssertionError("Expected invalid qBittorrent login to fail")
    finally:
        await client.aclose()


async def test_qbittorrent_test_connection_requires_authenticated_api() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/v2/auth/login":
            return httpx.Response(200, text="Ok.")
        if request.url.path == "/api/v2/torrents/info":
            return httpx.Response(200, json=[])
        return httpx.Response(404)

    client = httpx.AsyncClient(
        base_url="http://qbittorrent.local",
        transport=httpx.MockTransport(handler),
    )
    qbittorrent = QBittorrentClient(
        "http://qbittorrent.local",
        username="admin",
        password="secret",
        client=client,
    )

    await qbittorrent.test_connection()
    await client.aclose()


async def test_qbittorrent_reuses_authenticated_session_for_status_polling() -> None:
    login_count = 0

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal login_count
        if request.url.path == "/api/v2/auth/login":
            login_count += 1
            return httpx.Response(200, text="Ok.")
        if request.url.path == "/api/v2/torrents/info":
            return httpx.Response(200, json=[])
        return httpx.Response(404)

    client = httpx.AsyncClient(
        base_url="http://qbittorrent.local",
        transport=httpx.MockTransport(handler),
    )
    qbittorrent = QBittorrentClient(
        "http://qbittorrent.local",
        username="admin",
        password="secret",
        client=client,
    )

    await qbittorrent.list_statuses()
    await qbittorrent.list_statuses()

    assert login_count == 1
    await client.aclose()


async def test_qbittorrent_reauthenticates_when_session_expires() -> None:
    login_count = 0
    info_count = 0

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal login_count, info_count
        if request.url.path == "/api/v2/auth/login":
            login_count += 1
            return httpx.Response(200, text="Ok.")
        if request.url.path == "/api/v2/torrents/info":
            info_count += 1
            if info_count == 2:
                return httpx.Response(403)
            return httpx.Response(200, json=[])
        return httpx.Response(404)

    client = httpx.AsyncClient(
        base_url="http://qbittorrent.local",
        transport=httpx.MockTransport(handler),
    )
    qbittorrent = QBittorrentClient(
        "http://qbittorrent.local",
        username="admin",
        password="secret",
        client=client,
    )

    await qbittorrent.list_statuses()
    await qbittorrent.list_statuses()

    assert login_count == 2
    assert info_count == 3
    await client.aclose()


async def test_nexusphp_auth_test_rejects_login_page() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/torrents.php"
        return httpx.Response(
            200,
            html='<form action="takelogin.php"><input type="password" name="password"></form>',
        )

    client = httpx.AsyncClient(
        base_url="https://pt.local",
        transport=httpx.MockTransport(handler),
    )
    crawler = NexusPHPCrawler(
        NexusPHPSiteConfig(
            name="pt",
            base_url="https://pt.local/",
            parser=PARSER,
            cookie="uid=1; pass=bad",
        ),
        client=client,
    )

    result = await crawler.test_auth()

    assert result.ok is False
    assert "Cookie" in result.message
    await client.aclose()


async def test_nexusphp_auth_test_accepts_authenticated_marker() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/torrents.php"
        return httpx.Response(200, html='<a href="logout.php">logout</a>')

    client = httpx.AsyncClient(
        base_url="https://pt.local",
        transport=httpx.MockTransport(handler),
    )
    crawler = NexusPHPCrawler(
        NexusPHPSiteConfig(
            name="pt",
            base_url="https://pt.local/",
            parser=PARSER,
            cookie="uid=1; pass=good",
        ),
        client=client,
    )

    result = await crawler.test_auth()

    assert result.ok is True
    await client.aclose()


def test_navidrome_scan_response_accepts_subsonic_ok() -> None:
    response = httpx.Response(
        200,
        json={"subsonic-response": {"status": "ok"}},
        request=httpx.Request("GET", "https://music.local/rest/startScan.view"),
    )

    _validate_navidrome_scan_response(response)


def test_navidrome_scan_response_rejects_subsonic_error() -> None:
    response = httpx.Response(
        200,
        json={
            "subsonic-response": {
                "status": "failed",
                "error": {"code": 40, "message": "Wrong username or password"},
            }
        },
        request=httpx.Request("GET", "https://music.local/rest/startScan.view"),
    )

    with pytest.raises(RuntimeError, match="Wrong username or password"):
        _validate_navidrome_scan_response(response)


def test_navidrome_scan_response_rejects_non_json() -> None:
    response = httpx.Response(
        200,
        text="<html>login</html>",
        request=httpx.Request("GET", "https://music.local/rest/startScan.view"),
    )

    with pytest.raises(RuntimeError, match="non-JSON"):
        _validate_navidrome_scan_response(response)
