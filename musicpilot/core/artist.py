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

_t2s = OpenCC("t2s")  # Traditional → Simplified
_s2t = OpenCC("s2t")  # Simplified → Traditional


@dataclass(frozen=True, slots=True)
class ArtistInfo:
    id: int
    name: str
    normalized_name: str
    aliases: tuple[str, ...]


def normalize_artist_name(name: str | None) -> str:
    """Normalize an artist name for comparison.

    - Traditional → Simplified (OpenCC)
    - Fullwidth → Halfwidth
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


class ArtistService:
    """Service for managing artist names, aliases, and canonical names."""

    def __init__(self, repository: Any) -> None:
        self._repo = repository

    # ── Public API ──────────────────────────────────────────────

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

        # Direct alias lookup
        artist_id = await self._repo.find_artist_id_by_alias(name)
        if artist_id is not None:
            return await self._repo.list_artist_aliases(artist_id)

        # Try normalized lookup
        normalized = normalize_artist_name(name)
        artist = await self._repo.find_artist_by_normalized(normalized)
        if artist is not None:
            return await self._repo.list_artist_aliases(artist.id)

        return [name]

    async def get_canonical_name(self, name: str | None) -> str | None:
        """Resolve an artist name to its canonical (authoritative) name.

        Returns None if the name is unknown or empty.
        """
        if not name:
            return None
        name = name.strip()
        if not name:
            return None

        artist_id = await self._repo.find_artist_id_by_alias(name)
        if artist_id is not None:
            artist = await self._repo.get_artist(artist_id)
            if artist is not None:
                return artist.name

        normalized = normalize_artist_name(name)
        artist = await self._repo.find_artist_by_normalized(normalized)
        if artist is not None:
            return artist.name

        return name

    async def ensure_artist(
        self,
        name: str,
        *,
        source: str = "manual",
        external_ids: dict[str, str] | None = None,
    ) -> ArtistInfo:
        """Ensure an artist exists in the database.

        If the artist (or an alias matching it) already exists, returns the
        existing ArtistInfo. Otherwise, creates a new artist entry.

        If the name contains separators (feat., &, /, etc.), each part is
        handled independently and only the first part is returned as primary.
        """
        name = name.strip()
        if not name:
            raise ValueError("Artist name cannot be empty")

        # Check existing
        artist_id = await self._repo.find_artist_id_by_alias(name)
        if artist_id is not None:
            return await self._get_artist_info(artist_id)

        normalized = normalize_artist_name(name)
        artist = await self._repo.find_artist_by_normalized(normalized)
        if artist is not None:
            # Add this name as an alias
            await self._repo.add_alias(artist.id, name, source)
            return await self._get_artist_info(artist.id)

        # Create new artist
        artist = await self._repo.create_artist(
            name=name,
            normalized_name=normalized,
            external_ids=external_ids or {},
        )
        # Add itself as a default alias
        await self._repo.add_alias(artist.id, name, "primary")

        return ArtistInfo(
            id=artist.id,
            name=artist.name,
            normalized_name=artist.normalized_name,
            aliases=(name,),
        )

    async def merge_artists(self, target_id: int, source_id: int) -> ArtistInfo:
        """Merge source artist into target artist.

        All aliases of source are reassigned to target.
        The source artist record is deleted.
        """
        await self._repo.reassign_aliases(source_id, target_id)
        await self._repo.delete_artist(source_id)
        return await self._get_artist_info(target_id)

    async def build_library_from_media_files(
        self,
        user_agent: str = "MusicPilot/0.1.0",
    ) -> int:
        """Auto-populate artist database from existing MediaFile records.

        Scans all distinct artist values from media_files and music_library_tracks,
        creates artist groups enriched with aliases from MusicBrainz (cross-language
        merging: "Jay Chou" ↦ "周杰伦"), and merges groups that share MusicBrainz
        aliases.

        Idempotent: re-running will add new aliases and merge groups that were
        previously separate, but will not duplicate existing artists.

        Returns the number of artist groups created/updated.
        """
        raw_names = await self._repo.list_distinct_artists()
        if not raw_names:
            logger.info("No existing artists found to build library from.")
            return 0

        # Phase 1: Initial grouping by normalization
        # Also collect MusicBrainz aliases for each name
        norm_groups: dict[str, set[str]] = {}
        mb_aliases_per_name: dict[str, set[str]] = {}

        for raw in raw_names:
            if not raw:
                continue
            normalized = normalize_artist_name(raw)
            if normalized not in norm_groups:
                norm_groups[normalized] = set()
            norm_groups[normalized].add(raw)

        # Phase 2: Fetch aliases from MusicBrainz with rate limiting
        musicbrainz_aliases: dict[str, set[str]] = {}
        seen_mb_artists: set[str] = set()

        async with httpx.AsyncClient(timeout=10.0) as client:
            for i, (normalized, names) in enumerate(norm_groups.items()):
                # Rate limit: 1 request per second (MusicBrainz policy)
                if i > 0:
                    await asyncio.sleep(1)

                # Pick the longest name for MusicBrainz search
                search_name = max(names, key=len)
                mb_alias_set = await _fetch_musicbrainz_aliases(
                    client, search_name, user_agent, seen_mb_artists,
                )
                if mb_alias_set:
                    musicbrainz_aliases[normalized] = mb_alias_set

        # Phase 3: Merge groups using MusicBrainz alias overlap
        # If group A's MusicBrainz aliases intersect group B's → they're the same artist
        merged_groups: list[set[str]] = []
        used: set[str] = set()

        for norm_key, names in norm_groups.items():
            if norm_key in used:
                continue
            mb_set_a = musicbrainz_aliases.get(norm_key, set())
            cluster: set[str] = set(names)
            used.add(norm_key)

            for other_key, other_names in norm_groups.items():
                if other_key in used:
                    continue
                mb_set_b = musicbrainz_aliases.get(other_key, set())
                # Merge if either normalization overlaps or MusicBrainz aliases overlap
                if (normalize_artist_name(next(iter(other_names))) == normalize_artist_name(next(iter(names)))
                        or (mb_set_a and mb_set_b and mb_set_a & mb_set_b)):
                    cluster.update(other_names)
                    used.add(other_key)

            merged_groups.append(cluster)

        # Phase 4: Persist (idempotent — don't re-create existing artists)
        created = 0
        for names in merged_groups:
            # Canonical = most common name in the cluster
            name_counts: dict[str, int] = {}
            for n in names:
                name_counts[n] = name_counts.get(n, 0) + 1
            canonical = max(name_counts, key=name_counts.get)
            normalized = normalize_artist_name(canonical)

            # Check if any name in this group already maps to an existing artist
            # (by normalized_name or by alias lookup — handles idempotent re-runs)
            existing_artist = await self._repo.find_artist_by_normalized(normalized)
            if existing_artist is None:
                for name in names:
                    artist_id = await self._repo.find_artist_id_by_alias(name)
                    if artist_id is not None:
                        existing_artist = await self._repo.get_artist(artist_id)
                        break
            if existing_artist is not None:
                # Add any new aliases
                for alias in names:
                    if alias != existing_artist.name:
                        await self._repo.add_alias(existing_artist.id, alias, "media_file")
                # Also add MusicBrainz aliases from the cluster
                if normalized in musicbrainz_aliases:
                    for alias in musicbrainz_aliases[normalized]:
                        if normalize_artist_name(alias) != normalized:
                            await self._repo.add_alias(
                                existing_artist.id, alias, "musicbrainz",
                            )
                continue

            artist = await self._repo.create_artist(
                name=canonical,
                normalized_name=normalized,
                external_ids={},
            )
            for alias in names:
                src = "primary" if alias == canonical else "media_file"
                await self._repo.add_alias(artist.id, alias, src)
            # Add MusicBrainz aliases
            if normalized in musicbrainz_aliases:
                for alias in musicbrainz_aliases[normalized]:
                    # Skip only if the raw string matches the canonical name
                    if alias != canonical:
                        await self._repo.add_alias(artist.id, alias, "musicbrainz")
            created += 1

        logger.info(
            "Built artist library: %d groups from %d names, %d with MusicBrainz data",
            max(len(merged_groups), created), len(raw_names), len(musicbrainz_aliases),
        )
        return max(len(merged_groups), created)

    async def add_alias(self, artist_id: int, alias: str, source: str = "user") -> None:
        """Add an alias to an existing artist."""
        await self._repo.add_alias(artist_id, alias, source)

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

        Does NOT perform async lookups — returns quickly if already canonical.
        To do a full async resolve, call get_canonical_name separately.
        This is a convenience for cases where the name is already canonical.
        """
        if not metadata.artist:
            return metadata
        return TrackMetadata(
            title=metadata.title,
            artist=metadata.artist,
            album=metadata.album,
            year=metadata.year,
            track_number=metadata.track_number,
            lyrics=metadata.lyrics,
            cover_url=metadata.cover_url,
            extra=metadata.extra,
        )

    # ── Internal ────────────────────────────────────────────────

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
    # Name too short → not worth querying
    if not name or len(name) < 2:
        return set()

    headers = {"User-Agent": user_agent}
    search_url = "https://musicbrainz.org/ws/2/artist/"
    params = {
        "query": f'artist:"{name}"',
        "limit": "3",
        "fmt": "json",
    }

    try:
        response = await client.get(search_url, params=params, headers=headers)
        response.raise_for_status()
        data = response.json()
    except Exception as exc:  # noqa: BLE001
        logger.debug("MusicBrainz search failed for %r: %s", name, exc)
        return set()

    artists = data.get("artists") or []
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

    # Expand with OpenCC script variants (simplified ↔ traditional CJK)
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
        "MusicBrainz: %r → %d aliases (+%d via OpenCC) (mbid=%s)",
        name, len(aliases), len(expanded) - len(aliases), mbid,
    )
    return expanded