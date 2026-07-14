from pathlib import Path

from musicpilot.adapters.indexers.config import build_nexusphp_indexers, load_parser_catalog


def test_load_parser_catalog_returns_empty_catalog_for_missing_file(tmp_path: Path) -> None:
    assert load_parser_catalog(tmp_path / "missing.yaml").entries == ()


def test_build_nexusphp_indexers_uses_parser_catalog_base_url_match(tmp_path: Path) -> None:
    parser_path = tmp_path / "sites.parser.yaml"
    parser_path.write_text(
        """
sites:
  - name: pt
    base_url: https://pt.local/
    parser:
      list_selector: "tr"
      fields:
        title:
          selector: "a[href*='details.php']"
        download:
          selector: "a[href*='download.php']"
          attribute: href
""",
        encoding="utf-8",
    )

    catalog = load_parser_catalog(parser_path)
    crawlers = build_nexusphp_indexers(
        [
            {
                "name": "pt",
                "base_url": "https://pt.local/",
                "cookie": "uid=1",
                "max_concurrency": 2,
            },
            {
                "name": "unsupported",
                "base_url": "https://unsupported.local/",
            },
        ],
        catalog,
    )

    assert len(crawlers) == 1
    assert crawlers[0].name == "pt"


def test_jpopsuki_uses_advanced_html_music_search() -> None:
    catalog = load_parser_catalog(Path("config/sites.parser.yaml"))
    entry = catalog.match("https://jpopsuki.eu")

    assert entry is not None
    assert entry.adapter == "nexusphp"
    assert entry.parser is not None
    assert entry.parser.search_query_param == "torrentname"
    assert entry.parser.search_params["action"] == "advanced"
    assert entry.parser.search_params["filter_cat[1]"] == "1"
    assert entry.parser.search_params["filter_cat[2]"] == "1"
