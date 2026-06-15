from musicpilot.infra.api.app import _aggregate_media_candidates, _metadata_search_keywords
from musicpilot.infra.api.schemas import MediaCandidateResponse
from musicpilot.ports.metadata import MediaCandidate


def test_metadata_search_keywords_include_ascii_ellipsis_variant() -> None:
    keywords = _metadata_search_keywords(
        MediaCandidateResponse(
            title="Special Thanks To…",
            artist="Eason Chan",
            album="Special Thanks To…",
            albums=["Special Thanks To…"],
            source="musicbrainz",
            external_id="recording-id",
        )
    )

    assert keywords == ["Special Thanks To...", "Special Thanks To…"]


def test_metadata_search_keywords_use_title_and_each_album_only() -> None:
    keywords = _metadata_search_keywords(
        MediaCandidateResponse(
            title="你的背包",
            artist="陈奕迅",
            album="Special Thanks To...",
            albums=["Special Thanks To...", "The Line-Up"],
            source="musicbrainz",
            external_id="recording-id",
        )
    )

    assert keywords == ["你的背包", "Special Thanks To...", "The Line-Up"]


def test_aggregate_media_candidates_merges_same_title_and_artist_albums() -> None:
    candidates = [
        MediaCandidate(
            title="你的背包",
            artist="陈奕迅",
            album="Special Thanks To...",
            source="musicbrainz",
            external_id="recording-id-1",
        ),
        MediaCandidate(
            title="你的背包",
            artist="陈奕迅",
            album="The Line-Up",
            source="musicbrainz",
            external_id="recording-id-2",
        ),
    ]

    aggregated = _aggregate_media_candidates(candidates, limit=10)

    assert len(aggregated) == 1
    assert aggregated[0].title == "你的背包"
    assert aggregated[0].artist == "陈奕迅"
    assert aggregated[0].albums == ["Special Thanks To...", "The Line-Up"]
