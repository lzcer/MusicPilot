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


class ArtistService:
    """Service for managing artist names, aliases, and canonical names."""

    def __init__(self, repository: Any) -> None:
        self._repo = repository

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

        Scans all distinct artist values from media_files, music_library_tracks,
        and playlist_tracks, groups them by normalized name, then processes
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

        # Phase 1: Group raw names by normalization
        norm_groups: dict[str, set[str]] = {}

        for raw in raw_names:
            if not raw:
                continue
            parts = split_artist_credit(raw)
            if not parts:
                continue
            for part in parts:
                normalized = normalize_artist_name(part)
                if normalized not in norm_groups:
                    norm_groups[normalized] = set()
                norm_groups[normalized].add(part)

        # Phase 2: Process each group incrementally with immediate commit
        created = 0
        skipped = 0

        async with httpx.AsyncClient(timeout=httpx.Timeout(10.0, connect=5.0)) as client:
            seen_mb_artists: set[str] = set()
            group_count = len(norm_groups)

            for i, (normalized, names) in enumerate(norm_groups.items()):

                logger.info(
                    "Artist build [%d/%d]: processing %s",
                    i + 1, group_count, next(iter(names)),
                )

                # Check if this group already exists in the database
                existing_artist = await self._repo.find_artist_by_normalized(normalized)
                if existing_artist is None:
                    for name in names:
                        artist_id = await self._repo.find_artist_id_by_alias(name)
                        if artist_id is not None:
                            existing_artist = await self._repo.get_artist(artist_id)
                            break

                if existing_artist is not None:
                    # Already exists -- add any new aliases, then skip MB lookup
                    for alias in names:
                        if alias != existing_artist.name:
                            await self._repo.add_alias(existing_artist.id, alias, "media_file")
                    skipped += 1
                    continue

                # New artist -- rate-limit before MusicBrainz API calls
                if i > 0:
                    await asyncio.sleep(1)
                search_name = max(names, key=len)
                mb_aliases = await _fetch_musicbrainz_aliases(
                    client, search_name, user_agent, seen_mb_artists,
                )

                # Pick canonical name (longest is usually most descriptive)
                canonical = max(names, key=len)
                artist = await self._repo.create_artist(
                    name=canonical,
                    normalized_name=normalized,
                    external_ids={},
                )
                for alias in names:
                    src = "primary" if alias == canonical else "media_file"
                    await self._repo.add_alias(artist.id, alias, src)
                for mb_alias in mb_aliases:
                    if mb_alias != canonical:
                        await self._repo.add_alias(artist.id, mb_alias, "musicbrainz")
                created += 1

        logger.info(
            "Artist build done: %d created, %d skipped (from %d names, %d groups)",
            created, skipped, len(raw_names), group_count,
        )
        return created

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
            year=metadata.year,
            track_number=metadata.track_number,
            lyrics=metadata.lyrics,
            cover_url=metadata.cover_url,
            extra=metadata.extra,
        )

    # -- Internal --

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
    # Name too short -- not worth querying
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