from __future__ import annotations

import asyncio
import logging
import os
import re
import shutil
import unicodedata
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from opencc import OpenCC

from musicpilot.core.artist import ArtistService, split_artist_credit
from musicpilot.core.metadata import MetadataCascade
from musicpilot.ports.metadata import TrackMetadata
from musicpilot.ports.tag_writer import TagWriter

logger = logging.getLogger("musicpilot.metadata.scraping")

_t2s = OpenCC("t2s")  # Traditional → Simplified

ScrapingMode = Literal["source", "mapped", "copy"]
RequiredMetadata = Literal["album", "artist", "lyrics"]
ClassifyBy = Literal["artist", "album"]
DuplicateHandling = Literal["ignore", "overwrite", "keep_largest"]

_AUDIO_EXTENSIONS = {
    ".aac",
    ".aiff",
    ".alac",
    ".ape",
    ".flac",
    ".m4a",
    ".mp3",
    ".ogg",
    ".opus",
    ".wav",
    ".wma",
}

# Patterns for stripping noise from directory/filename metadata
# These are quality tags, format info, source info, etc.
_DIR_NOISE_RE = re.compile(
    r"(?:"
    r"\[[^\]]*?(?:FLAC|MP3|WAV|ALAC|APE|AAC|DSD|SACD|Hi.?Res|"
    r"24.?[Bb]it|96[kK][Hh]z|192[kK][Hh]z|"
    r"320|320[kK]bps|无损|CD|BD|WEB|H.?DT?S|LP|Vinyl|"
    r"Limited.?Edition|Deluxe|豪华版|台版|日版|欧版|引进版"
    r")[^\]]*\]|"  # [24bit 96kHz FLAC]
    r"\([^)]*?(?:FLAC|MP3|WAV|ALAC|APE|AAC|DSD|SACD|Hi.?Res|"
    r"24.?[Bb]it|96[kK][Hh]z|192[kK][Hh]z|"
    r"320|无损|CD|BD|WEB|H.?DT?S|LP|Vinyl"
    r")[^)]*\)"  # (24bit 96kHz FLAC)
    r")",
    re.I,
)
_ARTIST_SEP_RE = re.compile(r"\s+[–—\-|/]\s+")
_DISC_DIR_RE = re.compile(r"^(?:CD|Disc|Disk|ディスク|Volume|Vol)\s*\d+", re.I)
_CJK_RE = re.compile(r"[\u4e00-\u9fff]")
_SEARCH_TITLE_TRANSLATION = str.maketrans(
    {
        "妳": "你",
        "祢": "你",
        "裏": "里",
        "裡": "里",
        "麽": "么",
    }
)
# Trailing noise to strip from album/artist names: year, format tags
_ALBUM_TRAILING_NOISE_RE = re.compile(
    r"\s+(?:20\d{2}\s*)?(?:FLAC|MP3|WAV|ALAC|APE|AAC|DSD|SACD|"
    r"Hi.?Res|24.?[Bb]it|96[kK][Hh]z|无损|WEB|LP|Vinyl|EP|Single|单曲|专辑)\s*$",
    re.I,
)


@dataclass(frozen=True, slots=True)
class ScrapingConfig:
    enabled: bool = False
    mode: ScrapingMode = "mapped"
    source_directory: Path | None = None
    mapped_directory: Path | None = None
    scrape_when_missing: tuple[RequiredMetadata, ...] = ()
    required_metadata: tuple[RequiredMetadata, ...] = ()
    auto_rename: bool = False
    auto_classify: bool = False
    classify_by: ClassifyBy = "artist"
    duplicate_handling: DuplicateHandling = "ignore"


@dataclass(frozen=True, slots=True)
class LibraryTrackSnapshot:
    title: str
    artist: str | None = None
    album: str | None = None
    size: int | None = None
    path: str | None = None


@dataclass(frozen=True, slots=True)
class ScrapingFileResult:
    source_path: Path
    library_path: Path | None
    metadata: TrackMetadata
    status: Literal["success", "failed", "skipped"]
    operation_type: ScrapingMode
    error_message: str | None = None
    stage: str = "completed"
    needs_metadata_update: bool = False
    candidate_count: int = 0


@dataclass(frozen=True, slots=True)
class ScrapingSummary:
    source_files: int = 0
    mapped_files: int = 0
    updated_files: int = 0
    moved_files: int = 0
    failed_files: int = 0
    results: tuple[ScrapingFileResult, ...] = ()


@dataclass(frozen=True, slots=True)
class _PathOperationResult:
    path: Path
    operation_type: ScrapingMode
    overwritten_existing: bool = False


@dataclass(frozen=True, slots=True)
class _MatchScore:
    title: int = 0
    artist: int = 0
    album: int = 0

    @property
    def total(self) -> int:
        return self.title + self.artist + self.album


class LocalMusicScraper:
    def __init__(
        self,
        *,
        metadata: MetadataCascade,
        tag_writer: TagWriter | None,
        artist_service: ArtistService | None = None,
    ) -> None:
        self.metadata = metadata
        self.tag_writer = tag_writer
        self.artist_service = artist_service

    async def process_download(
        self,
        *,
        task_name: str,
        save_path: str | None,
        config: ScrapingConfig,
        source_files: tuple[Path, ...] | None = None,
        library_tracks: tuple[LibraryTrackSnapshot, ...] = (),
        media_history: tuple[LibraryTrackSnapshot, ...] = (),
        cached_metadata: dict[Path, tuple[TrackMetadata, ...]] | None = None,
        forced_metadata: dict[Path, TrackMetadata] | None = None,
        on_file_result: Callable[[ScrapingFileResult], Awaitable[None]] | None = None,
    ) -> ScrapingSummary:
        if not config.enabled:
            return ScrapingSummary()
        audio_files = (
            await asyncio.to_thread(_download_audio_files, task_name, save_path)
            if source_files is None
            else await asyncio.to_thread(_input_audio_files, source_files)
        )
        if not audio_files:
            return ScrapingSummary()

        logger.info(
            "Scraping run input: task=%r, save_path=%r, source_files=%s, "
            "config=%s, library_tracks=%d, media_history=%d, cached_files=%d",
            task_name,
            save_path,
            [str(item) for item in audio_files],
            _scraping_config_log_text(config),
            len(library_tracks),
            len(media_history),
            len(cached_metadata or {}),
        )

        mapped_files = 0
        updated_files = 0
        moved_files = 0
        results: list[ScrapingFileResult] = []

        # Batch-infer metadata from directory structure
        dir_inferred: dict[Path, TrackMetadata] = {}
        if audio_files:
            dir_inferred = await asyncio.to_thread(_infer_batch_metadata, audio_files)

        for source_file in audio_files:
            try:
                result, mapped, updated, moved = await self._process_file(
                    source_file,
                    config,
                    library_tracks,
                    media_history,
                    dir_inferred=dir_inferred,
                    cached_candidates=(cached_metadata or {}).get(source_file, ()),
                    forced_metadata=(forced_metadata or {}).get(source_file),
                )
            except Exception as exc:
                logger.exception("Scraping file failed unexpectedly: source=%s", source_file)
                try:
                    source_metadata = await asyncio.to_thread(read_track_metadata, source_file)
                except Exception:
                    source_metadata = TrackMetadata(title=source_file.stem)
                result = ScrapingFileResult(
                    source_path=source_file,
                    library_path=None,
                    metadata=source_metadata,
                    status="failed",
                    operation_type=config.mode,
                    error_message=str(exc) or exc.__class__.__name__,
                    stage=exc.__class__.__name__,
                )
                mapped = updated = moved = 0
            results.append(result)
            mapped_files += mapped
            updated_files += updated
            moved_files += moved
            if on_file_result is not None:
                await on_file_result(result)

        return ScrapingSummary(
            source_files=len(audio_files),
            mapped_files=mapped_files,
            updated_files=updated_files,
            moved_files=moved_files,
            failed_files=sum(1 for item in results if item.status == "failed"),
            results=tuple(results),
        )

    async def _process_file(
        self,
        source_file: Path,
        config: ScrapingConfig,
        library_tracks: tuple[LibraryTrackSnapshot, ...],
        media_history: tuple[LibraryTrackSnapshot, ...],
        dir_inferred: dict[Path, TrackMetadata] | None = None,
        cached_candidates: tuple[TrackMetadata, ...] = (),
        forced_metadata: TrackMetadata | None = None,
    ) -> tuple[ScrapingFileResult, int, int, int]:
        working_file = source_file
        mapped_files = 0
        updated_files = 0
        moved_files = 0
        source_metadata = await asyncio.to_thread(read_track_metadata, source_file)
        raw_dir_meta = (dir_inferred or {}).get(source_file)
        dir_meta = await self._resolve_known_artist_directory(source_metadata, raw_dir_meta)
        match_metadata = _metadata_for_matching(source_metadata, source_file, dir_meta=dir_meta)
        fallback_metadata = _path_only_metadata_for_matching(source_file, raw_dir_meta)
        fallback_available = not _same_metadata_match_key(match_metadata, fallback_metadata)
        scrape_fields = _metadata_fields_union(
            config.scrape_when_missing,
            config.required_metadata,
        )
        missing_before = _missing_metadata_fields(source_metadata, scrape_fields)
        needs_scrape = bool(missing_before)
        metadata = _merge_metadata(source_metadata, match_metadata)
        candidate_count = 0
        candidate_reference = match_metadata
        candidate_stage = "metadata_candidate"
        tag_writer = self.tag_writer
        metadata_gain: tuple[RequiredMetadata, ...] = ()
        should_write_tags = forced_metadata is not None
        logger.info(
            "Scraping file input: source=%s, source_metadata=%s, dir_inferred=%s, "
            "match_metadata=%s, fallback_metadata=%s, scrape_fields=%s, "
            "missing_before=%s, cached_candidates=%s, forced_metadata=%s",
            source_file,
            _metadata_log_text(source_metadata),
            _metadata_log_text(dir_meta),
            _metadata_log_text(match_metadata),
            _metadata_log_text(fallback_metadata),
            scrape_fields,
            missing_before,
            _metadata_candidates_log_text(cached_candidates),
            _metadata_log_text(forced_metadata),
        )
        if forced_metadata is not None:
            metadata = _merge_metadata(source_metadata, forced_metadata)
            candidate_count = 1
            candidate_stage = "manual_metadata"
            missing_required = _missing_metadata_fields(metadata, config.required_metadata)
            if missing_required:
                error_message = f"手动元数据缺少必需字段：{', '.join(missing_required)}"
                logger.info(
                    "Scraping file result: source=%s, status=failed, stage=manual_metadata, "
                    "metadata=%s, error=%s",
                    source_file,
                    _metadata_log_text(metadata),
                    error_message,
                )
                return (
                    ScrapingFileResult(
                        source_path=source_file,
                        library_path=None,
                        metadata=metadata,
                        status="failed",
                        operation_type=config.mode,
                        error_message=error_message,
                        stage=candidate_stage,
                        needs_metadata_update=True,
                        candidate_count=candidate_count,
                    ),
                    0,
                    0,
                    0,
                )
        elif needs_scrape:
            candidates = cached_candidates
            looked_up = await _select_metadata_candidate(
                match_metadata,
                cached_candidates,
                config.required_metadata,
                artist_service=self.artist_service,
            )
            logger.info(
                "Scraping cached candidate result: source=%s, selected=%s",
                source_file,
                _metadata_log_text(looked_up),
            )
            if looked_up is None:
                online_candidates = await self._search_metadata_candidates(
                    source_metadata,
                    match_metadata,
                    config.required_metadata,
                )
                candidates = (*cached_candidates, *online_candidates)
                looked_up = await _select_metadata_candidate(
                    match_metadata,
                    online_candidates,
                    config.required_metadata,
                    artist_service=self.artist_service,
                )
                logger.info(
                    "Scraping online candidate result: source=%s, "
                    "online_candidates=%s, selected=%s",
                    source_file,
                    _metadata_candidates_log_text(online_candidates),
                    _metadata_log_text(looked_up),
                )
            if looked_up is None and fallback_available:
                fallback_candidates = await self._search_metadata_candidates(
                    fallback_metadata,
                    fallback_metadata,
                    config.required_metadata,
                )
                fallback_lookup = await _select_metadata_candidate(
                    fallback_metadata,
                    fallback_candidates,
                    config.required_metadata,
                    artist_service=self.artist_service,
                )
                candidates = (*candidates, *fallback_candidates)
                candidate_reference = fallback_metadata
                candidate_stage = "metadata_candidate_fallback"
                logger.info(
                    "Scraping fallback candidate result: source=%s, "
                    "fallback_metadata=%s, fallback_candidates=%s, selected=%s",
                    source_file,
                    _metadata_log_text(fallback_metadata),
                    _metadata_candidates_log_text(fallback_candidates),
                    _metadata_log_text(fallback_lookup),
                )
                if fallback_lookup is not None:
                    looked_up = fallback_lookup
            candidate_count = len(candidates)
            if looked_up is not None:
                metadata = _merge_metadata(metadata, looked_up)
            missing_required = _missing_metadata_fields(metadata, config.required_metadata)
            if looked_up is None:
                if not missing_required:
                    metadata_gain = _filled_metadata_fields(
                        source_metadata,
                        metadata,
                        missing_before,
                    )
                else:
                    error_message = await _candidate_failure_message(
                        candidate_reference,
                        config.required_metadata,
                        candidates,
                        artist_service=self.artist_service,
                    )
                    logger.info(
                        "Scraping file result: source=%s, status=failed, stage=%s, "
                        "metadata=%s, error=%s",
                        source_file,
                        candidate_stage,
                        _metadata_log_text(source_metadata),
                        error_message,
                    )
                    return (
                        ScrapingFileResult(
                            source_path=source_file,
                            library_path=None,
                            metadata=source_metadata,
                            status="failed",
                            operation_type=config.mode,
                            error_message=error_message,
                            stage=candidate_stage,
                            needs_metadata_update=needs_scrape,
                            candidate_count=candidate_count,
                        ),
                        0,
                        0,
                        0,
                    )
            elif missing_required:
                error_message = await _candidate_failure_message(
                    candidate_reference,
                    config.required_metadata,
                    candidates,
                    artist_service=self.artist_service,
                )
                logger.info(
                    "Scraping file result: source=%s, status=failed, stage=%s, "
                    "metadata=%s, selected=%s, missing_required=%s, error=%s",
                    source_file,
                    candidate_stage,
                    _metadata_log_text(source_metadata),
                    _metadata_log_text(looked_up),
                    missing_required,
                    error_message,
                )
                return (
                    ScrapingFileResult(
                        source_path=source_file,
                        library_path=None,
                        metadata=source_metadata,
                        status="failed",
                        operation_type=config.mode,
                        error_message=error_message,
                        stage=candidate_stage,
                        needs_metadata_update=needs_scrape,
                        candidate_count=candidate_count,
                    ),
                    0,
                    0,
                    0,
                )
            else:
                metadata_gain = _filled_metadata_fields(
                    source_metadata,
                    metadata,
                    missing_before,
                )
        if tag_writer is None and (should_write_tags or metadata_gain):
            logger.info(
                "Scraping file result: source=%s, status=failed, stage=tag_writer, "
                "metadata=%s, metadata_gain=%s",
                source_file,
                _metadata_log_text(source_metadata),
                metadata_gain,
            )
            return (
                ScrapingFileResult(
                    source_path=source_file,
                    library_path=None,
                    metadata=source_metadata,
                    status="failed",
                    operation_type=config.mode,
                    error_message="标签写入器不可用。",
                    stage="tag_writer",
                    needs_metadata_update=forced_metadata is not None or needs_scrape,
                    candidate_count=candidate_count,
                ),
                0,
                0,
                0,
            )

        # Resolve artist to canonical name
        if self.artist_service is not None:
            canonical = await self.artist_service.get_canonical_name(metadata.artist)
            if canonical is not None:
                metadata = TrackMetadata(
                    title=metadata.title,
                    artist=canonical,
                    album=metadata.album,
                    year=metadata.year,
                    track_number=metadata.track_number,
                    lyrics=metadata.lyrics,
                    cover_url=metadata.cover_url,
                    extra=metadata.extra,
                )

        duplicate = await _find_duplicate_media(
            _duplicate_metadata_candidates(source_metadata, match_metadata, metadata),
            (*library_tracks, *media_history),
            artist_service=self.artist_service,
        )
        overwrite_duplicate = False
        current_size = await asyncio.to_thread(_file_size, source_file)
        if duplicate is not None:
            if config.duplicate_handling == "ignore":
                error_message = _duplicate_skip_message(
                    metadata,
                    duplicate,
                    current_size,
                    reason="音乐库已存在，重复文件处理为不处理",
                )
                logger.info(
                    "Scraping file result: source=%s, status=skipped, stage=skip_duplicate, "
                    "metadata=%s, error=%s",
                    source_file,
                    _metadata_log_text(metadata),
                    error_message,
                )
                return (
                    ScrapingFileResult(
                        source_path=source_file,
                        library_path=None,
                        metadata=metadata,
                        status="skipped",
                        operation_type=config.mode,
                        error_message=error_message,
                        stage="skip_duplicate",
                        needs_metadata_update=needs_scrape,
                        candidate_count=candidate_count,
                    ),
                    0,
                    0,
                    0,
                )
            if config.duplicate_handling == "keep_largest":
                if duplicate.size is None or current_size <= duplicate.size:
                    reason = (
                        "音乐库文件大小未知，无法确认当前文件更大"
                        if duplicate.size is None
                        else "当前文件不大于音乐库文件，保留最大文件"
                    )
                    error_message = _duplicate_skip_message(
                        metadata,
                        duplicate,
                        current_size,
                        reason=reason,
                    )
                    logger.info(
                        "Scraping file result: source=%s, status=skipped, "
                        "stage=skip_smaller_duplicate, metadata=%s, error=%s",
                        source_file,
                        _metadata_log_text(metadata),
                        error_message,
                    )
                    return (
                        ScrapingFileResult(
                            source_path=source_file,
                            library_path=None,
                            metadata=metadata,
                            status="skipped",
                            operation_type=config.mode,
                            error_message=error_message,
                            stage="skip_smaller_duplicate",
                            needs_metadata_update=needs_scrape,
                            candidate_count=candidate_count,
                        ),
                        0,
                        0,
                        0,
                    )
                overwrite_duplicate = True
            elif config.duplicate_handling in {"overwrite", "keep_largest"}:
                overwrite_duplicate = True

        overwritten_existing_target = False
        operation_type = config.mode
        if config.mode == "mapped":
            mapped_result = await asyncio.to_thread(
                _copy_to_mapping,
                source_file,
                config,
                hardlink=not metadata_gain,
                overwrite=not _will_classify_or_rename(config),
            )
            working_file = mapped_result.path
            operation_type = mapped_result.operation_type
            overwritten_existing_target = mapped_result.overwritten_existing
            mapped_files += 1
        elif config.mode == "copy":
            mapped_result = await asyncio.to_thread(
                _copy_to_mapping,
                source_file,
                config,
                hardlink=False,
                overwrite=not _will_classify_or_rename(config),
            )
            working_file = mapped_result.path
            operation_type = mapped_result.operation_type
            overwritten_existing_target = mapped_result.overwritten_existing
            mapped_files += 1

        if should_write_tags or metadata_gain:
            assert tag_writer is not None
            await tag_writer.write(working_file, metadata)
            updated_files += 1

        final_result = await asyncio.to_thread(
            _classify_or_rename,
            working_file,
            metadata,
            config,
            overwrite=True,
        )
        final_file = final_result.path
        overwritten_existing_target = (
            overwritten_existing_target or final_result.overwritten_existing
        )
        if final_file != working_file:
            moved_files += 1
        if overwrite_duplicate and duplicate is not None:
            remark = _duplicate_overwrite_message(metadata, duplicate, current_size)
        elif overwritten_existing_target:
            remark = _target_overwrite_message(final_file)
        else:
            remark = "刮削并转移完成"
        logger.info(
            "Scraping file result: source=%s, status=success, library_path=%s, "
            "metadata=%s, metadata_gain=%s, candidate_count=%d, remark=%s",
            source_file,
            final_file,
            _metadata_log_text(metadata),
            metadata_gain,
            candidate_count,
            remark,
        )
        return (
            ScrapingFileResult(
                source_path=source_file,
                library_path=final_file,
                metadata=metadata,
                status="success",
                operation_type=operation_type,
                error_message=remark,
                needs_metadata_update=forced_metadata is not None or needs_scrape,
                candidate_count=candidate_count,
            ),
            mapped_files,
            updated_files,
            moved_files,
        )

    async def search_metadata_candidates(
        self,
        source_metadata: TrackMetadata,
        match_metadata: TrackMetadata,
        required: tuple[RequiredMetadata, ...] = (),
    ) -> tuple[TrackMetadata, ...]:
        return await self._search_metadata_candidates(source_metadata, match_metadata, required)

    async def select_metadata_candidate(
        self,
        reference: TrackMetadata,
        candidates: tuple[TrackMetadata, ...],
        required: tuple[RequiredMetadata, ...] = (),
    ) -> TrackMetadata | None:
        return await _select_metadata_candidate(
            reference,
            candidates,
            required,
            artist_service=self.artist_service,
        )

    async def metadata_candidate_failure_message(
        self,
        reference: TrackMetadata,
        candidates: tuple[TrackMetadata, ...],
        required: tuple[RequiredMetadata, ...] = (),
    ) -> str:
        return await _candidate_failure_message(
            reference,
            required,
            candidates,
            artist_service=self.artist_service,
        )

    async def _search_metadata_candidates(
        self,
        source_metadata: TrackMetadata,
        match_metadata: TrackMetadata,
        required: tuple[RequiredMetadata, ...],
    ) -> tuple[TrackMetadata, ...]:
        # Build search tuples: (title, artist) from various sources
        searches: list[tuple[str, str | None]] = []
        seen_queries: set[tuple[str, str | None]] = set()

        for title, artist in [
            (match_metadata.title, match_metadata.artist),
            (source_metadata.title, source_metadata.artist),
        ]:
            search_title = _metadata_search_title(title)
            if not search_title:
                continue
            # Search with each alias of the artist
            if self.artist_service is not None and artist:
                aliases = await self.artist_service.get_aliases(artist)
                for alias in aliases:
                    query: tuple[str, str | None] = (search_title, alias)
                    if query not in seen_queries:
                        seen_queries.add(query)
                        searches.append(query)
            else:
                query: tuple[str, str | None] = (search_title, artist)
                if query not in seen_queries:
                    seen_queries.add(query)
                    searches.append(query)

        # Also add a pure title search as fallback
        for title in (match_metadata.title, source_metadata.title):
            search_title = _metadata_search_title(title)
            if search_title:
                query = (search_title, None)
                if query not in seen_queries:
                    seen_queries.add(query)
                    searches.append(query)

        candidates: list[TrackMetadata] = []
        seen: set[tuple[str, str, str]] = set()
        for title, artist in searches:
            if not title:
                continue
            async for batch in _iter_metadata_candidate_batches(
                self.metadata,
                title=title,
                artist=artist,
                limit=5,
            ):
                for candidate in batch:
                    key = (
                        _normalize_match_text(candidate.title),
                        _normalize_match_text(candidate.artist),
                        _normalize_match_text(candidate.album),
                    )
                    if key in seen:
                        continue
                    seen.add(key)
                    candidates.append(candidate)
        return tuple(candidates)

    async def _resolve_known_artist_directory(
        self,
        source_metadata: TrackMetadata,
        dir_meta: TrackMetadata | None,
    ) -> TrackMetadata | None:
        if (
            self.artist_service is None
            or dir_meta is None
            or source_metadata.artist
            or dir_meta.artist
            or not dir_meta.album
        ):
            return dir_meta
        if not await self.artist_service.has_artist_name(dir_meta.album):
            return dir_meta
        return TrackMetadata(
            title=dir_meta.title,
            artist=dir_meta.album,
            album=source_metadata.album,
            year=dir_meta.year,
            track_number=dir_meta.track_number,
            lyrics=dir_meta.lyrics,
            cover_url=dir_meta.cover_url,
            extra=dir_meta.extra,
        )


async def _iter_metadata_candidate_batches(
    metadata: MetadataCascade,
    *,
    title: str,
    artist: str | None,
    limit: int,
) -> AsyncIterator[tuple[TrackMetadata, ...]]:
    for provider in metadata.providers:
        try:
            batch_iter = getattr(provider, "iter_metadata_batches", None)
            if batch_iter is not None:
                async for batch in batch_iter(title=title, artist=artist, limit=limit):
                    yield batch
                continue
            search = getattr(provider, "search_metadata", None)
            if search is None:
                lookup = await provider.lookup(title=title, artist=artist)
                batch = (lookup,) if lookup is not None else ()
            else:
                batch = await search(title=title, artist=artist, limit=limit)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Metadata provider %s failed: %s", provider.name, exc)
            continue
        if batch:
            yield tuple(batch)


def scraping_config_from_payload(payload: dict[str, object]) -> ScrapingConfig:
    scraping = payload.get("scraping")
    if not isinstance(scraping, dict):
        scraping = {}
    mode = str(scraping.get("mode") or "mapped")
    classify_by = str(scraping.get("classify_by") or "artist")
    duplicate_handling = str(scraping.get("duplicate_handling") or "ignore")
    required = scraping.get("required_metadata")
    scrape_when_missing = scraping.get("scrape_when_missing")
    required_metadata = _required_metadata(required)
    scrape_metadata = _required_metadata(scrape_when_missing)
    if "scrape_when_missing" not in scraping:
        scrape_metadata = required_metadata
    if mode not in {"source", "mapped", "copy"}:
        mode = "mapped"
    if duplicate_handling not in {"ignore", "overwrite", "keep_largest"}:
        duplicate_handling = "ignore"
    return ScrapingConfig(
        enabled=bool(scraping.get("enabled")),
        mode=mode,
        source_directory=_optional_path(scraping.get("source_directory")),
        mapped_directory=_optional_path(scraping.get("mapped_directory")),
        scrape_when_missing=scrape_metadata,
        required_metadata=required_metadata,
        auto_rename=bool(scraping.get("auto_rename")),
        auto_classify=bool(scraping.get("auto_classify")),
        classify_by="album" if classify_by == "album" else "artist",
        duplicate_handling=duplicate_handling,
    )


def read_track_metadata(path: Path) -> TrackMetadata:
    from mutagen import File as MutagenFile

    audio = MutagenFile(path, easy=True)
    title = path.stem
    artist = None
    album = None
    year = None
    track_number = None
    lyrics = None
    if audio is not None and audio.tags:
        title = _first_tag(audio.tags.get("title")) or title
        artist = _first_tag(audio.tags.get("artist"))
        album = _first_tag(audio.tags.get("album"))
        year = _parse_year(_first_tag(audio.tags.get("date")))
        track_number = _parse_track_number(_first_tag(audio.tags.get("tracknumber")))
        lyrics = _first_tag(audio.tags.get("lyrics"))
    return TrackMetadata(
        title=title,
        artist=artist,
        album=album,
        year=year,
        track_number=track_number,
        lyrics=lyrics,
    )


def _download_audio_files(task_name: str, save_path: str | None) -> list[Path]:
    candidates: list[Path] = []
    if save_path:
        root = Path(save_path)
        candidates.append(root)
        if task_name:
            candidates.append(root / task_name)
    elif task_name:
        candidates.append(Path(task_name))
    seen: set[Path] = set()
    files: list[Path] = []
    for candidate in candidates:
        for audio_file in _audio_files(candidate):
            resolved = audio_file.resolve()
            if resolved not in seen:
                seen.add(resolved)
                files.append(resolved)
    return files


def _input_audio_files(source_files: tuple[Path, ...]) -> list[Path]:
    seen: set[Path] = set()
    files: list[Path] = []
    for source_file in source_files:
        path = source_file.expanduser()
        if not path.is_file() or path.suffix.casefold() not in _AUDIO_EXTENSIONS:
            continue
        resolved = path.resolve()
        if resolved in seen:
            continue
        seen.add(resolved)
        files.append(resolved)
    return files


@dataclass(frozen=True, slots=True)
class _DirInferredInfo:
    """Metadata inferred from directory structure analysis."""
    artist: str | None = None
    album: str | None = None
    year: int | None = None


def _infer_batch_metadata(source_files: list[Path]) -> dict[Path, TrackMetadata]:
    """Infer metadata from directory structure for a batch of source files.

    Analyzes parent directory names to extract artist/album info when
    individual file tags are empty. Supports patterns such as:

      周杰伦/七里香/01. 七里香.flac
      ArtistName/AlbumName/01 - Title.flac
      2014 周杰伦 - 哎呦，不错哦[24bit 96kHz FLAC]/10. 聽爸爸的話.flac

    Uses cross-file validation within the same directory to increase confidence.
    """
    # Group files by immediate parent directory
    dir_groups: dict[Path, list[Path]] = {}
    for f in source_files:
        parent = f.parent
        if parent not in dir_groups:
            dir_groups[parent] = []
        dir_groups[parent].append(f)

    # For each directory, infer artist/album from the directory name
    dir_info: dict[Path, _DirInferredInfo] = {}
    for dir_path, children in dir_groups.items():
        info = _analyze_directory(dir_path, children)
        dir_info[dir_path] = info

    # Build per-file result: merge inferred dir info with filename-derived title
    result: dict[Path, TrackMetadata] = {}
    for f in source_files:
        parent = f.parent
        info = dir_info.get(parent, _DirInferredInfo())

        # Extract title from filename (with track prefix stripped)
        stem = f.stem
        title_no_track = _strip_track_prefix(stem)

        # Check if filename also carries artist (e.g. "Artist - Title")
        parsed = _parse_artist_title(title_no_track)
        if parsed is not None:
            file_artist, file_title = parsed
            # File-level artist overrides dir-level inference
            result[f] = TrackMetadata(
                title=file_title,
                artist=file_artist,
                album=info.album,
                year=info.year,
            )
        else:
            result[f] = TrackMetadata(
                title=title_no_track or stem,
                artist=info.artist,
                album=info.album,
                year=info.year,
            )

    return result


def infer_metadata_from_paths(source_files: list[Path]) -> dict[Path, TrackMetadata]:
    return _infer_batch_metadata(source_files)


def _clean_album_name(name: str) -> str:
    """Remove trailing format/quality noise from an album or artist name."""
    name = _ALBUM_TRAILING_NOISE_RE.sub("", name).strip()
    name = re.sub(r"\s*\{[^}]*\}\s*$", "", name).strip()
    name = re.sub(r"\s*[\[(]?(?:19|20)\d{2}[\])]?\s*$", "", name).strip()
    name = re.sub(r"\s+", " ", name).strip()
    return name


def _analyze_directory(dir_path: Path, children: list[Path]) -> _DirInferredInfo:
    """Analyze a single directory name and its child files for metadata.

    Returns inferred artist/album or None if the directory name is not
    informative (e.g. root directories, generic names, disc markers).

    Handles multi-CD structures by skipping disc-marking dirs (CD1, CD2, etc.)
    and analyzing their parent instead.
    """
    dir_name = dir_path.name.strip()
    if not dir_name or dir_name in {".", "..", "downloads", "music", "library"}:
        return _DirInferredInfo()

    # Strip bracketed noise
    cleaned = _DIR_NOISE_RE.sub("", dir_name).strip()
    if not cleaned:
        cleaned = dir_name
    year = _parse_year(cleaned)

    # Strip leading year patterns: "2014 周杰伦 - 哎呦" → "周杰伦 - 哎呦"
    cleaned = re.sub(r"^\d{4}\s+", "", cleaned).strip()

    # Detect disc markers (CD1, CD2, Disc 2, etc.) — skip and analyze parent
    if _DISC_DIR_RE.match(cleaned):
        parent = dir_path.parent
        if parent.name.strip() and parent.name.strip() not in {".", "..", "downloads"}:
            return _analyze_directory(parent, children)
        return _DirInferredInfo()

    # Try "Artist - Album" pattern
    parts = _ARTIST_SEP_RE.split(cleaned, maxsplit=1)
    if len(parts) == 2:
        artist_part = parts[0].strip()
        album_part = _clean_album_name(parts[1].strip())
        if artist_part and len(artist_part) >= 1:
            return _DirInferredInfo(artist=artist_part, album=album_part, year=year)

    # No artist separator found. Check grandparent as potential artist.
    grandparent = dir_path.parent.name.strip()
    grandparent_valid = (
        grandparent
        and grandparent not in {".", "..", "downloads", "source", "mapped"}
    )

    if grandparent_valid:
        gp_cleaned = _DIR_NOISE_RE.sub("", grandparent).strip()
        gp_cleaned = re.sub(r"^\d{4}\s+", "", gp_cleaned).strip()
        gp_parts = _ARTIST_SEP_RE.split(gp_cleaned, maxsplit=1)

        if len(gp_parts) == 2:
            # Grandparent has "Artist - Album" format
            # Current dir is the actual album, OR if it's a sub-dir (like CD1),
            # it was already handled above. Use grandparent's album content here.
            gp_album = _clean_album_name(gp_parts[1].strip())
            return _DirInferredInfo(
                artist=gp_parts[0].strip(),
                album=gp_album,
                year=year or _parse_year(gp_cleaned),
            )
        elif gp_cleaned and len(gp_cleaned) >= 2:
            # Grandparent is the artist, current dir is the album
            return _DirInferredInfo(
                artist=gp_cleaned,
                album=_clean_album_name(cleaned),
                year=year,
            )

    # No grandparent or grandparent not usable. Treat the current directory as
    # album-only unless an explicit artist signal was found above.
    child_stems = [c.stem for c in children]
    match_count = sum(
        1 for s in child_stems
        if _normalize_match_text(cleaned) in _normalize_match_text(s)
    )
    if children and match_count / len(children) >= 0.5:
        return _DirInferredInfo(artist=None, album=_clean_album_name(cleaned), year=year)

    return _DirInferredInfo(artist=None, album=_clean_album_name(cleaned), year=year)


def _audio_files(path: Path) -> list[Path]:
    if path.is_file() and path.suffix.casefold() in _AUDIO_EXTENSIONS:
        return [path]
    if path.is_dir():
        return [
            item
            for item in path.rglob("*")
            if item.is_file() and item.suffix.casefold() in _AUDIO_EXTENSIONS
        ]
    return []


def _copy_to_mapping(
    source_file: Path,
    config: ScrapingConfig,
    *,
    hardlink: bool,
    overwrite: bool,
) -> _PathOperationResult:
    if config.mapped_directory is None:
        raise RuntimeError("Target directory is required for mapped or copy scraping.")
    relative = source_file.name
    if config.source_directory is not None:
        try:
            relative = str(source_file.relative_to(config.source_directory))
        except ValueError:
            relative = source_file.name
    target = config.mapped_directory / relative
    if not overwrite:
        target = _unique_path(target)
    elif _same_existing_file(source_file, target):
        return _PathOperationResult(target, operation_type="mapped")
    overwritten_existing = overwrite and target.exists()
    target.parent.mkdir(parents=True, exist_ok=True)
    if hardlink:
        try:
            if overwritten_existing:
                _remove_existing_target(target)
            os.link(source_file, target)
            return _PathOperationResult(
                target,
                operation_type="mapped",
                overwritten_existing=overwritten_existing,
            )
        except OSError:
            pass
    if overwritten_existing:
        _remove_existing_target(target)
    shutil.copy2(source_file, target)
    return _PathOperationResult(
        target,
        operation_type="copy",
        overwritten_existing=overwritten_existing,
    )


def _classify_or_rename(
    path: Path,
    metadata: TrackMetadata,
    config: ScrapingConfig,
    *,
    overwrite: bool,
) -> _PathOperationResult:
    target_dir = path.parent
    if config.auto_classify:
        group = metadata.artist if config.classify_by == "artist" else metadata.album
        if group:
            classify_root = (
                config.mapped_directory
                if config.mode in {"mapped", "copy"}
                else config.source_directory
            )
            target_dir = (classify_root or path.parent) / _safe_path_part(group)
    target_name = path.name
    if config.auto_rename:
        target_name = f"{_safe_path_part(metadata.title or path.stem)}{path.suffix}"
    target = target_dir / target_name
    if not overwrite:
        target = _unique_path(target, current=path)
    if target == path or _same_existing_file(path, target):
        return _PathOperationResult(path, operation_type=config.mode)
    target.parent.mkdir(parents=True, exist_ok=True)
    overwritten_existing = overwrite and target.exists()
    if overwritten_existing:
        _remove_existing_target(target)
    shutil.move(str(path), str(target))
    # Clean up empty parent directories left behind after the move
    _remove_empty_parents(path.parent, config)
    return _PathOperationResult(
        target,
        operation_type=config.mode,
        overwritten_existing=overwritten_existing,
    )


def _remove_empty_parents(source_dir: Path, config: ScrapingConfig) -> None:
    """Remove empty ancestor directories up to the configured root."""
    parent = source_dir
    while parent != parent.parent:  # stop at filesystem root
        if not parent.is_dir():
            break
        try:
            if any(parent.iterdir()):
                break
            parent.rmdir()
        except (OSError, PermissionError):
            break
        # Stop at the mapped/source root directory — don't remove it
        root = config.mapped_directory or config.source_directory
        if root and parent == root:
            break
        parent = parent.parent


def _remove_existing_target(target: Path) -> None:
    if not target.exists():
        return
    if target.is_dir():
        raise RuntimeError(f"Target path is a directory: {target}")
    target.unlink()


def _same_existing_file(left: Path, right: Path) -> bool:
    try:
        return left.exists() and right.exists() and left.samefile(right)
    except OSError:
        return False


def _file_size(path: Path) -> int:
    return path.stat().st_size


def _will_classify_or_rename(config: ScrapingConfig) -> bool:
    return config.auto_classify or config.auto_rename


def _duplicate_metadata_candidates(
    source_metadata: TrackMetadata,
    match_metadata: TrackMetadata,
    scraped_metadata: TrackMetadata,
) -> tuple[TrackMetadata, ...]:
    candidates: list[TrackMetadata] = []
    seen: set[tuple[str, str, str]] = set()
    for metadata in (source_metadata, match_metadata, scraped_metadata):
        key = (
            _normalize_match_text(metadata.title),
            _normalize_match_text(metadata.artist),
            _normalize_match_text(metadata.album),
        )
        if not key[0] or key in seen:
            continue
        seen.add(key)
        candidates.append(metadata)
    return tuple(candidates)


async def _find_duplicate_media(
    candidates: tuple[TrackMetadata, ...],
    tracks: tuple[LibraryTrackSnapshot, ...],
    *,
    artist_service: ArtistService | None = None,
) -> LibraryTrackSnapshot | None:
    best: LibraryTrackSnapshot | None = None
    best_score = 0
    for metadata in candidates:
        title = normalize_metadata_match_text(metadata.title)
        artist = normalize_metadata_match_text(metadata.artist)
        album = normalize_metadata_match_text(metadata.album)
        if not title:
            continue
        for track in tracks:
            if normalize_metadata_match_text(track.title) != title:
                continue
            track_artist = normalize_metadata_match_text(track.artist)
            track_album = normalize_metadata_match_text(track.album)
            artist_score = await _match_artist_with_aliases(
                metadata.artist,
                track.artist,
                artist_service=artist_service,
            )
            artist_matches = artist_score > 0
            if artist and track_artist and not artist_matches:
                continue
            score = 1
            if artist and artist_matches:
                score += 2
            if album and track_album == album:
                score += 1
            if score > best_score:
                best = track
                best_score = score
    return best


def _library_track_path(track: LibraryTrackSnapshot) -> Path | None:
    if not track.path:
        return None
    return Path(track.path)


def _duplicate_skip_message(
    metadata: TrackMetadata,
    track: LibraryTrackSnapshot,
    current_size: int,
    *,
    reason: str,
) -> str:
    existing_path = _library_track_path(track)
    path_text = f"，已存在路径={existing_path}" if existing_path is not None else ""
    return (
        f"已跳过：{reason}。"
        f"识别={metadata.title}/{metadata.artist or '-'}，"
        f"当前大小={_format_size(current_size)}，"
        f"音乐库大小={_format_size(track.size)}"
        f"{path_text}"
    )


def _duplicate_overwrite_message(
    metadata: TrackMetadata,
    track: LibraryTrackSnapshot,
    current_size: int,
) -> str:
    existing_path = _library_track_path(track)
    path_text = f"，原路径={existing_path}" if existing_path is not None else ""
    return (
        "覆盖完成：音乐库中已存在匹配媒体。"
        f"识别={metadata.title}/{metadata.artist or '-'}，"
        f"当前大小={_format_size(current_size)}，"
        f"音乐库大小={_format_size(track.size)}"
        f"{path_text}"
    )


def _target_overwrite_message(target: Path) -> str:
    return f"覆盖完成：目标路径已存在。路径={target}"


def _format_size(value: int | None) -> str:
    if value is None:
        return "未知"
    units = ("B", "KB", "MB", "GB", "TB")
    size = float(value)
    index = 0
    while size >= 1024 and index < len(units) - 1:
        size /= 1024
        index += 1
    if index == 0:
        return f"{int(size)} {units[index]}"
    return f"{size:.2f} {units[index]}"


def _scraping_config_log_text(config: ScrapingConfig) -> str:
    return (
        "{"
        f"enabled={config.enabled}, mode={config.mode!r}, "
        f"source_directory={str(config.source_directory) if config.source_directory else None!r}, "
        f"mapped_directory={str(config.mapped_directory) if config.mapped_directory else None!r}, "
        f"scrape_when_missing={config.scrape_when_missing}, "
        f"required_metadata={config.required_metadata}, "
        f"auto_rename={config.auto_rename}, auto_classify={config.auto_classify}, "
        f"classify_by={config.classify_by!r}, duplicate_handling={config.duplicate_handling!r}"
        "}"
    )


def _metadata_log_text(metadata: TrackMetadata | None) -> str:
    if metadata is None:
        return "None"
    return (
        "{"
        f"title={metadata.title!r}, artist={metadata.artist!r}, album={metadata.album!r}, "
        f"year={metadata.year!r}, track_number={metadata.track_number!r}, "
        f"lyrics={bool(metadata.lyrics)}, cover_url={metadata.cover_url!r}, "
        f"extra_keys={sorted(metadata.extra.keys()) if metadata.extra else []}"
        "}"
    )


def _metadata_candidates_log_text(candidates: tuple[TrackMetadata, ...]) -> str:
    if not candidates:
        return "[]"
    items = ", ".join(_metadata_log_text(candidate) for candidate in candidates[:10])
    suffix = f", ... +{len(candidates) - 10} more" if len(candidates) > 10 else ""
    return f"[{items}{suffix}]"


def _metadata_missing(metadata: TrackMetadata, required: tuple[RequiredMetadata, ...]) -> bool:
    for field in required:
        value = getattr(metadata, field)
        if not isinstance(value, str) or not value.strip():
            return True
    return False


def _metadata_for_matching(
    metadata: TrackMetadata,
    source_file: Path,
    dir_meta: TrackMetadata | None = None,
) -> TrackMetadata:
    """Build a matching metadata by pulling info from multiple sources.

    Priority:
    1. File tags (already in `metadata`)
    2. Directory structure inference (`dir_meta`)
    3. Filename parsing (`Artist - Title`)
    """
    if metadata.artist:
        return metadata

    # Try filename parsing first
    parsed = _parse_artist_title(metadata.title) or _parse_artist_title(source_file.stem)
    if parsed is not None:
        artist, title = parsed
        album = metadata.album or (dir_meta.album if dir_meta else None)
        return TrackMetadata(
            title=title,
            artist=artist,
            album=album,
            year=metadata.year,
            track_number=metadata.track_number,
            lyrics=metadata.lyrics,
            cover_url=metadata.cover_url,
            extra=metadata.extra,
        )

    # Fall back to directory-inferred metadata
    if dir_meta is not None and (dir_meta.artist or dir_meta.album):
        # Use title from dir_meta (track prefix stripped) or strip it from source
        inferred_title = dir_meta.title or _strip_track_prefix(metadata.title) or metadata.title
        return TrackMetadata(
            title=inferred_title,
            artist=dir_meta.artist,
            album=dir_meta.album or metadata.album,
            year=metadata.year,
            track_number=metadata.track_number,
            lyrics=metadata.lyrics,
            cover_url=metadata.cover_url,
            extra=metadata.extra,
        )

    return metadata


def _path_only_metadata_for_matching(
    source_file: Path,
    dir_meta: TrackMetadata | None = None,
) -> TrackMetadata:
    if dir_meta is not None:
        return dir_meta

    title_no_track = _strip_track_prefix(source_file.stem) or source_file.stem
    parsed = _parse_artist_title(title_no_track)
    if parsed is not None:
        artist, title = parsed
    else:
        artist = None
        title = title_no_track
    return TrackMetadata(title=title, artist=artist)


def _same_metadata_match_key(left: TrackMetadata, right: TrackMetadata) -> bool:
    return (
        _normalize_match_text(left.title),
        _normalize_match_text(left.artist),
        _normalize_match_text(left.album),
    ) == (
        _normalize_match_text(right.title),
        _normalize_match_text(right.artist),
        _normalize_match_text(right.album),
    )


def _parse_artist_title(value: str | None) -> tuple[str, str] | None:
    if not value:
        return None
    text = _strip_track_prefix(value)
    for delimiter in (" - ", " – ", " — ", "-", "–", "—"):
        if delimiter not in text:
            continue
        left, right = (part.strip() for part in text.split(delimiter, 1))
        if len(left) >= 1 and len(right) >= 1:
            return left, right
    return None


def _metadata_search_title(title: str | None) -> str | None:
    text = _strip_track_prefix(unicodedata.normalize("NFKC", str(title or "").strip()))
    if not text:
        return None
    if not _CJK_RE.search(text):
        return text
    normalized = _t2s.convert(text).translate(_SEARCH_TITLE_TRANSLATION)
    return normalized.strip() or text


def _strip_track_prefix(value: str) -> str:
    return re.sub(
        r"^\s*(?:(?:cd\s*)?\d{1,3}(?:[.\-_、\s]+))+",
        "",
        value,
        flags=re.I,
    ).strip()


_MATCH_SCORE_THRESHOLD = 1  # Minimum total score to accept a candidate


async def _select_metadata_candidate(
    existing: TrackMetadata,
    candidates: tuple[TrackMetadata, ...],
    required: tuple[RequiredMetadata, ...],
    *,
    artist_service: ArtistService | None = None,
) -> TrackMetadata | None:
    """Select the best metadata candidate using scoring.

    Scores all candidates by title/artist/album match against the existing
    metadata. Returns the highest-scoring candidate that fills required
    fields, if its score meets the minimum threshold.
    """
    if not candidates:
        return None

    scored: list[tuple[int, TrackMetadata]] = []
    for candidate in candidates:
        if not _candidate_fills_required(existing, candidate, required):
            continue
        score = await _metadata_match_score(existing, candidate, artist_service=artist_service)
        scored.append((score.total, candidate))

    if not scored:
        return None

    # Sort by score descending, then pick the best
    scored.sort(key=lambda x: x[0], reverse=True)
    best_total, best_candidate = scored[0]

    if best_total < _MATCH_SCORE_THRESHOLD:
        return None

    return best_candidate


def _candidate_fills_required(
    existing: TrackMetadata,
    candidate: TrackMetadata,
    required: tuple[RequiredMetadata, ...],
) -> bool:
    for field in required:
        current = getattr(existing, field)
        if isinstance(current, str) and current.strip():
            continue
        value = getattr(candidate, field)
        if not isinstance(value, str) or not value.strip():
            return False
    return True


def _candidate_has_conflicting_album(existing: TrackMetadata, candidate: TrackMetadata) -> bool:
    return bool(
        existing.album
        and candidate.album
        and _match_score(existing.album, candidate.album) == 0
    )


async def _candidate_failure_message(
    metadata: TrackMetadata,
    required: tuple[RequiredMetadata, ...],
    candidates: tuple[TrackMetadata, ...],
    *,
    artist_service: ArtistService | None = None,
) -> str:
    required_text = ", ".join(required) if required else "none"
    score_text = await _best_candidate_score_text(
        metadata,
        candidates,
        artist_service=artist_service,
    )
    diagnostics_text = await _candidate_diagnostics_text(
        metadata,
        required,
        candidates,
        artist_service=artist_service,
    )
    return (
        "未找到可信的刮削候选。"
        f"title={metadata.title!r}, artist={metadata.artist!r}, "
        f"required={required_text}, candidates={len(candidates)}"
        f"{score_text}{diagnostics_text}"
    )


async def _best_candidate_score_text(
    metadata: TrackMetadata,
    candidates: tuple[TrackMetadata, ...],
    *,
    artist_service: ArtistService | None = None,
) -> str:
    best_candidate = None
    best_score = _MatchScore()
    for candidate in candidates:
        score = await _metadata_match_score(metadata, candidate, artist_service=artist_service)
        if score.total > best_score.total:
            best_candidate = candidate
            best_score = score
    if best_candidate is None:
        return ""
    return (
        f", best={best_candidate.title!r}/{best_candidate.artist!r}/"
        f"{best_candidate.album!r}, score={best_score.total}"
        f"(title={best_score.title}, artist={best_score.artist}, album={best_score.album})"
    )


async def _candidate_diagnostics_text(
    metadata: TrackMetadata,
    required: tuple[RequiredMetadata, ...],
    candidates: tuple[TrackMetadata, ...],
    *,
    artist_service: ArtistService | None = None,
) -> str:
    if not candidates:
        return ""
    items: list[str] = []
    for index, candidate in enumerate(candidates[:5], start=1):
        score = await _metadata_match_score(metadata, candidate, artist_service=artist_service)
        missing = _candidate_missing_required(metadata, candidate, required)
        album_conflict = _candidate_has_conflicting_album(metadata, candidate)
        reasons: list[str] = []
        if missing:
            reasons.append(f"missing={','.join(missing)}")
        if album_conflict:
            reasons.append("album_conflict")
        if score.total < _MATCH_SCORE_THRESHOLD:
            reasons.append(f"score_below_threshold={_MATCH_SCORE_THRESHOLD}")
        reason_text = ";".join(reasons) if reasons else "eligible"
        items.append(
            f"#{index}:{candidate.title!r}/{candidate.artist!r}/{candidate.album!r} "
            f"score={score.total}(title={score.title},artist={score.artist},album={score.album}) "
            f"{reason_text}"
        )
    suffix = "" if len(candidates) <= 5 else f"; ... +{len(candidates) - 5} more"
    return f", diagnostics=[{'; '.join(items)}{suffix}]"


def _candidate_missing_required(
    existing: TrackMetadata,
    candidate: TrackMetadata,
    required: tuple[RequiredMetadata, ...],
) -> tuple[RequiredMetadata, ...]:
    missing: list[RequiredMetadata] = []
    for field in required:
        current = getattr(existing, field)
        if isinstance(current, str) and current.strip():
            continue
        value = getattr(candidate, field)
        if not isinstance(value, str) or not value.strip():
            missing.append(field)
    return tuple(missing)


async def _metadata_match_score(
    existing: TrackMetadata,
    scraped: TrackMetadata,
    *,
    artist_service: ArtistService | None = None,
) -> _MatchScore:
    title_score = _match_score(existing.title, scraped.title)
    artist_score = await _match_artist_with_aliases(
        existing.artist,
        scraped.artist,
        artist_service=artist_service,
    )
    album_score = _match_score(existing.album, scraped.album)

    # Strong penalty: existing artist known but candidate artist doesn't match
    if existing.artist and artist_score == 0:
        # Check if the existing artist actually had a value, not just blank
        if existing.artist.strip():
            artist_score = -3

    # Title mismatch means the whole candidate is suspect
    if title_score < 2 and existing.title:
        # Even a partial title match is better than nothing for the fallback case
        pass

    # If artist is unknown but title matches, that might be OK — but
    # a complete mismatch of everything means this candidate is wrong
    return _MatchScore(title=title_score, artist=artist_score, album=album_score)


def _match_score(left: str | None, right: str | None) -> int:
    left_normalized = _normalize_match_text(left)
    right_normalized = _normalize_match_text(right)
    if not left_normalized or not right_normalized:
        return 0
    if left_normalized == right_normalized:
        return 2
    if left_normalized in right_normalized or right_normalized in left_normalized:
        return 1
    # Fuzzy word overlap: if most significant words match, give partial score
    if _fuzzy_word_overlap(left, right) >= 0.6:
        return 1
    return 0


def _fuzzy_word_overlap(left: str | None, right: str | None) -> float:
    """Compute the fraction of tokens from the shorter text present in the longer one.

    Splits each string on non-alphanumeric boundaries, extracts lowercased
    tokens of at least 2 characters, then measures overlap ratio.
    """
    if not left or not right:
        return 0.0
    left_tokens = {m.group(0).casefold() for m in re.finditer(r"[a-z0-9]{2,}", left)}
    right_tokens = {m.group(0).casefold() for m in re.finditer(r"[a-z0-9]{2,}", right)}
    if not left_tokens or not right_tokens:
        return 0.0
    shorter = left_tokens if len(left_tokens) <= len(right_tokens) else right_tokens
    longer = right_tokens if len(left_tokens) <= len(right_tokens) else left_tokens
    return len(shorter & longer) / len(shorter)


def _match_artist(left: str | None, right: str | None) -> int:
    if not left or not right:
        return 0
    scores = [
        _match_score(left_item, right_item)
        for left_item in _split_artist_names(left)
        for right_item in _split_artist_names(right)
    ]
    return max(scores, default=0)


async def _match_artist_with_aliases(
    left: str | None,
    right: str | None,
    *,
    artist_service: ArtistService | None = None,
) -> int:
    if not left or not right:
        return 0
    direct_score = _match_artist(left, right)
    if direct_score > 0 or artist_service is None:
        return direct_score
    left_aliases: list[str] = []
    for item in _split_artist_names(left):
        left_aliases.extend(await artist_service.get_aliases(item))
    right_aliases: list[str] = []
    for item in _split_artist_names(right):
        right_aliases.extend(await artist_service.get_aliases(item))
    left_values = {_normalize_match_text(item) for item in left_aliases if item}
    right_values = {_normalize_match_text(item) for item in right_aliases if item}
    return 2 if left_values and right_values and left_values & right_values else 0


def _split_artist_names(value: str) -> list[str]:
    return split_artist_credit(value)


def normalize_metadata_match_text(value: str | None) -> str:
    if not value:
        return ""
    text = unicodedata.normalize("NFKC", value)
    text = re.sub(r"\[[^\]]+\]|\([^\)]*\)", " ", text)
    text = _t2s.convert(text).translate(_SEARCH_TITLE_TRANSLATION)
    text = re.sub(r"[^0-9a-zA-Z\u4e00-\u9fff]+", "", text)
    return text.casefold()


def _normalize_match_text(value: str | None) -> str:
    return normalize_metadata_match_text(value)


def _merge_metadata(existing: TrackMetadata, scraped: TrackMetadata) -> TrackMetadata:
    return TrackMetadata(
        title=scraped.title or existing.title,
        artist=scraped.artist or existing.artist,
        album=scraped.album or existing.album,
        year=scraped.year or existing.year,
        track_number=scraped.track_number or existing.track_number,
        lyrics=scraped.lyrics or existing.lyrics,
        cover_url=scraped.cover_url or existing.cover_url,
        extra={**existing.extra, **scraped.extra},
    )


def _metadata_fields_union(
    left: tuple[RequiredMetadata, ...],
    right: tuple[RequiredMetadata, ...],
) -> tuple[RequiredMetadata, ...]:
    values: list[RequiredMetadata] = []
    for field in (*left, *right):
        if field not in values:
            values.append(field)
    return tuple(values)


def _missing_metadata_fields(
    metadata: TrackMetadata,
    fields: tuple[RequiredMetadata, ...],
) -> tuple[RequiredMetadata, ...]:
    return tuple(field for field in fields if not _metadata_has_value(metadata, field))


def _filled_metadata_fields(
    before: TrackMetadata,
    after: TrackMetadata,
    fields: tuple[RequiredMetadata, ...],
) -> tuple[RequiredMetadata, ...]:
    return tuple(
        field
        for field in fields
        if not _metadata_has_value(before, field) and _metadata_has_value(after, field)
    )


def _metadata_has_value(metadata: TrackMetadata, field: RequiredMetadata) -> bool:
    value = getattr(metadata, field)
    return isinstance(value, str) and bool(value.strip())


def _optional_path(value: object) -> Path | None:
    text = str(value or "").strip()
    if not text:
        return None
    return Path(text).expanduser().resolve()


def _required_metadata(value: object) -> tuple[RequiredMetadata, ...]:
    if not isinstance(value, list):
        return ()
    allowed = {"album", "artist", "lyrics"}
    return tuple(item for item in value if item in allowed)


def _first_tag(value: object) -> str | None:
    if isinstance(value, (list, tuple)) and value:
        value = value[0]
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def _parse_year(value: str | None) -> int | None:
    if not value:
        return None
    match = re.search(r"\d{4}", value)
    return int(match.group(0)) if match else None


def _parse_track_number(value: str | None) -> int | None:
    if not value:
        return None
    try:
        return int(value.split("/", 1)[0])
    except ValueError:
        return None


def _safe_path_part(value: str) -> str:
    cleaned = re.sub(r'[<>:"/\\|?*\x00-\x1f]+', " ", value)
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" .")
    return cleaned or "Unknown"


def _unique_path(path: Path, *, current: Path | None = None) -> Path:
    if current is not None and path == current:
        return path
    if not path.exists():
        return path
    stem = path.stem
    suffix = path.suffix
    parent = path.parent
    index = 2
    while True:
        candidate = parent / f"{stem} ({index}){suffix}"
        if current is not None and candidate == current:
            return candidate
        if not candidate.exists():
            return candidate
        index += 1
