from pathlib import Path

from musicpilot.adapters.indexers.config import build_nexusphp_indexers, load_parser_catalog
from musicpilot.adapters.indexers.gazelle import GazelleCrawler


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


def test_build_indexers_uses_gazelle_adapter(tmp_path: Path) -> None:
    parser_path = tmp_path / "sites.parser.yaml"
    parser_path.write_text(
        """
sites:
  - name: DicMusic
    base_url: https://dicmusic.local/
    adapter: gazelle
""",
        encoding="utf-8",
    )

    crawlers = build_nexusphp_indexers(
        [{"name": "DicMusic", "base_url": "https://dicmusic.local/", "cookie": "session=1"}],
        load_parser_catalog(parser_path),
    )

    assert len(crawlers) == 1
    assert isinstance(crawlers[0], GazelleCrawler)
