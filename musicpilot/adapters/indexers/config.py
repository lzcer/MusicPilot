from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import yaml

from musicpilot.adapters.indexers.nexusphp import (
    FieldRule,
    NexusPHPCrawler,
    NexusPHPParserConfig,
    NexusPHPSiteConfig,
)


@dataclass(frozen=True, slots=True)
class ParserCatalogEntry:
    name: str
    base_url: str
    parser: NexusPHPParserConfig


class ParserCatalog:
    def __init__(self, entries: tuple[ParserCatalogEntry, ...]) -> None:
        self.entries = entries
        self._by_host = {_normalized_host(entry.base_url): entry for entry in entries}

    def match(self, base_url: str) -> ParserCatalogEntry | None:
        return self._by_host.get(_normalized_host(base_url))


def load_parser_catalog(path: Path) -> ParserCatalog:
    if not path.exists():
        return ParserCatalog(())

    payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    sites = payload.get("sites", [])
    if not isinstance(sites, list):
        raise ValueError(f"Expected 'sites' to be a list in {path}")

    entries: list[ParserCatalogEntry] = []
    for site in sites:
        if not isinstance(site, dict):
            raise ValueError(f"Invalid parser site entry in {path}: expected mapping")
        try:
            entries.append(
                ParserCatalogEntry(
                    name=str(site["name"]),
                    base_url=str(site["base_url"]),
                    parser=parser_config_from_mapping(site.get("parser")),
                )
            )
        except KeyError as exc:
            raise ValueError(
                f"Missing required parser site config key {exc.args[0]!r} in {path}"
            ) from exc
    return ParserCatalog(tuple(entries))


def build_nexusphp_indexers(
    sites: list[dict[str, Any]],
    catalog: ParserCatalog,
    proxy_url: str | None = None,
) -> tuple[NexusPHPCrawler, ...]:
    crawlers: list[NexusPHPCrawler] = []
    for site in sites:
        entry = catalog.match(str(site.get("base_url", "")))
        if entry is None:
            continue
        use_proxy = bool(site.get("use_proxy", False))
        crawlers.append(
            NexusPHPCrawler(
                _site_config(site, entry),
                proxy_url=proxy_url if use_proxy else None,
            )
        )
    return tuple(crawlers)


def _site_config(raw: Any, entry: ParserCatalogEntry) -> NexusPHPSiteConfig:
    if not isinstance(raw, dict):
        raise ValueError("Invalid site entry: expected mapping")
    try:
        return NexusPHPSiteConfig(
            name=str(raw["name"]),
            base_url=str(raw["base_url"]),
            cookie=str(raw["cookie"]) if raw.get("cookie") else None,
            site_id=str(raw["id"]) if raw.get("id") else None,
            parser=entry.parser,
            max_concurrency=int(raw.get("max_concurrency", 2)),
            user_agent=str(raw["user_agent"]) if raw.get("user_agent") else None,
        )
    except KeyError as exc:
        raise ValueError(f"Missing required site config key {exc.args[0]!r}") from exc


def parser_config_from_mapping(raw: Any) -> NexusPHPParserConfig:
    if raw is None:
        raise ValueError("Parser config is required")
    if not isinstance(raw, dict):
        raise ValueError("Invalid parser config: expected mapping")

    list_selector = str(raw.get("list_selector", "")).strip()
    if not list_selector:
        raise ValueError("Invalid parser config: list_selector is required")
    raw_fields = raw.get("fields", {})
    if not isinstance(raw_fields, dict):
        raise ValueError("Invalid parser.fields config: expected mapping")

    fields: dict[str, FieldRule] = {}
    for name, value in raw_fields.items():
        if not isinstance(value, dict):
            raise ValueError(f"Invalid parser field {name!r}: expected mapping")
        fields[str(name)] = FieldRule(
            selector=str(value.get("selector", "")),
            attribute=str(value.get("attribute", "text")),
            regex=str(value["regex"]) if value.get("regex") else None,
            index=int(value["index"]) if value.get("index") is not None else None,
            remove=tuple(str(item) for item in value.get("remove", ())),
            filters=tuple(str(item) for item in value.get("filters", ())),
        )
        if not fields[str(name)].selector:
            raise ValueError(f"Invalid parser field {name!r}: selector is required")

    return NexusPHPParserConfig(list_selector=list_selector, fields=fields)


def _normalized_host(base_url: str) -> str:
    parsed = urlparse(base_url if "://" in base_url else f"https://{base_url}")
    host = (parsed.hostname or base_url).lower().strip()
    return host.removeprefix("www.")
