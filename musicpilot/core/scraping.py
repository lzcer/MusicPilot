from __future__ import annotations

import asyncio
import logging
import os
import re
import shutil
import unicodedata
from collections.abc import AsyncIterator, Awaitable, Callable, Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Literal
from weakref import WeakValueDictionary

from opencc import OpenCC

from musicpilot.core.artist import ArtistService, split_artist_credit
from musicpilot.core.metadata import MetadataCascade
from musicpilot.core.track_variants import (
    TrackVariantSignature,
    build_track_variant_signature,
    strong_variants_match,
    variant_sort_score,
)
from musicpilot.ports.metadata import TrackMetadata
from musicpilot.ports.tag_writer import TagWriter

logger = logging.getLogger("musicpilot.metadata.scraping")

_t2s = OpenCC("t2s")  # Traditional → Simplified

ScrapingMode = Literal["source", "mapped", "copy"]
RequiredMetadata = Literal["album", "artist", "lyrics"]
ClassifyBy = Literal["artist", "album", "artist_album"]
DuplicateHandling = Literal["ignore", "overwrite", "keep_largest"]
PathOperationCause = Literal[
    "already_mapped",
    "hardlink_created",
    "copy_requested",
    "hardlink_failed",
]

_INVALID_METADATA_TEXT_KEYS = frozenset(
    {
        "unknown",
        "unknownartist",
        "unknownalbum",
        "unknow",
        "unspecified",
        "none",
        "null",
        "na",
        "undefined",
        "未知",
        "未知歌手",
        "未知艺术家",
        "未知专辑",
        "未分类",
        "未命名",
        "无",
        "kuwo",
        "kuwomusic",
        "酷我",
        "酷我音乐",
        "kugou",
        "kugoumusic",
        "酷狗",
        "酷狗音乐",
        "qmusic",
        "qqmusic",
        "qq音乐",
        "netease",
        "neteasecloudmusic",
        "网易云",
        "网易云音乐",
        "migu",
        "咪咕",
        "咪咕音乐",
    }
)

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

_ALBUM_COVER_EXTENSION_PRIORITY = {
    ".jpg": 0,
    ".jpeg": 1,
    ".png": 2,
    ".webp": 3,
    ".gif": 4,
}
_ALBUM_COVER_STEM_PRIORITY = {
    "folder": 2,
    "front": 3,
    "album": 4,
    "artwork": 5,
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


class ArtistDirectoryResolutionError(RuntimeError):
    pass


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
    track_version_control: bool = False


@dataclass(frozen=True, slots=True)
class LibraryTrackSnapshot:
    title: str
    artist: str | None = None
    album: str | None = None
    size: int | None = None
    path: str | None = None


@dataclass(frozen=True, slots=True)
class _DuplicateMatch:
    metadata: TrackMetadata
    track: LibraryTrackSnapshot


@dataclass(frozen=True, slots=True)
class ScrapingFileResult:
    source_path: Path
    library_path: Path | None
    metadata: TrackMetadata
    status: Literal["success", "failed", "skipped"]
    operation_type: ScrapingMode
    operation_reason: str | None = None
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


ScrapingFileOutcome = tuple[ScrapingFileResult, int, int, int]
LibrarySnapshotLoader = Callable[
    [],
    Awaitable[
        tuple[
            tuple[LibraryTrackSnapshot, ...],
            tuple[LibraryTrackSnapshot, ...],
        ]
    ],
]
TransferRunner = Callable[
    [Path, Callable[[], Awaitable[ScrapingFileOutcome]]],
    Awaitable[ScrapingFileOutcome],
]


@dataclass(frozen=True, slots=True)
class ContextualMetadata:
    metadata: TrackMetadata
    verify_identity: bool = True
    preserve_artist_album: bool = True


@dataclass(frozen=True, slots=True)
class _OperationReasonContext:
    configured_mode: ScrapingMode
    manual: bool = False
    missing_before: tuple[RequiredMetadata, ...] = ()
    metadata_gain: tuple[RequiredMetadata, ...] = ()
    writes_tags: bool = False
    path_cause: PathOperationCause | None = None
    completed: bool = False


@dataclass(frozen=True, slots=True)
class _PathOperationResult:
    path: Path
    operation_type: ScrapingMode
    overwritten_existing: bool = False
    cause: PathOperationCause | None = None


@dataclass(frozen=True, slots=True)
class _MatchScore:
    title: int = 0
    artist: int = 0
    album: int = 0

    @property
    def total(self) -> int:
        return self.title + self.artist + self.album


@dataclass(frozen=True, slots=True)
class _CandidateScore:
    base: _MatchScore
    variant: int
    collaboration: int
    variants_match: bool
    collaboration_matches: bool

    @property
    def ranking_total(self) -> int:
        return self.base.total + self.variant + self.collaboration


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
        self._album_cover_locks: WeakValueDictionary[str, asyncio.Lock] = WeakValueDictionary()

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
        contextual_metadata: dict[Path, ContextualMetadata] | None = None,
        on_file_result: Callable[[ScrapingFileResult], Awaitable[None]] | None = None,
        library_snapshot_loader: LibrarySnapshotLoader | None = None,
        transfer_runner: TransferRunner | None = None,
        preload_metadata: bool = True,
        metadata_lookup_completed_files: set[Path] | None = None,
        inferred_metadata: dict[Path, TrackMetadata] | None = None,
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
        dir_inferred = dict(inferred_metadata or {})
        missing_inferred_files = [item for item in audio_files if item not in dir_inferred]
        if missing_inferred_files:
            dir_inferred.update(
                await asyncio.to_thread(_infer_batch_metadata, missing_inferred_files)
            )

        candidate_cache = dict(cached_metadata or {})
        lookup_completed_paths = set(metadata_lookup_completed_files or set())
        if preload_metadata:
            lookup_completed_paths.update(
                await self._preload_metadata_candidates(
                    audio_files,
                    config,
                    dir_inferred=dir_inferred,
                    cached_metadata=candidate_cache,
                    forced_metadata=forced_metadata or {},
                    contextual_metadata=contextual_metadata or {},
                )
            )

        for source_file in audio_files:
            try:
                async def run_file(
                    source_file: Path = source_file,
                ) -> ScrapingFileOutcome:
                    return await self._process_file(
                        source_file,
                        config,
                        library_tracks,
                        media_history,
                        dir_inferred=dir_inferred,
                        cached_candidates=candidate_cache.get(source_file, ()),
                        forced_metadata=(forced_metadata or {}).get(source_file),
                        contextual_metadata=(contextual_metadata or {}).get(source_file),
                        library_snapshot_loader=library_snapshot_loader,
                        transfer_runner=transfer_runner,
                        metadata_lookup_completed=source_file in lookup_completed_paths,
                    )

                if transfer_runner is not None:
                    result, mapped, updated, moved = await transfer_runner(
                        source_file,
                        run_file,
                    )
                else:
                    result, mapped, updated, moved = await run_file()
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
                    operation_reason=_operation_reason(
                        _OperationReasonContext(configured_mode=config.mode)
                    ),
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

        await self._organize_album_covers(config, tuple(results))

        return ScrapingSummary(
            source_files=len(audio_files),
            mapped_files=mapped_files,
            updated_files=updated_files,
            moved_files=moved_files,
            failed_files=sum(1 for item in results if item.status == "failed"),
            results=tuple(results),
        )

    async def _organize_album_covers(
        self,
        config: ScrapingConfig,
        results: tuple[ScrapingFileResult, ...],
    ) -> None:
        if not config.auto_classify or config.classify_by not in {"album", "artist_album"}:
            return

        source_targets: dict[Path, set[Path]] = {}
        for result in results:
            if result.status != "success" or result.library_path is None:
                continue
            source_targets.setdefault(result.source_path.parent, set()).add(
                result.library_path.parent
            )

        target_sources: dict[Path, set[Path]] = {}
        for source_dir, target_dirs in source_targets.items():
            if len(target_dirs) != 1:
                logger.warning(
                    "Album cover skipped for ambiguous source directory: source=%s, targets=%s",
                    source_dir,
                    sorted(str(item) for item in target_dirs),
                )
                continue
            target_dir = next(iter(target_dirs))
            target_sources.setdefault(target_dir, set()).add(source_dir)

        for target_dir, source_dirs in sorted(
            target_sources.items(),
            key=lambda item: str(item[0]).casefold(),
        ):
            candidates: list[Path] = []
            for source_dir in sorted(source_dirs, key=lambda item: str(item).casefold()):
                try:
                    candidates.extend(await asyncio.to_thread(_album_cover_candidates, source_dir))
                except OSError as exc:
                    logger.warning(
                        "Album cover discovery failed: source=%s, error=%s",
                        source_dir,
                        exc,
                    )
            if not candidates:
                continue

            source_cover = min(candidates, key=_album_cover_sort_key)
            lock_key = _album_cover_lock_key(target_dir)
            lock = self._album_cover_locks.setdefault(lock_key, asyncio.Lock())
            async with lock:
                try:
                    action, output_path, fallback_error = await asyncio.to_thread(
                        _transfer_album_cover,
                        source_cover,
                        target_dir,
                        config,
                    )
                except Exception as exc:
                    logger.warning(
                        "Album cover organization failed: source=%s, target_dir=%s, error=%s",
                        source_cover,
                        target_dir,
                        exc,
                    )
                    continue
                if action == "existing":
                    logger.info(
                        "Album cover skipped because target exists: source=%s, target=%s",
                        source_cover,
                        output_path,
                    )
                elif fallback_error is not None:
                    logger.warning(
                        "Album cover hardlink failed and copied instead: source=%s, "
                        "target=%s, error=%s",
                        source_cover,
                        output_path,
                        fallback_error,
                    )
                else:
                    logger.info(
                        "Album cover organized: source=%s, target=%s, action=%s",
                        source_cover,
                        output_path,
                        action,
                    )

    async def _preload_metadata_candidates(
        self,
        audio_files: list[Path],
        config: ScrapingConfig,
        *,
        dir_inferred: dict[Path, TrackMetadata],
        cached_metadata: dict[Path, tuple[TrackMetadata, ...]],
        forced_metadata: dict[Path, TrackMetadata],
        contextual_metadata: dict[Path, ContextualMetadata],
    ) -> set[Path]:
        if not audio_files:
            return set()
        scrape_fields = _metadata_fields_union(
            config.scrape_when_missing,
            config.required_metadata,
        )
        if not scrape_fields:
            return set()

        async def preload_file(
            source_file: Path,
        ) -> tuple[Path, tuple[TrackMetadata, ...], TrackMetadata | None] | None:
            if source_file in forced_metadata:
                return None
            if source_file in contextual_metadata:
                return None
            try:
                return await self._preload_metadata_candidates_for_file(
                    source_file,
                    config,
                    dir_inferred=dir_inferred,
                    cached_candidates=cached_metadata.get(source_file, ()),
                    contextual_metadata=contextual_metadata.get(source_file),
                )
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "Scraping metadata preload failed: source=%s, error=%s",
                    source_file,
                    exc,
                )
                return None

        completed: set[Path] = set()
        tasks = [asyncio.create_task(preload_file(source_file)) for source_file in audio_files]
        for task in asyncio.as_completed(tasks):
            item = await task
            if item is None:
                continue
            source_file, candidates, _selected = item
            cached_metadata[source_file] = candidates
            completed.add(source_file)
        return completed

    async def preload_selected_metadata_for_file(
        self,
        source_file: Path,
        config: ScrapingConfig,
        *,
        inferred_metadata: TrackMetadata | None = None,
    ) -> tuple[TrackMetadata, ...]:
        dir_inferred = (
            {source_file: inferred_metadata}
            if inferred_metadata is not None
            else await asyncio.to_thread(_infer_batch_metadata, [source_file])
        )
        item = await self._preload_metadata_candidates_for_file(
            source_file,
            config,
            dir_inferred=dir_inferred,
            cached_candidates=(),
            contextual_metadata=None,
        )
        if item is None or item[2] is None:
            return ()
        return (item[2],)

    async def _preload_metadata_candidates_for_file(
        self,
        source_file: Path,
        config: ScrapingConfig,
        *,
        dir_inferred: dict[Path, TrackMetadata],
        cached_candidates: tuple[TrackMetadata, ...],
        contextual_metadata: ContextualMetadata | None,
    ) -> tuple[Path, tuple[TrackMetadata, ...], TrackMetadata | None] | None:
        source_metadata = await asyncio.to_thread(read_track_metadata, source_file)
        raw_dir_meta = await self._resolve_filename_artist_title(
            dir_inferred.get(source_file),
            source_file,
        )
        dir_meta = await self._resolve_known_artist_directory(source_metadata, raw_dir_meta)
        match_metadata = _metadata_for_matching(
            source_metadata,
            source_file,
            dir_meta=dir_meta,
        )
        fallback_metadata = _path_only_metadata_for_matching(source_file, raw_dir_meta)
        metadata = _merge_metadata(source_metadata, match_metadata)
        if contextual_metadata is not None:
            metadata = _merge_metadata(metadata, contextual_metadata.metadata)
            match_metadata = _merge_metadata(match_metadata, contextual_metadata.metadata)
            fallback_metadata = contextual_metadata.metadata
            verification_reference = contextual_metadata.metadata
            requires_identity_verification = contextual_metadata.verify_identity
        else:
            requires_identity_verification = _metadata_requires_identity_verification(
                source_metadata,
                match_metadata,
                metadata,
                source_file,
                raw_dir_meta,
            )
            verification_reference = _identity_verification_reference(metadata)
        scrape_fields = _metadata_fields_union(
            config.scrape_when_missing,
            config.required_metadata,
        )
        trigger_fields = _missing_metadata_fields(source_metadata, scrape_fields)
        needs_scrape = bool(trigger_fields)
        if not needs_scrape and not requires_identity_verification:
            return None
        if requires_identity_verification:
            verified = await _select_identity_candidate(
                verification_reference,
                cached_candidates,
                artist_service=self.artist_service,
                track_version_control=config.track_version_control,
                reference_file=source_file,
            )
            enriching = (
                await _select_identity_candidate(
                    verification_reference,
                    cached_candidates,
                    artist_service=self.artist_service,
                    track_version_control=config.track_version_control,
                    reference_file=source_file,
                    required=config.required_metadata,
                    trigger_fields=trigger_fields,
                    require_trigger_gain=True,
                )
                if needs_scrape
                else verified
            )
            candidates = cached_candidates
            if verified is None or (needs_scrape and enriching is None):
                candidates = _merge_metadata_candidates(
                    candidates,
                    await self._search_metadata_candidates(
                        verification_reference,
                        verification_reference,
                        (),
                    ),
                )
                verified = await _select_identity_candidate(
                    verification_reference,
                    candidates,
                    artist_service=self.artist_service,
                    track_version_control=config.track_version_control,
                    reference_file=source_file,
                )
                enriching = (
                    await _select_identity_candidate(
                        verification_reference,
                        candidates,
                        artist_service=self.artist_service,
                        track_version_control=config.track_version_control,
                        reference_file=source_file,
                        required=config.required_metadata,
                        trigger_fields=trigger_fields,
                        require_trigger_gain=True,
                    )
                    if needs_scrape
                    else verified
                )
            return source_file, candidates, enriching or verified
        looked_up = await _select_metadata_candidate(
            match_metadata,
            cached_candidates,
            config.required_metadata,
            artist_service=self.artist_service,
            track_version_control=config.track_version_control,
            reference_file=source_file,
            trigger_fields=trigger_fields,
            require_trigger_gain=needs_scrape,
        )
        candidates = cached_candidates
        if looked_up is None:
            online_candidates = await self._search_metadata_candidates(
                source_metadata,
                match_metadata,
                config.required_metadata,
            )
            candidates = _merge_metadata_candidates(candidates, online_candidates)
            looked_up = await _select_metadata_candidate(
                match_metadata,
                online_candidates,
                config.required_metadata,
                artist_service=self.artist_service,
                track_version_control=config.track_version_control,
                reference_file=source_file,
                trigger_fields=trigger_fields,
                require_trigger_gain=needs_scrape,
            )
        if looked_up is None and not _same_metadata_match_key(
            match_metadata,
            fallback_metadata,
        ):
            fallback_candidates = await self._search_metadata_candidates(
                fallback_metadata,
                fallback_metadata,
                config.required_metadata,
            )
            candidates = _merge_metadata_candidates(candidates, fallback_candidates)
            looked_up = await _select_metadata_candidate(
                fallback_metadata,
                fallback_candidates,
                config.required_metadata,
                artist_service=self.artist_service,
                track_version_control=config.track_version_control,
                reference_file=source_file,
                trigger_fields=trigger_fields,
                require_trigger_gain=needs_scrape,
            )
        return source_file, candidates, looked_up

    async def _process_file(
        self,
        source_file: Path,
        config: ScrapingConfig,
        library_tracks: tuple[LibraryTrackSnapshot, ...],
        media_history: tuple[LibraryTrackSnapshot, ...],
        dir_inferred: dict[Path, TrackMetadata] | None = None,
        cached_candidates: tuple[TrackMetadata, ...] = (),
        forced_metadata: TrackMetadata | None = None,
        contextual_metadata: ContextualMetadata | None = None,
        library_snapshot_loader: LibrarySnapshotLoader | None = None,
        transfer_runner: TransferRunner | None = None,
        metadata_lookup_completed: bool = False,
    ) -> ScrapingFileOutcome:
        working_file = source_file
        mapped_files = 0
        updated_files = 0
        moved_files = 0
        source_metadata = await asyncio.to_thread(read_track_metadata, source_file)
        raw_dir_meta = await self._resolve_filename_artist_title(
            (dir_inferred or {}).get(source_file),
            source_file,
        )
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

        def build_operation_reason(
            *,
            writes_tags: bool = False,
            path_result: _PathOperationResult | None = None,
            completed: bool = False,
        ) -> str:
            return _operation_reason(
                _OperationReasonContext(
                    configured_mode=config.mode,
                    manual=forced_metadata is not None,
                    missing_before=(
                        missing_before if forced_metadata is None else ()
                    ),
                    metadata_gain=metadata_gain,
                    writes_tags=writes_tags,
                    path_cause=path_result.cause if path_result is not None else None,
                    completed=completed,
                )
            )

        requires_identity_verification = False
        verification_reference = match_metadata
        if forced_metadata is None and contextual_metadata is not None:
            metadata = _merge_metadata(metadata, contextual_metadata.metadata)
            match_metadata = _merge_metadata(match_metadata, contextual_metadata.metadata)
            fallback_metadata = contextual_metadata.metadata
            verification_reference = contextual_metadata.metadata
            requires_identity_verification = contextual_metadata.verify_identity
        elif forced_metadata is None:
            requires_identity_verification = _metadata_requires_identity_verification(
                source_metadata,
                match_metadata,
                metadata,
                source_file,
                raw_dir_meta,
            )
            verification_reference = _identity_verification_reference(metadata)
        input_variant_signature = _metadata_variant_signature(
            match_metadata,
            source_file=source_file,
        )
        logger.info(
            "Scraping file input: source=%s, source_metadata=%s, dir_inferred=%s, "
            "match_metadata=%s, fallback_metadata=%s, scrape_fields=%s, "
            "missing_before=%s, cached_candidates=%s, forced_metadata=%s, "
            "contextual_metadata=%s, verify_identity=%s, version=%s, version_evidence=%s",
            source_file,
            _metadata_log_text(source_metadata),
            _metadata_log_text(dir_meta),
            _metadata_log_text(match_metadata),
            _metadata_log_text(fallback_metadata),
            scrape_fields,
            missing_before,
            _metadata_candidates_log_text(cached_candidates),
            _metadata_log_text(forced_metadata),
            _metadata_log_text(
                contextual_metadata.metadata if contextual_metadata is not None else None
            ),
            requires_identity_verification,
            _variant_signature_text(input_variant_signature),
            _variant_evidence_text(input_variant_signature),
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
                        operation_reason=build_operation_reason(),
                        error_message=error_message,
                        stage=candidate_stage,
                        needs_metadata_update=True,
                        candidate_count=candidate_count,
                    ),
                    0,
                    0,
                    0,
                )
        elif requires_identity_verification:
            if metadata_lookup_completed:
                candidates = cached_candidates
                verified = await _select_identity_candidate(
                    verification_reference,
                    candidates,
                    artist_service=self.artist_service,
                    track_version_control=config.track_version_control,
                    reference_file=source_file,
                )
            else:
                _online_verified, online_candidates = await self._verify_metadata_identity(
                    verification_reference,
                    source_file=source_file,
                    track_version_control=config.track_version_control,
                )
                candidates = _merge_metadata_candidates(cached_candidates, online_candidates)
                verified = await _select_identity_candidate(
                    verification_reference,
                    candidates,
                    artist_service=self.artist_service,
                    track_version_control=config.track_version_control,
                    reference_file=source_file,
                )
            candidate_count = len(candidates)
            if verified is None:
                error_message = await _identity_verification_failure_message(
                    verification_reference,
                    candidates,
                    artist_service=self.artist_service,
                    track_version_control=config.track_version_control,
                    reference_file=source_file,
                )
                logger.info(
                    "Scraping file result: source=%s, status=failed, "
                    "stage=identity_verification, metadata=%s, error=%s",
                    source_file,
                    _metadata_log_text(verification_reference),
                    error_message,
                )
                return (
                    ScrapingFileResult(
                        source_path=source_file,
                        library_path=None,
                        metadata=metadata,
                        status="failed",
                        operation_type=config.mode,
                        operation_reason=build_operation_reason(),
                        error_message=error_message,
                        stage="identity_verification",
                        needs_metadata_update=needs_scrape,
                        candidate_count=candidate_count,
                    ),
                    0,
                    0,
                    0,
                )
            if needs_scrape:
                adopted = await _select_identity_candidate(
                    verification_reference,
                    candidates,
                    artist_service=self.artist_service,
                    track_version_control=config.track_version_control,
                    reference_file=source_file,
                    required=config.required_metadata,
                    trigger_fields=missing_before,
                    require_trigger_gain=True,
                )
                logger.info(
                    "Scraping identity candidate adoption: source=%s, "
                    "trigger_fields=%s, verified=%s, adopted=%s, trigger_gain=%s",
                    source_file,
                    missing_before,
                    _metadata_log_text(verified),
                    _metadata_log_text(adopted),
                    _candidate_trigger_gain(adopted, missing_before) if adopted else (),
                )
                if adopted is not None:
                    metadata = _merge_missing_metadata(
                        metadata,
                        adopted,
                        preserve_artist_album=(
                            contextual_metadata.preserve_artist_album
                            if contextual_metadata is not None
                            else False
                        ),
                    )
                missing_required = _missing_metadata_fields(metadata, config.required_metadata)
                if missing_required:
                    error_message = await _candidate_failure_message(
                        verification_reference,
                        config.required_metadata,
                        candidates,
                        artist_service=self.artist_service,
                        track_version_control=config.track_version_control,
                        reference_file=source_file,
                        trigger_fields=missing_before,
                        require_trigger_gain=True,
                    )
                    logger.info(
                        "Scraping file result: source=%s, status=failed, "
                        "stage=identity_verification, metadata=%s, selected=%s, "
                        "missing_required=%s, error=%s",
                        source_file,
                        _metadata_log_text(verification_reference),
                        _metadata_log_text(adopted),
                        missing_required,
                        error_message,
                    )
                    return (
                        ScrapingFileResult(
                            source_path=source_file,
                            library_path=None,
                            metadata=metadata,
                            status="failed",
                            operation_type=config.mode,
                            operation_reason=build_operation_reason(),
                            error_message=error_message,
                            stage="identity_verification",
                            needs_metadata_update=True,
                            candidate_count=candidate_count,
                        ),
                        0,
                        0,
                        0,
                    )
                metadata_gain = _filled_metadata_fields(
                    source_metadata,
                    metadata,
                    missing_before,
                )
        elif needs_scrape:
            candidates = cached_candidates
            looked_up = await _select_metadata_candidate(
                match_metadata,
                cached_candidates,
                config.required_metadata,
                artist_service=self.artist_service,
                track_version_control=config.track_version_control,
                reference_file=source_file,
                trigger_fields=missing_before,
                require_trigger_gain=True,
            )
            logger.info(
                "Scraping cached candidate result: source=%s, trigger_fields=%s, "
                "selected=%s, trigger_gain=%s",
                source_file,
                missing_before,
                _metadata_log_text(looked_up),
                _candidate_trigger_gain(looked_up, missing_before) if looked_up else (),
            )
            if looked_up is None and not metadata_lookup_completed:
                online_candidates = await self._search_metadata_candidates(
                    source_metadata,
                    match_metadata,
                    config.required_metadata,
                )
                candidates = _merge_metadata_candidates(cached_candidates, online_candidates)
                looked_up = await _select_metadata_candidate(
                    match_metadata,
                    online_candidates,
                    config.required_metadata,
                    artist_service=self.artist_service,
                    track_version_control=config.track_version_control,
                    reference_file=source_file,
                    trigger_fields=missing_before,
                    require_trigger_gain=True,
                )
                logger.info(
                    "Scraping online candidate result: source=%s, "
                    "online_candidates=%s, selected=%s",
                    source_file,
                    _metadata_candidates_log_text(online_candidates),
                    _metadata_log_text(looked_up),
                )
            if looked_up is None and fallback_available and not metadata_lookup_completed:
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
                    track_version_control=config.track_version_control,
                    reference_file=source_file,
                    trigger_fields=missing_before,
                    require_trigger_gain=True,
                )
                candidates = _merge_metadata_candidates(candidates, fallback_candidates)
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
                metadata = _merge_missing_metadata(
                    metadata,
                    looked_up,
                )
            missing_required = _missing_metadata_fields(metadata, config.required_metadata)
            version_error = (
                await _version_control_failure_text(
                    candidate_reference,
                    config.required_metadata,
                    candidates,
                    artist_service=self.artist_service,
                    reference_file=source_file,
                )
                if looked_up is None and config.track_version_control
                else None
            )
            if looked_up is None:
                if not missing_required and version_error is None:
                    metadata_gain = _filled_metadata_fields(
                        source_metadata,
                        metadata,
                        missing_before,
                    )
                else:
                    error_message = version_error
                    if error_message is None:
                        error_message = await _candidate_failure_message(
                            candidate_reference,
                            config.required_metadata,
                            candidates,
                            artist_service=self.artist_service,
                            track_version_control=config.track_version_control,
                            reference_file=source_file,
                            trigger_fields=missing_before,
                            require_trigger_gain=True,
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
                            operation_reason=build_operation_reason(),
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
                    track_version_control=config.track_version_control,
                    reference_file=source_file,
                    trigger_fields=missing_before,
                    require_trigger_gain=True,
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
                        operation_reason=build_operation_reason(),
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
        writes_tags = should_write_tags or bool(metadata_gain)
        if tag_writer is None and writes_tags:
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
                    operation_reason=build_operation_reason(writes_tags=writes_tags),
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
                    album_artist=metadata.album_artist,
                    year=metadata.year,
                    track_number=metadata.track_number,
                    lyrics=metadata.lyrics,
                    cover_url=metadata.cover_url,
                    extra=metadata.extra,
                )

        duplicate_match = await _find_duplicate_media(
            _duplicate_metadata_candidates(source_metadata, match_metadata, metadata),
            (*library_tracks, *media_history),
            artist_service=self.artist_service,
            track_version_control=config.track_version_control,
            source_file=source_file,
        )
        duplicate = duplicate_match.track if duplicate_match is not None else None
        overwrite_duplicate = False
        current_size = await asyncio.to_thread(_file_size, source_file)
        if duplicate is not None:
            if config.duplicate_handling == "ignore":
                error_message = _duplicate_skip_message(
                    metadata,
                    duplicate,
                    current_size,
                    config=config,
                    reason="音乐库已存在，重复文件处理为不处理",
                    matched_metadata=duplicate_match.metadata,
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
                        operation_reason=build_operation_reason(),
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
                        config=config,
                        reason=reason,
                        matched_metadata=duplicate_match.metadata,
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
                            operation_reason=build_operation_reason(),
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

        classification_artist = _classification_artist(metadata, config)
        if classification_artist is not None and self.artist_service is not None:
            try:
                classification_artist = await self.artist_service.get_or_create_canonical_name(
                    classification_artist,
                    source="scraping",
                )
            except Exception as exc:
                raise ArtistDirectoryResolutionError(
                    f"歌手权威名查询或创建失败：{classification_artist}：{exc}"
                ) from exc

        overwritten_existing_target = False
        operation_type = config.mode
        path_result: _PathOperationResult | None = None
        if config.mode == "mapped":
            path_result = await asyncio.to_thread(
                _copy_to_mapping,
                source_file,
                config,
                hardlink=not writes_tags,
                overwrite=not _will_classify_or_rename(config),
            )
            working_file = path_result.path
            operation_type = path_result.operation_type
            overwritten_existing_target = path_result.overwritten_existing
            mapped_files += 1
        elif config.mode == "copy":
            path_result = await asyncio.to_thread(
                _copy_to_mapping,
                source_file,
                config,
                hardlink=False,
                overwrite=not _will_classify_or_rename(config),
            )
            working_file = path_result.path
            operation_type = path_result.operation_type
            overwritten_existing_target = path_result.overwritten_existing
            mapped_files += 1

        operation_reason = build_operation_reason(
            writes_tags=writes_tags,
            path_result=path_result,
            completed=True,
        )

        if should_write_tags or metadata_gain:
            assert tag_writer is not None
            await tag_writer.write(working_file, metadata)
            updated_files += 1

        final_result = await asyncio.to_thread(
            _classify_or_rename,
            working_file,
            metadata,
            config,
            classification_artist=classification_artist,
            overwrite=not config.track_version_control or overwrite_duplicate,
        )
        final_file = final_result.path
        overwritten_existing_target = (
            overwritten_existing_target or final_result.overwritten_existing
        )
        if final_file != working_file:
            moved_files += 1
        if overwrite_duplicate and duplicate is not None:
            remark = _duplicate_overwrite_message(
                metadata,
                duplicate,
                current_size,
                config=config,
                matched_metadata=duplicate_match.metadata,
            )
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
                operation_reason=operation_reason,
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
        *,
        track_version_control: bool = False,
        reference_file: Path | None = None,
    ) -> TrackMetadata | None:
        return await _select_metadata_candidate(
            reference,
            candidates,
            required,
            artist_service=self.artist_service,
            track_version_control=track_version_control,
            reference_file=reference_file,
        )

    async def rank_metadata_candidates(
        self,
        reference: TrackMetadata,
        candidates: tuple[TrackMetadata, ...],
        required: tuple[RequiredMetadata, ...] = (),
        *,
        track_version_control: bool = False,
        reference_file: Path | None = None,
    ) -> tuple[TrackMetadata, ...]:
        return await _rank_metadata_candidates(
            reference,
            candidates,
            required,
            artist_service=self.artist_service,
            track_version_control=track_version_control,
            reference_file=reference_file,
        )

    async def metadata_candidate_failure_message(
        self,
        reference: TrackMetadata,
        candidates: tuple[TrackMetadata, ...],
        required: tuple[RequiredMetadata, ...] = (),
        *,
        track_version_control: bool = False,
        reference_file: Path | None = None,
    ) -> str:
        return await _candidate_failure_message(
            reference,
            required,
            candidates,
            artist_service=self.artist_service,
            track_version_control=track_version_control,
            reference_file=reference_file,
        )

    async def _verify_metadata_identity(
        self,
        reference: TrackMetadata,
        *,
        source_file: Path | None = None,
        track_version_control: bool = False,
    ) -> tuple[TrackMetadata | None, tuple[TrackMetadata, ...]]:
        candidates = await self._search_metadata_candidates(reference, reference, ())
        verified = await _select_identity_candidate(
            reference,
            candidates,
            artist_service=self.artist_service,
            track_version_control=track_version_control,
            reference_file=source_file,
        )
        return verified, candidates

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
            for search_title in _metadata_search_titles(title):
                # Search with each alias of the artist
                if self.artist_service is not None and artist:
                    aliases = await self.artist_service.get_aliases(artist)
                    for alias in aliases:
                        query: tuple[str, str | None] = (search_title, alias)
                        if query not in seen_queries:
                            seen_queries.add(query)
                            searches.append(query)
                else:
                    query = (search_title, artist)
                    if query not in seen_queries:
                        seen_queries.add(query)
                        searches.append(query)

        # Also add a pure title search as fallback
        for title in (match_metadata.title, source_metadata.title):
            for search_title in _metadata_search_titles(title):
                query = (search_title, None)
                if query not in seen_queries:
                    seen_queries.add(query)
                    searches.append(query)

        candidates: list[TrackMetadata] = []
        seen: set[tuple[object, ...]] = set()
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
                    key = _metadata_candidate_key(candidate)
                    if key in seen:
                        continue
                    seen.add(key)
                    candidates.append(candidate)
        return tuple(candidates)

    async def _resolve_filename_artist_title(
        self,
        dir_meta: TrackMetadata | None,
        source_file: Path,
    ) -> TrackMetadata | None:
        if self.artist_service is None or dir_meta is None:
            return dir_meta
        parsed = _parse_artist_title(source_file.stem)
        if parsed is None:
            return dir_meta
        assumed_artist, assumed_title = parsed
        artist_known, title_known = await asyncio.gather(
            self.artist_service.has_artist_name(assumed_artist),
            self.artist_service.has_artist_name(assumed_title),
        )
        if artist_known or not title_known:
            return dir_meta
        return TrackMetadata(
            title=assumed_artist,
            artist=assumed_title,
            album=dir_meta.album,
            album_artist=dir_meta.album_artist,
            year=dir_meta.year,
            track_number=dir_meta.track_number,
            lyrics=dir_meta.lyrics,
            cover_url=dir_meta.cover_url,
            extra=dir_meta.extra,
        )

    async def _resolve_known_artist_directory(
        self,
        source_metadata: TrackMetadata,
        dir_meta: TrackMetadata | None,
    ) -> TrackMetadata | None:
        if (
            self.artist_service is None
            or dir_meta is None
            or _metadata_has_value(source_metadata, "artist")
            or dir_meta.artist
            or not dir_meta.album
        ):
            return dir_meta
        if not await self.artist_service.has_artist_name(dir_meta.album):
            return dir_meta
        return TrackMetadata(
            title=dir_meta.title,
            artist=dir_meta.album,
            album=(
                source_metadata.album
                if _metadata_has_value(source_metadata, "album")
                else None
            ),
            album_artist=dir_meta.album_artist,
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
        classify_by=(
            "artist_album"
            if classify_by == "artist_album"
            else "album"
            if classify_by == "album"
            else "artist"
        ),
        duplicate_handling=duplicate_handling,
        track_version_control=bool(scraping.get("track_version_control")),
    )


def read_track_metadata(path: Path) -> TrackMetadata:
    from mutagen import File as MutagenFile

    audio = MutagenFile(path, easy=True)
    title = path.stem
    artist = None
    album = None
    album_artist = None
    year = None
    track_number = None
    lyrics = None
    if audio is not None and audio.tags:
        title = _first_tag(audio.tags.get("title")) or title
        artist = _first_tag(audio.tags.get("artist"))
        album = _first_tag(audio.tags.get("album"))
        album_artist = _first_tag(audio.tags.get("albumartist"))
        year = _parse_year(_first_tag(audio.tags.get("date")))
        track_number = _parse_track_number(_first_tag(audio.tags.get("tracknumber")))
        lyrics = _first_tag(audio.tags.get("lyrics"))
    return TrackMetadata(
        title=title,
        artist=artist,
        album=album,
        album_artist=album_artist,
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


def infer_album_context_metadata(
    source_files: list[Path],
    *,
    artist: str,
    album: str,
) -> dict[Path, ContextualMetadata]:
    files = sorted(source_files, key=lambda path: path.as_posix().casefold())
    segmented = {path: _split_title_segments(path.stem) for path in files}
    common_count = _most_common_segment_count(segmented.values())
    aligned = {
        path: segments
        for path, segments in segmented.items()
        if common_count is not None and len(segments) == common_count
    }
    track_index = _track_number_segment_index(tuple(aligned.values()))
    artist_indexes = _constant_context_segment_indexes(
        tuple(aligned.values()),
        artist,
    )
    album_indexes = _constant_context_segment_indexes(
        tuple(aligned.values()),
        album,
    )
    ignored_indexes = set(artist_indexes) | set(album_indexes)
    if track_index is not None:
        ignored_indexes.add(track_index)

    result: dict[Path, ContextualMetadata] = {}
    for path in files:
        segments = segmented[path]
        if common_count is not None and len(segments) == common_count:
            title_segments = [
                segment for index, segment in enumerate(segments) if index not in ignored_indexes
            ]
            track_number = (
                _parse_track_number(segments[track_index])
                if track_index is not None
                else None
            )
        else:
            title_segments = [_strip_track_prefix(path.stem)]
            track_number = None
        title = _clean_inferred_title(" - ".join(item for item in title_segments if item))
        if not title:
            title = _strip_track_prefix(path.stem) or path.stem
        result[path] = ContextualMetadata(
            metadata=TrackMetadata(
                title=title,
                artist=artist,
                album=album,
                track_number=track_number,
            ),
            verify_identity=True,
            preserve_artist_album=True,
        )
    return result


def _split_title_segments(value: str) -> list[str]:
    segments = [
        segment.strip()
        for segment in re.split(r"\s+(?:-|–|—|\||/|_)\s+", value)
        if segment.strip()
    ]
    return segments or [value.strip()]


def _most_common_segment_count(segment_groups: Iterable[list[str]]) -> int | None:
    counts: dict[int, int] = {}
    for segments in segment_groups:
        counts[len(segments)] = counts.get(len(segments), 0) + 1
    if not counts:
        return None
    count, frequency = max(counts.items(), key=lambda item: item[1])
    return count if frequency >= 2 else None


def _track_number_segment_index(segment_groups: tuple[list[str], ...]) -> int | None:
    if not segment_groups:
        return None
    best_index = None
    best_count = 0
    for index in range(len(segment_groups[0])):
        numbers = [_parse_track_number(segments[index]) for segments in segment_groups]
        valid = [number for number in numbers if number is not None]
        if len(valid) <= best_count:
            continue
        if len(valid) >= max(2, int(len(segment_groups) * 0.8)) and len(set(valid)) > 1:
            best_index = index
            best_count = len(valid)
    return best_index


def _constant_context_segment_indexes(
    segment_groups: tuple[list[str], ...],
    expected: str,
) -> tuple[int, ...]:
    if not segment_groups or not expected:
        return ()
    result: list[int] = []
    expected_key = _normalize_match_text(expected)
    for index in range(len(segment_groups[0])):
        values = [segments[index] for segments in segment_groups]
        keys = {_normalize_match_text(value) for value in values if value}
        if len(keys) == 1 and expected_key in keys:
            result.append(index)
    return tuple(result)


def _parse_track_number(value: str | None) -> int | None:
    if not value:
        return None
    match = re.search(r"(?:cd\s*\d+\s*)?(\d{1,3})", value, flags=re.I)
    if not match:
        return None
    number = int(match.group(1))
    return number if 0 < number < 1000 else None


def _clean_inferred_title(value: str) -> str:
    return re.sub(r"\s+", " ", _strip_track_prefix(value)).strip()


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


def _operation_reason(context: _OperationReasonContext) -> str:
    parts = [
        {
            "source": "配置指定在源目录处理",
            "mapped": "配置指定映射文件",
            "copy": "配置指定复制文件",
        }[context.configured_mode]
    ]
    if context.manual:
        parts.append("使用手动元数据整理")
    elif context.missing_before:
        parts.append(f"因缺少{_metadata_fields_text(context.missing_before)}触发刮削")
        gained = tuple(
            field for field in context.missing_before if field in context.metadata_gain
        )
        remaining = tuple(
            field for field in context.missing_before if field not in context.metadata_gain
        )
        if gained:
            parts.append(f"已补充{_metadata_fields_text(gained)}")
        if remaining:
            prefix = "仍缺少" if gained else "刮削后仍缺少"
            parts.append(f"{prefix}{_metadata_fields_text(remaining)}")

    if not context.completed:
        return "；".join(parts)

    def append_completion(*clauses: str) -> None:
        if not clauses:
            return
        if not context.manual and context.missing_before:
            parts[-1] = f"{parts[-1]}，{clauses[0]}"
            parts.extend(clauses[1:])
        else:
            parts.extend(clauses)

    if context.configured_mode == "source":
        append_completion(
            "已写入源文件" if context.writes_tags else "无需写入标签，已在源目录完成处理"
        )
        return "；".join(parts)

    if context.path_cause == "already_mapped":
        append_completion("无需写入标签，目标文件已映射，无需重复处理")
    elif context.path_cause == "hardlink_created":
        append_completion("无需写入标签，已成功创建硬链接")
    elif context.path_cause == "hardlink_failed":
        append_completion("无需写入标签", "硬链接创建失败，自动改用复制")
    elif context.path_cause == "copy_requested":
        if context.configured_mode == "mapped":
            append_completion(
                "需要写入标签，自动改用复制"
                if context.writes_tags
                else "已复制文件"
            )
        else:
            append_completion(
                "需要写入标签，已复制文件"
                if context.writes_tags
                else "无需写入标签，已复制文件"
            )
    else:
        append_completion("已完成文件处理")
    return "；".join(parts)


def _metadata_fields_text(fields: tuple[RequiredMetadata, ...]) -> str:
    return "、".join(_metadata_field_text(field) for field in fields)


def _metadata_field_text(field: RequiredMetadata) -> str:
    return {
        "album": "专辑",
        "artist": "艺术家",
        "lyrics": "歌词",
    }[field]


def _album_cover_candidates(source_dir: Path) -> tuple[Path, ...]:
    if not source_dir.is_dir():
        return ()
    candidates = [
        path
        for path in source_dir.iterdir()
        if path.is_file() and _album_cover_sort_key_or_none(path) is not None
    ]
    return tuple(sorted(candidates, key=_album_cover_sort_key))


def _album_cover_lock_key(target_dir: Path) -> str:
    return os.path.normcase(os.path.abspath(target_dir))


def _album_cover_sort_key(path: Path) -> tuple[int, int, int, str]:
    key = _album_cover_sort_key_or_none(path)
    if key is None:
        raise ValueError(f"Not an album cover candidate: {path}")
    return key


def _album_cover_sort_key_or_none(path: Path) -> tuple[int, int, int, str] | None:
    extension_priority = _ALBUM_COVER_EXTENSION_PRIORITY.get(path.suffix.casefold())
    if extension_priority is None:
        return None

    stem = path.stem.casefold()
    if stem == "cover":
        stem_priority = 0
        number_priority = 0
    elif stem.startswith("cover_") and stem[6:].isdigit():
        stem_priority = 1
        number_priority = int(stem[6:])
    elif stem in _ALBUM_COVER_STEM_PRIORITY:
        stem_priority = _ALBUM_COVER_STEM_PRIORITY[stem]
        number_priority = 0
    else:
        return None
    return (
        stem_priority,
        number_priority,
        extension_priority,
        str(path).casefold(),
    )


def _existing_album_cover(target_dir: Path) -> Path | None:
    if not target_dir.is_dir():
        return None
    covers = sorted(
        (
            path
            for path in target_dir.iterdir()
            if path.is_file()
            and path.stem.casefold() == "cover"
            and path.suffix.casefold() in _ALBUM_COVER_EXTENSION_PRIORITY
        ),
        key=lambda path: str(path).casefold(),
    )
    return covers[0] if covers else None


def _transfer_album_cover(
    source_path: Path,
    target_dir: Path,
    config: ScrapingConfig,
) -> tuple[str, Path, OSError | None]:
    existing = _existing_album_cover(target_dir)
    if existing is not None:
        return "existing", existing, None

    target_dir.mkdir(parents=True, exist_ok=True)
    target_path = target_dir / f"Cover{source_path.suffix}"
    if config.mode == "mapped":
        try:
            os.link(source_path, target_path)
            return "hardlink", target_path, None
        except FileExistsError:
            return "existing", target_path, None
        except OSError as exc:
            if not _copy_file_without_overwrite(source_path, target_path):
                return "existing", target_path, None
            return "copy", target_path, exc

    if not _copy_file_without_overwrite(source_path, target_path):
        return "existing", target_path, None
    if config.mode == "source":
        source_path.unlink()
        _remove_empty_parents(source_path.parent, config)
        return "move", target_path, None
    return "copy", target_path, None


def _copy_file_without_overwrite(source_path: Path, target_path: Path) -> bool:
    target_created = False
    try:
        with source_path.open("rb") as source, target_path.open("xb") as target:
            target_created = True
            shutil.copyfileobj(source, target)
        shutil.copystat(source_path, target_path)
    except FileExistsError:
        return False
    except Exception:
        if target_created:
            target_path.unlink(missing_ok=True)
        raise
    return True


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
    elif hardlink and _same_existing_file(source_file, target):
        return _PathOperationResult(
            target,
            operation_type="mapped",
            cause="already_mapped",
        )
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
                cause="hardlink_created",
            )
        except OSError:
            hardlink_failed = True
    else:
        hardlink_failed = False
    if overwritten_existing:
        _remove_existing_target(target)
    shutil.copy2(source_file, target)
    return _PathOperationResult(
        target,
        operation_type="copy",
        overwritten_existing=overwritten_existing,
        cause="hardlink_failed" if hardlink_failed else "copy_requested",
    )


def _classify_or_rename(
    path: Path,
    metadata: TrackMetadata,
    config: ScrapingConfig,
    *,
    classification_artist: str | None = None,
    overwrite: bool,
) -> _PathOperationResult:
    target_dir = path.parent
    if config.auto_classify:
        primary_artist = _primary_artist(metadata.artist)
        groups: tuple[str | None, ...]
        if config.classify_by == "artist_album":
            groups = (
                classification_artist or metadata.album_artist or primary_artist,
                metadata.album or "未知专辑",
            )
        else:
            groups = (
                (
                    classification_artist or primary_artist
                    if config.classify_by == "artist"
                    else metadata.album
                ),
            )
        if all(groups):
            classify_root = (
                config.mapped_directory
                if config.mode in {"mapped", "copy"}
                else config.source_directory
            )
            target_dir = classify_root or path.parent
            for group in groups:
                if group is not None:
                    target_dir /= _safe_path_part(group)
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


def _classification_artist(
    metadata: TrackMetadata,
    config: ScrapingConfig,
) -> str | None:
    if not config.auto_classify:
        return None
    if config.classify_by == "artist":
        return _primary_artist(metadata.artist)
    if config.classify_by == "artist_album":
        return _primary_artist(metadata.album_artist or metadata.artist)
    return None


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
        root = (
            config.mapped_directory
            if config.mode in {"mapped", "copy"}
            else config.source_directory
        )
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
    seen: set[tuple[object, ...]] = set()
    for metadata in (source_metadata, match_metadata, scraped_metadata):
        key = _metadata_candidate_key(metadata)
        if not key[0] or key in seen:
            continue
        seen.add(key)
        candidates.append(metadata)
    return tuple(candidates)


def _merge_metadata_candidates(
    *candidate_groups: tuple[TrackMetadata, ...],
) -> tuple[TrackMetadata, ...]:
    candidates: list[TrackMetadata] = []
    seen: set[tuple[object, ...]] = set()
    for group in candidate_groups:
        for metadata in group:
            key = _metadata_candidate_key(metadata)
            if key in seen:
                continue
            seen.add(key)
            candidates.append(metadata)
    return tuple(candidates)


async def _find_duplicate_media(
    candidates: tuple[TrackMetadata, ...],
    tracks: tuple[LibraryTrackSnapshot, ...],
    *,
    artist_service: ArtistService | None = None,
    track_version_control: bool = False,
    source_file: Path | None = None,
) -> _DuplicateMatch | None:
    best: _DuplicateMatch | None = None
    best_score = 0
    for metadata in candidates:
        metadata_signature = _metadata_variant_signature(metadata, source_file=source_file)
        title = (
            metadata_signature.normalized_base_title
            if track_version_control
            else normalize_metadata_match_text(metadata.title)
        )
        artist = normalize_metadata_match_text(metadata.artist)
        album = normalize_metadata_match_text(metadata.album)
        if not title:
            continue
        for track in tracks:
            track_metadata = TrackMetadata(
                title=track.title,
                artist=track.artist,
                album=track.album,
            )
            track_path = Path(track.path) if track.path else None
            track_signature = _metadata_variant_signature(
                track_metadata,
                source_file=track_path,
            )
            track_title = (
                track_signature.normalized_base_title
                if track_version_control
                else normalize_metadata_match_text(track.title)
            )
            if track_title != title:
                continue
            if track_version_control and (
                not strong_variants_match(metadata_signature, track_signature)
                or not await _collaboration_signatures_match(
                    metadata_signature,
                    track_signature,
                    artist_service=artist_service,
                )
            ):
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
                best = _DuplicateMatch(metadata=metadata, track=track)
                best_score = score
    return best


def _library_track_path(track: LibraryTrackSnapshot, config: ScrapingConfig) -> Path | None:
    if not track.path:
        return None
    path = Path(track.path)
    candidates = (path,) if path.is_absolute() else tuple(
        root / path
        for root in (config.mapped_directory, config.source_directory)
        if root is not None
    )
    return next((candidate for candidate in candidates if candidate.is_file()), None)


def _duplicate_skip_message(
    metadata: TrackMetadata,
    track: LibraryTrackSnapshot,
    current_size: int,
    *,
    config: ScrapingConfig,
    reason: str,
    matched_metadata: TrackMetadata | None = None,
) -> str:
    existing_path = _library_track_path(track, config)
    path_text = f"，已存在路径={existing_path}" if existing_path is not None else ""
    match_text = _duplicate_match_metadata_text(metadata, matched_metadata)
    return (
        f"已跳过：{reason}。"
        f"识别={metadata.title}/{metadata.artist or '-'}，"
        f"{match_text}"
        f"当前大小={_format_size(current_size)}，"
        f"音乐库大小={_format_size(track.size)}"
        f"{path_text}"
    )


def _duplicate_overwrite_message(
    metadata: TrackMetadata,
    track: LibraryTrackSnapshot,
    current_size: int,
    *,
    config: ScrapingConfig,
    matched_metadata: TrackMetadata | None = None,
) -> str:
    existing_path = _library_track_path(track, config)
    path_text = f"，原路径={existing_path}" if existing_path is not None else ""
    match_text = _duplicate_match_metadata_text(metadata, matched_metadata)
    return (
        "覆盖完成：音乐库中已存在匹配媒体。"
        f"识别={metadata.title}/{metadata.artist or '-'}，"
        f"{match_text}"
        f"当前大小={_format_size(current_size)}，"
        f"音乐库大小={_format_size(track.size)}"
        f"{path_text}"
    )


def _duplicate_match_metadata_text(
    metadata: TrackMetadata,
    matched_metadata: TrackMetadata | None,
) -> str:
    if matched_metadata is None:
        return ""
    if (
        _normalize_match_text(metadata.title) == _normalize_match_text(matched_metadata.title)
        and _normalize_match_text(metadata.artist)
        == _normalize_match_text(matched_metadata.artist)
    ):
        return ""
    return f"匹配依据={matched_metadata.title}/{matched_metadata.artist or '-'}，"


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
        f"classify_by={config.classify_by!r}, duplicate_handling={config.duplicate_handling!r}, "
        f"track_version_control={config.track_version_control}"
        "}"
    )


def _metadata_log_text(metadata: TrackMetadata | None) -> str:
    if metadata is None:
        return "None"
    signature = _metadata_variant_signature(metadata)
    return (
        "{"
        f"title={metadata.title!r}, artist={metadata.artist!r}, album={metadata.album!r}, "
        f"year={metadata.year!r}, track_number={metadata.track_number!r}, "
        f"lyrics={bool(metadata.lyrics)}, cover_url={metadata.cover_url!r}, "
        f"version={_variant_signature_text(signature)!r}, "
        f"version_evidence={_variant_evidence_text(signature)!r}, "
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
    if _metadata_has_value(metadata, "artist"):
        if _metadata_has_value(metadata, "album"):
            return metadata
        return TrackMetadata(
            title=metadata.title,
            artist=metadata.artist,
            album=dir_meta.album if dir_meta else None,
            album_artist=metadata.album_artist,
            year=metadata.year,
            track_number=metadata.track_number,
            lyrics=metadata.lyrics,
            cover_url=metadata.cover_url,
            extra=metadata.extra,
        )

    # Try filename parsing first
    parsed = _parse_artist_title(metadata.title) or _parse_artist_title(source_file.stem)
    if parsed is not None:
        artist, title = parsed
        if (
            dir_meta is not None
            and dir_meta.artist
            and dir_meta.title
            and _normalize_match_text(dir_meta.artist) == _normalize_match_text(title)
            and _normalize_match_text(dir_meta.title) == _normalize_match_text(artist)
        ):
            artist, title = dir_meta.artist, dir_meta.title
        album = (
            metadata.album
            if _metadata_has_value(metadata, "album")
            else dir_meta.album
            if dir_meta
            else None
        )
        return TrackMetadata(
            title=title,
            artist=artist,
            album=album,
            album_artist=metadata.album_artist or (dir_meta.album_artist if dir_meta else None),
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
            album=dir_meta.album
            or (metadata.album if _metadata_has_value(metadata, "album") else None),
            album_artist=metadata.album_artist or dir_meta.album_artist,
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


def _metadata_requires_identity_verification(
    source_metadata: TrackMetadata,
    match_metadata: TrackMetadata,
    metadata: TrackMetadata,
    source_file: Path,
    dir_meta: TrackMetadata | None,
) -> bool:
    reference = _identity_verification_reference(metadata)
    if not reference.title or not reference.artist:
        return False
    if (
        dir_meta is not None
        and not _metadata_has_value(source_metadata, "artist")
        and match_metadata.artist
    ):
        return True
    if _title_looks_noisy(source_metadata.title):
        return True
    if _album_looks_noisy(source_metadata.album):
        return True
    if source_metadata.title and source_file.stem:
        stem_title = _strip_track_prefix(source_file.stem)
        if (
            _normalize_match_text(source_metadata.title)
            == _normalize_match_text(source_file.stem)
            and _parse_artist_title(stem_title) is not None
        ):
            return True
    return False


def _identity_verification_reference(metadata: TrackMetadata) -> TrackMetadata:
    original_title = (metadata.title or "").strip()
    title = _strip_track_prefix(original_title)
    artist = metadata.artist
    parsed = _parse_artist_title(title) if title != original_title else None
    if parsed is not None:
        artist, title = parsed
    return TrackMetadata(
        title=title or metadata.title,
        artist=artist,
        album=metadata.album,
        album_artist=metadata.album_artist,
        year=metadata.year,
        track_number=metadata.track_number,
        lyrics=metadata.lyrics,
        cover_url=metadata.cover_url,
        extra=metadata.extra,
    )


def _title_looks_noisy(title: str | None) -> bool:
    if not title:
        return False
    stripped = _strip_track_prefix(title)
    return stripped != title.strip()


def _album_looks_noisy(album: str | None) -> bool:
    if not album:
        return False
    normalized = album.casefold()
    return bool(
        ".专辑" in normalized
        or "[专辑" in normalized
        or _ALBUM_TRAILING_NOISE_RE.search(album)
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


def _metadata_search_titles(title: str | None) -> tuple[str, ...]:
    values: list[str] = []
    for item in (
        title,
        build_track_variant_signature(title=title).base_title,
    ):
        search_title = _metadata_search_title(item)
        if search_title and search_title not in values:
            values.append(search_title)
    return tuple(values)


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
    track_version_control: bool = False,
    reference_file: Path | None = None,
    trigger_fields: tuple[RequiredMetadata, ...] = (),
    require_trigger_gain: bool = False,
) -> TrackMetadata | None:
    """Select the best metadata candidate using scoring.

    Scores all candidates by title/artist/album match against the existing
    metadata. Returns the highest-scoring candidate that fills required
    fields, if its score meets the minimum threshold.
    """
    ranked = await _rank_metadata_candidates(
        existing,
        candidates,
        required,
        artist_service=artist_service,
        track_version_control=track_version_control,
        reference_file=reference_file,
        trigger_fields=trigger_fields,
        require_trigger_gain=require_trigger_gain,
    )
    return ranked[0] if ranked else None


async def _rank_metadata_candidates(
    existing: TrackMetadata,
    candidates: tuple[TrackMetadata, ...],
    required: tuple[RequiredMetadata, ...],
    *,
    artist_service: ArtistService | None = None,
    track_version_control: bool = False,
    reference_file: Path | None = None,
    trigger_fields: tuple[RequiredMetadata, ...] = (),
    require_trigger_gain: bool = False,
    identity_verification: bool = False,
) -> tuple[TrackMetadata, ...]:
    scored: list[tuple[_CandidateScore, int, TrackMetadata]] = []
    for candidate in candidates:
        if not _candidate_fills_required(existing, candidate, required):
            continue
        trigger_gain = _candidate_trigger_gain(candidate, trigger_fields)
        if require_trigger_gain and not trigger_gain:
            continue
        score = await _candidate_match_score(
            existing,
            candidate,
            artist_service=artist_service,
            reference_file=reference_file,
        )
        if identity_verification:
            if not _identity_score_is_trusted(existing, candidate, score.base):
                continue
        elif score.base.total < _MATCH_SCORE_THRESHOLD:
            continue
        if track_version_control and (
            not score.variants_match or not score.collaboration_matches
        ):
            continue
        scored.append((score, len(trigger_gain), candidate))

    scored.sort(
        key=lambda item: (
            item[0].ranking_total,
            item[1],
            item[0].base.total,
            item[0].base.title,
            item[0].base.artist,
        ),
        reverse=True,
    )
    return tuple(item[2] for item in scored)


async def _select_identity_candidate(
    reference: TrackMetadata,
    candidates: tuple[TrackMetadata, ...],
    *,
    artist_service: ArtistService | None = None,
    track_version_control: bool = False,
    reference_file: Path | None = None,
    required: tuple[RequiredMetadata, ...] = (),
    trigger_fields: tuple[RequiredMetadata, ...] = (),
    require_trigger_gain: bool = False,
) -> TrackMetadata | None:
    ranked = await _rank_metadata_candidates(
        reference,
        candidates,
        required,
        artist_service=artist_service,
        track_version_control=track_version_control,
        reference_file=reference_file,
        trigger_fields=trigger_fields,
        require_trigger_gain=require_trigger_gain,
        identity_verification=True,
    )
    return ranked[0] if ranked else None


def _identity_score_is_trusted(
    reference: TrackMetadata,
    candidate: TrackMetadata,
    score: _MatchScore,
) -> bool:
    if not reference.title or score.title < 2:
        return False
    if reference.artist and score.artist <= 0:
        return False
    return True


def _candidate_fills_required(
    existing: TrackMetadata,
    candidate: TrackMetadata,
    required: tuple[RequiredMetadata, ...],
) -> bool:
    for field in required:
        if _metadata_has_value(existing, field):
            continue
        if not _metadata_has_value(candidate, field):
            return False
    return True


def _candidate_trigger_gain(
    candidate: TrackMetadata,
    trigger_fields: tuple[RequiredMetadata, ...],
) -> tuple[RequiredMetadata, ...]:
    return tuple(field for field in trigger_fields if _metadata_has_value(candidate, field))


def _candidate_has_conflicting_album(existing: TrackMetadata, candidate: TrackMetadata) -> bool:
    return bool(
        _metadata_has_value(existing, "album")
        and _metadata_has_value(candidate, "album")
        and _match_score(existing.album, candidate.album) == 0
    )


async def _candidate_failure_message(
    metadata: TrackMetadata,
    required: tuple[RequiredMetadata, ...],
    candidates: tuple[TrackMetadata, ...],
    *,
    artist_service: ArtistService | None = None,
    track_version_control: bool = False,
    reference_file: Path | None = None,
    trigger_fields: tuple[RequiredMetadata, ...] = (),
    require_trigger_gain: bool = False,
) -> str:
    if track_version_control:
        version_failure = await _version_control_failure_text(
            metadata,
            required,
            candidates,
            artist_service=artist_service,
            reference_file=reference_file,
        )
        if version_failure is not None:
            return version_failure
    required_text = ", ".join(required) if required else "none"
    score_text = await _best_candidate_score_text(
        metadata,
        candidates,
        artist_service=artist_service,
        reference_file=reference_file,
    )
    diagnostics_text = await _candidate_diagnostics_text(
        metadata,
        required,
        candidates,
        artist_service=artist_service,
        track_version_control=track_version_control,
        reference_file=reference_file,
        trigger_fields=trigger_fields,
        require_trigger_gain=require_trigger_gain,
    )
    return (
        "未找到可信的刮削候选。"
        f"title={metadata.title!r}, artist={metadata.artist!r}, "
        f"required={required_text}, candidates={len(candidates)}"
        f"{score_text}{diagnostics_text}"
    )


async def _identity_verification_failure_message(
    metadata: TrackMetadata,
    candidates: tuple[TrackMetadata, ...],
    *,
    artist_service: ArtistService | None = None,
    track_version_control: bool = False,
    reference_file: Path | None = None,
) -> str:
    if track_version_control:
        version_failure = await _version_control_failure_text(
            metadata,
            (),
            candidates,
            artist_service=artist_service,
            reference_file=reference_file,
            identity_verification=True,
        )
        if version_failure is not None:
            return version_failure
    score_text = await _best_candidate_score_text(
        metadata,
        candidates,
        artist_service=artist_service,
        reference_file=reference_file,
    )
    diagnostics_text = await _candidate_diagnostics_text(
        metadata,
        (),
        candidates,
        artist_service=artist_service,
        track_version_control=track_version_control,
        reference_file=reference_file,
    )
    return (
        "本地推断元数据未通过联网校验。"
        f"title={metadata.title!r}, artist={metadata.artist!r}, "
        f"album={metadata.album!r}, candidates={len(candidates)}"
        f"{score_text}{diagnostics_text}"
    )


async def _version_control_failure_text(
    metadata: TrackMetadata,
    required: tuple[RequiredMetadata, ...],
    candidates: tuple[TrackMetadata, ...],
    *,
    artist_service: ArtistService | None,
    reference_file: Path | None,
    identity_verification: bool = False,
) -> str | None:
    rejected: list[tuple[_CandidateScore, TrackMetadata]] = []
    for candidate in candidates:
        if not _candidate_fills_required(metadata, candidate, required):
            continue
        score = await _candidate_match_score(
            metadata,
            candidate,
            artist_service=artist_service,
            reference_file=reference_file,
        )
        trusted = (
            _identity_score_is_trusted(metadata, candidate, score.base)
            if identity_verification
            else score.base.total >= _MATCH_SCORE_THRESHOLD
        )
        if not trusted:
            continue
        if score.variants_match and score.collaboration_matches:
            return None
        rejected.append((score, candidate))
    if not rejected:
        return None
    rejected.sort(key=lambda item: item[0].base.total, reverse=True)
    best_score, best_candidate = rejected[0]
    reference_signature = _metadata_variant_signature(metadata, source_file=reference_file)
    candidate_signature = _metadata_variant_signature(best_candidate)
    if all(score.variants_match for score, _candidate in rejected):
        return (
            "未找到合作艺人一致的刮削候选。"
            f"参考版本={_variant_signature_text(reference_signature)}，"
            f"参考证据={_variant_evidence_text(reference_signature)}，"
            f"最佳候选={best_candidate.title!r}/{best_candidate.artist!r}，"
            f"候选版本={_variant_signature_text(candidate_signature)}，"
            f"已排除候选={len(rejected)}。"
        )
    return (
        "未找到版本一致的刮削候选。"
        f"参考版本={_variant_signature_text(reference_signature)}，"
        f"参考证据={_variant_evidence_text(reference_signature)}，"
        f"最佳候选={best_candidate.title!r}/{best_candidate.artist!r}/"
        f"{best_candidate.album!r}，"
        f"候选版本={_variant_signature_text(candidate_signature)}，"
        f"已排除候选={len(rejected)}，base_score={best_score.base.total}。"
    )


async def _best_candidate_score_text(
    metadata: TrackMetadata,
    candidates: tuple[TrackMetadata, ...],
    *,
    artist_service: ArtistService | None = None,
    reference_file: Path | None = None,
) -> str:
    best_candidate = None
    best_score: _CandidateScore | None = None
    for candidate in candidates:
        score = await _candidate_match_score(
            metadata,
            candidate,
            artist_service=artist_service,
            reference_file=reference_file,
        )
        if best_score is None or score.ranking_total > best_score.ranking_total:
            best_candidate = candidate
            best_score = score
    if best_candidate is None or best_score is None:
        return ""
    candidate_signature = _metadata_variant_signature(best_candidate)
    return (
        f", best={best_candidate.title!r}/{best_candidate.artist!r}/"
        f"{best_candidate.album!r}, score={best_score.ranking_total}"
        f"(base={best_score.base.total}, title={best_score.base.title}, "
        f"artist={best_score.base.artist}, album={best_score.base.album}, "
        f"variant={best_score.variant}, collaboration={best_score.collaboration}, "
        f"candidate_version={_variant_signature_text(candidate_signature)}, "
        f"candidate_evidence={_variant_evidence_text(candidate_signature)})"
    )


async def _candidate_diagnostics_text(
    metadata: TrackMetadata,
    required: tuple[RequiredMetadata, ...],
    candidates: tuple[TrackMetadata, ...],
    *,
    artist_service: ArtistService | None = None,
    track_version_control: bool = False,
    reference_file: Path | None = None,
    trigger_fields: tuple[RequiredMetadata, ...] = (),
    require_trigger_gain: bool = False,
) -> str:
    if not candidates:
        return ""
    items: list[str] = []
    for index, candidate in enumerate(candidates[:5], start=1):
        score = await _candidate_match_score(
            metadata,
            candidate,
            artist_service=artist_service,
            reference_file=reference_file,
        )
        missing = _candidate_missing_required(metadata, candidate, required)
        trigger_gain = _candidate_trigger_gain(candidate, trigger_fields)
        album_mismatch = _candidate_has_conflicting_album(metadata, candidate)
        reasons: list[str] = []
        if missing:
            reasons.append(f"missing={','.join(missing)}")
        if album_mismatch:
            reasons.append("album_mismatch")
        if require_trigger_gain and not trigger_gain:
            reasons.append("no_trigger_gain")
        if score.base.total < _MATCH_SCORE_THRESHOLD:
            reasons.append(f"score_below_threshold={_MATCH_SCORE_THRESHOLD}")
        if track_version_control and not score.variants_match:
            reasons.append("version_mismatch")
        if track_version_control and not score.collaboration_matches:
            reasons.append("collaboration_mismatch")
        reason_text = ";".join(reasons) if reasons else "eligible"
        candidate_signature = _metadata_variant_signature(candidate)
        items.append(
            f"#{index}:{candidate.title!r}/{candidate.artist!r}/{candidate.album!r} "
            f"score={score.ranking_total}(base={score.base.total},title={score.base.title},"
            f"artist={score.base.artist},album={score.base.album},variant={score.variant},"
            f"collaboration={score.collaboration},trigger_gain={trigger_gain},"
            f"version={_variant_signature_text(candidate_signature)},"
            f"evidence={_variant_evidence_text(candidate_signature)}) {reason_text}"
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
        if _metadata_has_value(existing, field):
            continue
        if not _metadata_has_value(candidate, field):
            missing.append(field)
    return tuple(missing)


async def _candidate_match_score(
    existing: TrackMetadata,
    candidate: TrackMetadata,
    *,
    artist_service: ArtistService | None = None,
    reference_file: Path | None = None,
) -> _CandidateScore:
    base_score = await _metadata_match_score(
        existing,
        candidate,
        artist_service=artist_service,
    )
    reference_signature = _metadata_variant_signature(existing, source_file=reference_file)
    candidate_signature = _metadata_variant_signature(candidate)
    collaboration_matches = await _collaboration_signatures_match(
        reference_signature,
        candidate_signature,
        artist_service=artist_service,
    )
    collaboration_score = (
        1
        if not reference_signature.collaboration and not candidate_signature.collaboration
        else 3
        if collaboration_matches
        else -3
    )
    return _CandidateScore(
        base=base_score,
        variant=variant_sort_score(reference_signature, candidate_signature),
        collaboration=collaboration_score,
        variants_match=strong_variants_match(reference_signature, candidate_signature),
        collaboration_matches=collaboration_matches,
    )


async def _collaboration_signatures_match(
    left: TrackVariantSignature,
    right: TrackVariantSignature,
    *,
    artist_service: ArtistService | None = None,
) -> bool:
    if left.collaboration != right.collaboration:
        return False
    if not left.collaboration:
        return True
    if (
        len(left.artist_credits) < 2
        or len(right.artist_credits) < 2
        or len(left.artist_credits) != len(right.artist_credits)
    ):
        return False
    unmatched = list(right.artist_credits)
    for left_artist in left.artist_credits:
        match_index = None
        for index, right_artist in enumerate(unmatched):
            if await _artist_credit_exact_match(
                left_artist,
                right_artist,
                artist_service=artist_service,
            ):
                match_index = index
                break
        if match_index is None:
            return False
        unmatched.pop(match_index)
    return not unmatched


async def _artist_credit_exact_match(
    left: str,
    right: str,
    *,
    artist_service: ArtistService | None,
) -> bool:
    left_values = {_normalize_match_text(left)}
    right_values = {_normalize_match_text(right)}
    if artist_service is not None:
        left_canonical, right_canonical = await asyncio.gather(
            artist_service.get_canonical_name(left),
            artist_service.get_canonical_name(right),
        )
        left_aliases, right_aliases = await asyncio.gather(
            artist_service.get_aliases(left),
            artist_service.get_aliases(right),
        )
        left_values.update(
            _normalize_match_text(item)
            for item in (*left_aliases, left_canonical)
            if item
        )
        right_values.update(
            _normalize_match_text(item)
            for item in (*right_aliases, right_canonical)
            if item
        )
    left_values.discard("")
    right_values.discard("")
    return bool(left_values & right_values)


def _metadata_variant_signature(
    metadata: TrackMetadata,
    *,
    source_file: Path | None = None,
) -> TrackVariantSignature:
    directories: tuple[Path, ...] = ()
    if source_file is not None:
        directories = tuple(
            path
            for path in (source_file.parent, source_file.parent.parent)
            if path.name
        )
    return build_track_variant_signature(
        title=metadata.title,
        artist=metadata.artist,
        album=metadata.album,
        file_name=source_file.name if source_file is not None else None,
        directories=directories,
    )


def _metadata_candidate_key(metadata: TrackMetadata) -> tuple[object, ...]:
    signature = _metadata_variant_signature(metadata)
    return (
        signature.normalized_base_title,
        signature.artist_credit_keys
        or ((_normalize_match_text(metadata.artist),) if metadata.artist else ()),
        _normalize_match_text(metadata.album),
        tuple(sorted(signature.strong_variants)),
        signature.collaboration,
        _metadata_has_value(metadata, "lyrics"),
    )


def _variant_signature_text(signature: TrackVariantSignature) -> str:
    labels = {
        "live": "Live",
        "remix": "Remix",
        "acoustic": "Acoustic",
        "instrumental": "Instrumental",
        "karaoke": "Karaoke",
        "demo": "Demo",
    }
    variants = "+".join(
        labels[item] for item in sorted(signature.strong_variants)
    ) or "普通版"
    if not signature.collaboration:
        return variants
    artists = "/".join(signature.artist_credits) or "unknown"
    return f"{variants};feat={artists}"


def _variant_evidence_text(signature: TrackVariantSignature) -> str:
    if not signature.evidence:
        return "none"
    return "|".join(
        f"{item.source}:{item.strength}:{item.variant}:{item.raw_value}"
        for item in signature.evidence
    )


async def _metadata_match_score(
    existing: TrackMetadata,
    scraped: TrackMetadata,
    *,
    artist_service: ArtistService | None = None,
) -> _MatchScore:
    existing_title = _metadata_variant_signature(existing).base_title
    scraped_title = _metadata_variant_signature(scraped).base_title
    title_score = _match_score(existing_title, scraped_title)
    artist_score = await _match_artist_with_aliases(
        existing.artist,
        scraped.artist,
        artist_service=artist_service,
    )
    album_score = _match_score(existing.album, scraped.album)

    # Strong penalty: existing artist known but candidate artist doesn't match
    if _metadata_has_value(existing, "artist") and artist_score == 0:
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


def _primary_artist(value: str | None) -> str | None:
    artists = split_artist_credit(value)
    return artists[0] if artists else None


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
        album_artist=scraped.album_artist or existing.album_artist,
        year=scraped.year or existing.year,
        track_number=scraped.track_number or existing.track_number,
        lyrics=scraped.lyrics or existing.lyrics,
        cover_url=scraped.cover_url or existing.cover_url,
        extra={**existing.extra, **scraped.extra},
    )


def _merge_missing_metadata(
    existing: TrackMetadata,
    scraped: TrackMetadata,
    *,
    preserve_artist_album: bool = False,
) -> TrackMetadata:
    artist = existing.artist
    album = existing.album
    if not preserve_artist_album:
        artist = existing.artist or scraped.artist
        album = existing.album or scraped.album
    return TrackMetadata(
        title=existing.title or scraped.title,
        artist=artist,
        album=album,
        album_artist=existing.album_artist or scraped.album_artist,
        year=existing.year or scraped.year,
        track_number=existing.track_number or scraped.track_number,
        lyrics=existing.lyrics or scraped.lyrics,
        cover_url=existing.cover_url or scraped.cover_url,
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
    if not isinstance(value, str) or not value.strip():
        return False
    if field not in {"artist", "album"}:
        return True
    normalized = unicodedata.normalize("NFKC", value).casefold()
    if "\ufffd" in normalized or "锟斤拷" in normalized:
        return False
    key = re.sub(r"\W+", "", normalized)
    return bool(key) and key not in _INVALID_METADATA_TEXT_KEYS


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
