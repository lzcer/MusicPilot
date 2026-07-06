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
    ResultFilterRule,
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
    return ParserCatalog(_load_parser_catalog_entries(path))


def load_merged_parser_catalog(system_path: Path, user_path: Path) -> ParserCatalog:
    merged: dict[str, ParserCatalogEntry] = {}
    paths = (system_path,) if system_path == user_path else (system_path, user_path)

    for path in paths:
        for entry in _load_parser_catalog_entries(path):
            merged[_normalized_host(entry.base_url)] = entry

    return ParserCatalog(tuple(merged.values()))


def _load_parser_catalog_entries(path: Path) -> tuple[ParserCatalogEntry, ...]:
    if not path.exists():
        return ()

    payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    sites = payload.get("sites", [])
    if not isinstance(sites, list):
        raise ValueError(f"Expected 'sites' to be a list in {path}")

    entries: list[ParserCatalogEntry] = []
    for site in sites:
        if not isinstance(site, dict):
            raise ValueError(f"Invalid parser site entry in {path}: expected mapping")
        parser = parser_config_from_mapping(site.get("parser"))
        try:
            for target in _parser_site_targets(site, path):
                entries.append(
                    ParserCatalogEntry(
                        name=str(target["name"]),
                        base_url=str(target["base_url"]),
                        parser=parser,
                    )
                )
        except KeyError as exc:
            raise ValueError(
                f"Missing required parser site config key {exc.args[0]!r} in {path}"
            ) from exc
    return tuple(entries)


def _parser_site_targets(site: dict[str, Any], path: Path) -> tuple[dict[str, Any], ...]:
    if "targets" not in site:
        return ({"name": site["name"], "base_url": site["base_url"]},)

    targets = site["targets"]
    if not isinstance(targets, list):
        raise ValueError(f"Invalid parser site targets in {path}: expected list")

    parsed_targets: list[dict[str, Any]] = []
    for target in targets:
        if not isinstance(target, dict):
            raise ValueError(f"Invalid parser site target in {path}: expected mapping")
        parsed_targets.append({"name": target["name"], "base_url": target["base_url"]})
    return tuple(parsed_targets)


def build_nexusphp_indexers(
    sites: list[dict[str, Any]],
    catalog: ParserCatalog,
    proxy_url: str | None = None,
) -> tuple[NexusPHPCrawler, ...]:
    crawlers: list[NexusPHPCrawler] = []
    for site in sites:
        if not bool(site.get("enabled", True)):
            continue
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
    raw_filter = raw.get("filter", {})
    if not isinstance(raw_filter, dict):
        raise ValueError("Invalid parser.filter config: expected mapping")
    search_query_param = str(raw.get("search_query_param", "search")).strip()
    if not search_query_param:
        raise ValueError("Invalid parser.search_query_param config: value is required")
    raw_search_params = raw.get("search_params", {})
    if not isinstance(raw_search_params, dict):
        raise ValueError("Invalid parser.search_params config: expected mapping")

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

    result_filter = {
        str(name): _result_filter_rule_from_mapping(name, value)
        for name, value in raw_filter.items()
    }
    missing_filter_fields = [name for name in result_filter if name not in fields]
    if missing_filter_fields:
        raise ValueError(
            "Invalid parser.filter config: missing field(s) "
            + ", ".join(missing_filter_fields)
        )

    return NexusPHPParserConfig(
        list_selector=list_selector,
        fields=fields,
        result_filter=result_filter,
        search_query_param=search_query_param,
        search_params={
            str(name): str(value)
            for name, value in raw_search_params.items()
            if value is not None
        },
    )


def _result_filter_rule_from_mapping(name: object, raw: Any) -> ResultFilterRule:
    if isinstance(raw, list):
        include = _string_tuple(raw)
        if not include:
            raise ValueError(f"Invalid parser.filter field {name!r}: include is required")
        return ResultFilterRule(include=include)
    if not isinstance(raw, dict):
        raise ValueError(f"Invalid parser.filter field {name!r}: expected list or mapping")

    include = _string_tuple(raw.get("include", ()))
    exclude = _string_tuple(raw.get("exclude", ()))
    if not include and not exclude:
        raise ValueError(f"Invalid parser.filter field {name!r}: include or exclude is required")
    return ResultFilterRule(include=include, exclude=exclude)


def _string_tuple(raw: Any) -> tuple[str, ...]:
    if raw is None:
        return ()
    if isinstance(raw, str):
        values = (raw,)
    elif isinstance(raw, list | tuple):
        values = tuple(str(item) for item in raw)
    else:
        raise ValueError("Invalid parser.filter value: expected string or list")
    return tuple(value.strip() for value in values if value.strip())


def _normalized_host(base_url: str) -> str:
    parsed = urlparse(base_url if "://" in base_url else f"https://{base_url}")
    host = (parsed.hostname or base_url).lower().strip()
    return host.removeprefix("www.")
