"""Artist library service.

Handles artist alias resolution, canonical name lookup, and automatic
population of the artist database from existing media files and external
sources such as MusicBrainz.
"""

from __future__ import annotations

import asyncio
import logging
import re
from dataclasses import dataclass
from typing import Any

import httpx
from opencc import OpenCC

from musicpilot.ports.metadata import TrackMetadata

logger = logging.getLogger(__name__)

_t2s = OpenCC("t2s")  # Traditional -> Simplified
_s2t = OpenCC("s2t")  # Simplified -> Traditional
_CJK_RE = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff]")
_LATIN_RE = re.compile(r"[A-Za-z]")
_BRACKETED_ARTIST_RE = re.compile(
    r"^\s*(?P<outer>.+?)\s*[（(]\s*(?P<inner>[^()（）]+)\s*[）)]\s*$"
)


@dataclass(frozen=True, slots=True)
class ArtistInfo:
    id: int
    name: str
    normalized_name: str
    aliases: tuple[str, ...]


def normalize_artist_name(name: str | None) -> str:
    """Normalize an artist name for comparison.

    - Traditional -> Simplified (OpenCC)
    - Fullwidth -> Halfwidth
    - Lowercase
    - Strip whitespace/punctuation
    """
    if not name:
        return ""
    text = name.strip()
    text = _t2s.convert(text)

    # Fullwidth to halfwidth
    result: list[str] = []
    for ch in text:
        code = ord(ch)
        if 0xFF01 <= code <= 0xFF5E:
            result.append(chr(code - 0xFEE0))
        elif code == 0x3000:
            result.append(" ")
        else:
            result.append(ch)
    text = "".join(result).casefold()

    # Collapse whitespace and strip non-alphanumeric (keep CJK)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def normalize_compare(a: str | None, b: str | None) -> bool:
    """Check if two artist names are equivalent after normalization."""
    return bool(normalize_artist_name(a) == normalize_artist_name(b))


def split_artist_credit(value: str | None) -> list[str]:
    if not value:
        return []
    pattern = re.compile(
        r"\s*(?:/|、|,|，|&|＆|\+|•|\bfeat\.?|\bft\.?|\bfeaturing\b|\bwith\b)\s*",
        re.IGNORECASE,
    )
    names: list[str] = []
    seen: set[str] = set()
    for item in pattern.split(value):
        name = item.strip()
        if not name:
            continue
        normalized = normalize_artist_name(name)
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        names.append(name)
    return names


def _unique_artist_names(values: tuple[str, ...]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        name = value.strip()
        normalized = normalize_artist_name(name)
        if not name or not normalized or normalized in seen:
            continue
        seen.add(normalized)
        result.append(name)
    return result


def _unique_exact_artist_names(values: tuple[str, ...]) -> tuple[str, ...]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        name = value.strip()
        if not name or name in seen:
            continue
        seen.add(name)
        result.append(name)
    return tuple(result)


def artist_identity_candidates(name: str | None) -> tuple[str, ...]:
    if not name or not name.strip():
        return ()
    original = name.strip()
    values: list[str] = []

    def add_script_variants(value: str) -> None:
        values.extend((value, _t2s.convert(value), _s2t.convert(value)))

    add_script_variants(original)
    match = _BRACKETED_ARTIST_RE.match(original)
    if match is not None:
        outer = match.group("outer").strip()
        inner = match.group("inner").strip()
        if bool(_CJK_RE.search(outer)) != bool(_CJK_RE.search(inner)):
            add_script_variants(outer)
            add_script_variants(inner)
    return _unique_exact_artist_names(tuple(values))


def _preferred_canonical_name(
    candidates: tuple[str, ...],
    *,
    fallback: str,
) -> str:
    chinese_names: list[str] = []
    for candidate in candidates:
        if not _CJK_RE.search(candidate) or re.search(r"[()（）]", candidate):
            continue
        simplified = _t2s.convert(candidate).strip()
        if simplified and simplified not in chinese_names:
            chinese_names.append(simplified)
    if chinese_names:
        return next(
            (name for name in chinese_names if not _LATIN_RE.search(name)),
            chinese_names[0],
        )
    return fallback.strip()


def _identity_candidates_for_names(names: tuple[str, ...]) -> tuple[str, ...]:
    values: list[str] = []
    for name in names:
        values.extend(artist_identity_candidates(name))
    return _unique_exact_artist_names(tuple(values))


def _group_artist_identity_names(raw_names: list[str]) -> list[tuple[str, ...]]:
    parts = _unique_exact_artist_names(
        tuple(
            part
            for raw_name in raw_names
            for part in split_artist_credit(raw_name)
        )
    )
    parents = list(range(len(parts)))

    def root(index: int) -> int:
        while parents[index] != index:
            parents[index] = parents[parents[index]]
            index = parents[index]
        return index

    def union(left: int, right: int) -> None:
        left_root = root(left)
        right_root = root(right)
        if left_root != right_root:
            parents[right_root] = left_root

    identity_owner: dict[str, int] = {}
    for index, part in enumerate(parts):
        identity_keys = {
            normalized
            for candidate in artist_identity_candidates(part)
            if (normalized := normalize_artist_name(candidate))
        }
        for identity_key in identity_keys:
            owner = identity_owner.get(identity_key)
            if owner is None:
                identity_owner[identity_key] = index
            else:
                union(index, owner)

    groups: dict[int, list[str]] = {}
    for index, part in enumerate(parts):
        groups.setdefault(root(index), []).append(part)
    return [
        tuple(sorted(names, key=lambda item: (len(item), item)))
        for names in groups.values()
    ]


class ArtistService:
    """Service for managing artist names, aliases, and canonical names."""

    def __init__(
        self,
        repository: Any,
        musicbrainz_user_agent: str = "MusicPilot/0.1.0",
    ) -> None:
        self._repo = repository
        self._musicbrainz_user_agent = musicbrainz_user_agent
        self._local_artist_creation_lock = asyncio.Lock()
        self._alias_write_lock = asyncio.Lock()
        self._musicbrainz_enriched_artist_ids: set[int] = set()
        self._musicbrainz_enrichment_lock = asyncio.Lock()
        self._last_musicbrainz_enrichment_at = 0.0

    # -- Public API --

    async def get_aliases(self, name: str | None) -> list[str]:
        """Get all known names (canonical + aliases) for an artist.

        If the name is found in the local DB, returns all aliases including
        the canonical name. If not found, returns only the name itself.
        """
        if not name:
            return []
        name = name.strip()
        if not name:
            return []
        candidates = artist_identity_candidates(name)
        artists = await self._find_identity_artists(candidates)
        if artists:
            artist = self._select_identity_artist(
                artists,
                candidates=candidates,
                fallback=name,
            )
            aliases = await self._repo.list_artist_aliases(artist.id)
            return _unique_artist_names(tuple(aliases))
        return _unique_artist_names(candidates or (name,))

    async def get_canonical_name(self, name: str | None) -> str | None:
        """Resolve an artist name to its canonical (authoritative) name.

        Returns the original name when it is unknown, or None when empty.
        """
        if not name:
            return None
        name = name.strip()
        if not name:
            return None

        candidates = artist_identity_candidates(name)
        artists = await self._find_identity_artists(candidates)
        if artists:
            return self._select_identity_artist(
                artists,
                candidates=candidates,
                fallback=name,
            ).name
        return name

    async def has_artist_name(self, name: str | None) -> bool:
        if not name:
            return False
        name = name.strip()
        if not name:
            return False
        candidates = artist_identity_candidates(name)
        return bool(await self._find_identity_artists(candidates))

    async def get_or_create_canonical_name(
        self,
        name: str,
        *,
        source: str = "scraping",
    ) -> str:
        names = split_artist_credit(name)
        if not names:
            raise ValueError("Artist name cannot be empty")
        artist, _created = await self._ensure_artist_local(
            names[0],
            source=source,
        )
        return artist.name

    async def ensure_artist(
        self,
        name: str,
        *,
        source: str = "manual",
        external_ids: dict[str, str] | None = None,
    ) -> ArtistInfo:
        """Ensure an artist exists in the database.

        Resolves structured identity candidates against the local library,
        creates a local record when needed, then enriches safe aliases from
        MusicBrainz without holding the local creation lock.

        If the name contains separators (feat., &, /, etc.), each part is
        handled independently and only the first part is returned as primary.
        """
        name = name.strip()
        if not name:
            raise ValueError("Artist name cannot be empty")
        names = split_artist_credit(name)
        if len(names) > 1:
            primary: ArtistInfo | None = None
            for item in names:
                info = await self.ensure_artist(
                    item,
                    source=source,
                    external_ids=external_ids if item == names[0] else None,
                )
                if primary is None:
                    primary = info
            if primary is None:
                raise ValueError("Artist name cannot be empty")
            return primary

        artist, _created = await self._ensure_artist_local(
            name,
            source=source,
            external_ids=external_ids,
        )
        return await self._enrich_artist_from_musicbrainz(
            artist,
            lookup_name=name,
        )

    async def merge_artists(self, target_id: int, source_id: int) -> ArtistInfo:
        """Merge source artist into target artist.

        All aliases of source are reassigned to target.
        The source artist record is deleted.
        """
        await self._repo.reassign_aliases(source_id, target_id)
        await self._repo.delete_artist(source_id)
        return await self._get_artist_info(target_id)

    async def update_artist(
        self,
        artist_id: int,
        *,
        name: str,
        aliases: tuple[str, ...],
    ) -> ArtistInfo:
        canonical_name = name.strip()
        if not canonical_name:
            raise ValueError("Artist name cannot be empty")
        normalized = normalize_artist_name(canonical_name)
        async with self._local_artist_creation_lock:
            artist = await self._repo.get_artist(artist_id)
            if artist is None:
                raise ValueError("Artist not found")
            canonical_matches = await self._find_identity_artists(
                artist_identity_candidates(canonical_name)
            )
            if any(item.id != artist_id for item in canonical_matches):
                raise ValueError(f"Artist name already exists: {canonical_name}")

            clean_aliases: list[str] = []
            for alias in _unique_exact_artist_names(aliases):
                if normalize_artist_name(alias) == normalized:
                    continue
                alias_matches = await self._find_identity_artists(
                    artist_identity_candidates(alias)
                )
                if any(item.id != artist_id for item in alias_matches):
                    raise ValueError(
                        f"Artist alias already belongs to another artist: {alias}"
                    )
                clean_aliases.append(alias)

            updated = await self._repo.update_artist_profile(
                artist_id,
                name=canonical_name,
                normalized_name=normalized,
                aliases=(
                    (canonical_name, "primary"),
                    *((alias, "user") for alias in clean_aliases),
                ),
            )
        if updated is None:
            raise ValueError("Artist not found")
        return await self._get_artist_info(artist_id)

    async def build_library_from_media_files(
        self,
        user_agent: str | None = None,
    ) -> int:
        """Auto-populate artist database from existing MediaFile records.

        Scans all distinct artist values from media_files, music_library_tracks,
        and playlist_tracks, groups them by identity candidates, then processes
        each group incrementally:

        1. If the artist already exists in the DB -- add any new aliases, skip.
        2. If it's new -- fetch aliases from MusicBrainz, create artist, commit.

        Each group is committed immediately so partial progress survives crashes.
        Idempotent: re-running skips already-created artists.

        Returns the number of artist groups created.
        """
        raw_names = await self._repo.list_distinct_artists()
        if not raw_names:
            logger.info("No existing artists found to build library from.")
            return 0

        identity_groups = _group_artist_identity_names(raw_names)

        created = 0
        skipped = 0
        async with httpx.AsyncClient(timeout=httpx.Timeout(10.0, connect=5.0)) as client:
            seen_mb_artists: set[str] = set()
            group_count = len(identity_groups)
            for i, ordered_names in enumerate(identity_groups):
                candidates = _identity_candidates_for_names(ordered_names)
                canonical = _preferred_canonical_name(
                    candidates,
                    fallback=ordered_names[0],
                )
                logger.info(
                    "Artist build [%d/%d]: processing %s",
                    i + 1,
                    group_count,
                    canonical,
                )
                artist, was_created = await self._ensure_artist_local(
                    canonical,
                    source="media_file",
                    identity_names=ordered_names,
                )
                if was_created:
                    created += 1
                else:
                    skipped += 1
                if i > 0:
                    await asyncio.sleep(1)
                mb_aliases = await _fetch_musicbrainz_aliases(
                    client,
                    canonical,
                    user_agent or self._musicbrainz_user_agent,
                    seen_mb_artists,
                )
                await self._add_aliases_safely(
                    artist.id,
                    tuple((alias, "musicbrainz") for alias in mb_aliases),
                )

        logger.info(
            "Artist build done: %d created, %d skipped (from %d names, %d groups)",
            created, skipped, len(raw_names), group_count,
        )
        return created

    async def add_alias(self, artist_id: int, alias: str, source: str = "user") -> None:
        """Add an alias to an existing artist."""
        alias_name = alias.strip()
        if not alias_name:
            raise ValueError("Artist alias cannot be empty")
        async with self._local_artist_creation_lock:
            artist = await self._repo.get_artist(artist_id)
            if artist is None:
                raise ValueError("Artist not found")
            matches = await self._find_identity_artists(
                artist_identity_candidates(alias_name)
            )
            if any(item.id != artist_id for item in matches):
                raise ValueError(
                    f"Artist alias already belongs to another artist: {alias_name}"
                )
            await self._repo.add_alias(artist_id, alias_name, source)

    async def list_artists(self) -> list[ArtistInfo]:
        """List all artists with their aliases."""
        artists = await self._repo.list_all_artists()
        result = []
        for artist in artists:
            aliases = await self._repo.list_artist_aliases(artist.id)
            result.append(
                ArtistInfo(
                    id=artist.id,
                    name=artist.name,
                    normalized_name=artist.normalized_name,
                    aliases=tuple(a for a in aliases if a != artist.name),
                )
            )
        return result

    def resolve_metadata_artist(self, metadata: TrackMetadata) -> TrackMetadata:
        """Resolve the artist in a TrackMetadata to its canonical name.

        Does NOT perform async lookups -- returns quickly if already canonical.
        To do a full async resolve, call get_canonical_name separately.
        This is a convenience for cases where the name is already canonical.
        """
        if not metadata.artist:
            return metadata
        return TrackMetadata(
            title=metadata.title,
            artist=metadata.artist,
            album=metadata.album,
            album_artist=metadata.album_artist,
            year=metadata.year,
            track_number=metadata.track_number,
            lyrics=metadata.lyrics,
            cover_url=metadata.cover_url,
            has_cover=metadata.has_cover,
            extra=metadata.extra,
        )

    # -- Internal --

    async def _find_identity_artists(self, candidates: tuple[str, ...]) -> list[Any]:
        aliases = _unique_exact_artist_names(candidates)
        normalized_names = tuple(
            dict.fromkeys(
                normalized
                for candidate in aliases
                if (normalized := normalize_artist_name(candidate))
            )
        )
        return await self._repo.list_artists_by_identity_candidates(
            aliases=aliases,
            normalized_names=normalized_names,
        )

    def _select_identity_artist(
        self,
        artists: list[Any],
        *,
        candidates: tuple[str, ...],
        fallback: str,
    ) -> Any:
        preferred = _preferred_canonical_name(candidates, fallback=fallback)
        exact_matches = [artist for artist in artists if artist.name == preferred]
        selected = min(exact_matches or artists, key=lambda artist: artist.id)
        if len(artists) > 1:
            logger.warning(
                "Artist identity conflict: candidates=%s, matches=%s, selected_id=%s, "
                "selected_name=%r",
                candidates,
                [(artist.id, artist.name) for artist in artists],
                selected.id,
                selected.name,
            )
        return selected

    async def _ensure_artist_local(
        self,
        name: str,
        *,
        source: str,
        external_ids: dict[str, str] | None = None,
        identity_names: tuple[str, ...] | None = None,
    ) -> tuple[ArtistInfo, bool]:
        clean_name = name.strip()
        if not clean_name:
            raise ValueError("Artist name cannot be empty")
        lookup_names = _unique_exact_artist_names(
            (clean_name, *(identity_names or ()))
        )
        candidates = _identity_candidates_for_names(lookup_names)
        if not candidates:
            raise ValueError("Artist name cannot be empty")
        canonical = _preferred_canonical_name(candidates, fallback=clean_name)

        async with self._local_artist_creation_lock:
            matches = await self._find_identity_artists(candidates)
            if matches:
                artist = self._select_identity_artist(
                    matches,
                    candidates=candidates,
                    fallback=clean_name,
                )
                created = False
            else:
                artist = await self._repo.create_artist(
                    name=canonical,
                    normalized_name=normalize_artist_name(canonical),
                    external_ids=external_ids or {},
                )
                created = True
            alias_names = _unique_exact_artist_names((artist.name, *candidates))
            await self._add_aliases_safely(
                artist.id,
                tuple(
                    (
                        alias,
                        "primary" if alias == artist.name else source,
                    )
                    for alias in alias_names
                ),
            )
            return await self._get_artist_info(artist.id), created

    async def _add_aliases_safely(
        self,
        artist_id: int,
        aliases: tuple[tuple[str, str], ...],
    ) -> None:
        async with self._alias_write_lock:
            await self._add_aliases_safely_locked(artist_id, aliases)

    async def _add_aliases_safely_locked(
        self,
        artist_id: int,
        aliases: tuple[tuple[str, str], ...],
    ) -> None:
        alias_sources: dict[str, str] = {}
        for alias, source in aliases:
            alias_name = alias.strip()
            if alias_name and alias_name not in alias_sources:
                alias_sources[alias_name] = source
        if not alias_sources:
            return

        current_aliases = set(await self._repo.list_artist_aliases(artist_id))
        candidate_map = {
            alias: artist_identity_candidates(alias)
            for alias in alias_sources
        }
        lookup_aliases = _unique_exact_artist_names(
            tuple(
                candidate
                for candidates in candidate_map.values()
                for candidate in candidates
            )
        )
        owners = await self._repo.list_artist_alias_owners(lookup_aliases)
        matching_artists = await self._find_identity_artists(lookup_aliases)
        safe_aliases: list[tuple[str, str]] = []
        for alias, source in alias_sources.items():
            if alias in current_aliases:
                continue
            candidates = candidate_map[alias]
            normalized_candidates = {
                normalized
                for candidate in candidates
                if (normalized := normalize_artist_name(candidate))
            }
            owner_ids = {
                owner_id
                for candidate in candidates
                for owner_id in owners.get(candidate, ())
            }
            owner_ids.update(
                artist.id
                for artist in matching_artists
                if artist.normalized_name in normalized_candidates
            )
            conflicting_ids = sorted(owner_ids - {artist_id})
            if conflicting_ids:
                logger.warning(
                    "Artist alias conflict skipped: artist_id=%s, alias=%r, source=%s, "
                    "owner_ids=%s",
                    artist_id,
                    alias,
                    source,
                    conflicting_ids,
                )
                continue
            safe_aliases.append((alias, source))
            current_aliases.add(alias)
        await self._repo.add_aliases(artist_id, tuple(safe_aliases))

    async def _get_artist_info(self, artist_id: int) -> ArtistInfo:
        artist = await self._repo.get_artist(artist_id)
        if artist is None:
            msg = f"Artist {artist_id} not found after creation"
            raise RuntimeError(msg)
        aliases = await self._repo.list_artist_aliases(artist_id)
        return ArtistInfo(
            id=artist.id,
            name=artist.name,
            normalized_name=artist.normalized_name,
            aliases=tuple(a for a in aliases if a != artist.name),
        )

    async def _enrich_artist_from_musicbrainz(
        self,
        artist: ArtistInfo,
        *,
        lookup_name: str,
    ) -> ArtistInfo:
        if artist.id in self._musicbrainz_enriched_artist_ids:
            return artist
        async with self._musicbrainz_enrichment_lock:
            if artist.id in self._musicbrainz_enriched_artist_ids:
                return await self._get_artist_info(artist.id)
            loop = asyncio.get_running_loop()
            delay = 1.0 - (loop.time() - self._last_musicbrainz_enrichment_at)
            if delay > 0:
                await asyncio.sleep(delay)
            try:
                async with httpx.AsyncClient(
                    timeout=httpx.Timeout(10.0, connect=5.0)
                ) as client:
                    aliases = await asyncio.wait_for(
                        _fetch_musicbrainz_aliases(
                            client,
                            lookup_name,
                            self._musicbrainz_user_agent,
                            set(),
                        ),
                        timeout=15,
                    )
            except TimeoutError:
                logger.debug("MusicBrainz enrichment timed out for %r", lookup_name)
                aliases = set()
            self._last_musicbrainz_enrichment_at = loop.time()
            await self._add_aliases_safely(
                artist.id,
                tuple(
                    (alias, "musicbrainz")
                    for alias in sorted(aliases)
                    if alias != artist.name
                ),
            )
            self._musicbrainz_enriched_artist_ids.add(artist.id)
            return await self._get_artist_info(artist.id)


async def _fetch_musicbrainz_aliases(
    client: httpx.AsyncClient,
    name: str,
    user_agent: str,
    seen_artists: set[str],
) -> set[str]:
    """Fetch aliases for an artist from MusicBrainz.

    Searches MusicBrainz by name, picks the best matching artist, and returns
    all aliases (including different languages, scripts, and search variants).

    Returns an empty set if the lookup fails or no match is found.
    """
    # Name too short -- not worth querying
    if not name or len(name) < 2:
        return set()

    headers = {"User-Agent": user_agent}
    search_url = "https://musicbrainz.org/ws/2/artist/"
    queries = (
        f'artist:"{name}"',
        f'alias:"{name}"',
        name,
    )
    artists: list[dict[str, Any]] = []

    for query in queries:
        params = {
            "query": query,
            "limit": "5",
            "fmt": "json",
        }
        try:
            response = await client.get(search_url, params=params, headers=headers)
            response.raise_for_status()
            data = response.json()
        except Exception as exc:  # noqa: BLE001
            logger.debug("MusicBrainz search failed for %r using %r: %s", name, query, exc)
            continue

        artists = data.get("artists") or []
        if artists:
            break

    if not artists:
        logger.debug("MusicBrainz: no artist found for %r", name)
        return set()

    # Pick the best match: prefer score + type=Person
    best = max(
        artists,
        key=lambda a: (
            a.get("score", 0),
            1 if a.get("type") in ("Person", "person") else 0,
        ),
    )
    mbid = best.get("id")
    if not mbid:
        return set()

    # Avoid re-fetching the same MB artist for different local names
    if mbid in seen_artists:
        return set()
    seen_artists.add(mbid)

    # Fetch full detail with aliases
    detail_params = {"inc": "aliases", "fmt": "json"}
    try:
        detail_resp = await client.get(
            f"https://musicbrainz.org/ws/2/artist/{mbid}",
            params=detail_params,
            headers=headers,
        )
        detail_resp.raise_for_status()
        detail = detail_resp.json()
    except Exception as exc:  # noqa: BLE001
        logger.debug("MusicBrainz detail fetch failed for %s (%s): %s", name, mbid, exc)
        return set()

    aliases: set[str] = set()
    raw_aliases = detail.get("aliases") or []
    for alias in raw_aliases:
        al_name = (alias.get("name") or "").strip()
        if al_name and len(al_name) >= 1:
            aliases.add(al_name)

    # Also add the primary name and any sort-name variants
    primary = (detail.get("name") or "").strip()
    if primary:
        aliases.add(primary)
    sort_name = (detail.get("sort-name") or "").strip()
    if sort_name and sort_name != primary:
        aliases.add(sort_name)

    # Expand with OpenCC script variants (simplified <-> traditional CJK)
    # MusicBrainz may not return both scripts for all artists
    expanded: set[str] = set(aliases)
    for alias in aliases:
        simplified = _t2s.convert(alias)
        if simplified and simplified != alias:
            expanded.add(simplified)
        traditional = _s2t.convert(alias)
        if traditional and traditional != alias:
            expanded.add(traditional)

    logger.debug(
        "MusicBrainz: %r -> %d aliases (+%d via OpenCC) (mbid=%s)",
        name, len(aliases), len(expanded) - len(aliases), mbid,
    )
    return expanded
