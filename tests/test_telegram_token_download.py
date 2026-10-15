from musicpilot.adapters.bots.telegram import _can_use_token, _token_download_url
from musicpilot.core.events import SearchResult


def test_telegram_token_download_url_preserves_gazelle_download_query() -> None:
    assert _token_download_url("https://dicmusic.com/torrents.php?action=download&id=34") == (
        "https://dicmusic.com/torrents.php?action=download&id=34&usetoken=1"
    )


def test_telegram_token_download_is_limited_to_eligible_gazelle_results() -> None:
    result = SearchResult(
        title="Album",
        download_url="https://dicmusic.com/torrents.php?action=download&id=34",
        source="DicMusic",
        metadata={"adapter": "gazelle", "can_use_token": True},
    )

    assert _can_use_token(result) is True
    assert _can_use_token(
        SearchResult(
            title="Album",
            download_url="https://dicmusic.com/torrents.php?action=download&id=34",
            source="DicMusic",
            metadata={"adapter": "gazelle", "can_use_token": False},
        )
    ) is False
