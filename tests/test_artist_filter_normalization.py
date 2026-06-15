from musicpilot.core.events import SearchResult
from musicpilot.infra.api.app import _filter_by_artist, normalize_search_text


def test_artist_filter_matches_traditional_artist_against_simplified_result() -> None:
    result = SearchResult(
        title="陈奕迅 - Special Thanks To...",
        download_url="https://example.test/eason",
        source="site",
    )

    assert _filter_by_artist([result], "陳奕迅") == [result]


def test_artist_filter_matches_simplified_artist_against_traditional_result() -> None:
    result = SearchResult(
        title="周杰倫 - 七里香 FLAC",
        download_url="https://example.test/jay",
        source="site",
    )

    assert _filter_by_artist([result], "周杰伦") == [result]


def test_search_normalization_unifies_width_case_and_ellipsis() -> None:
    assert normalize_search_text("Ｓｐｅｃｉａｌ　Ｔｈａｎｋｓ　Ｔｏ…") == "special thanks to..."


def test_search_normalization_uses_opencc_for_traditional_words() -> None:
    assert normalize_search_text("乾杯現場錄音專輯") == "干杯现场录音专辑"
