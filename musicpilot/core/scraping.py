from __future__ import annotations

import asyncio
import os
import re
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from opencc import OpenCC

from musicpilot.core.artist import ArtistService, normalize_artist_name
from musicpilot.core.metadata import MetadataCascade
from musicpilot.ports.metadata import TrackMetadata
from musicpilot.ports.tag_writer import TagWriter

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


@dataclass(frozen=True, slots=True)
class ScrapingConfig:
    enabled: bool = False
    mode: ScrapingMode = "mapped"
    source_directory: Path | None = None
    mapped_directory: Path | None = None
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
                )
            except Exception as exc:
                try:
                    source_metadata = await asyncio.to_thread(read_track_metadata, source_file)
                except Exception:
                    source_metadata = TrackMetadata(title=source_file.stem)
                result = ScrapingFileResult(
                    source_path=source_file,
                    library_path=None,
                    metadata=source_metadata,
                    status="failed",
                    error_message=str(exc) or exc.__class__.__name__,
                    stage=exc.__class__.__name__,
                )
                mapped = updated = moved = 0
            results.append(result)
            mapped_files += mapped
            updated_files += updated
            moved_files += moved

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
    ) -> tuple[ScrapingFileResult, int, int, int]:
        working_file = source_file
        mapped_files = 0
        updated_files = 0
        moved_files = 0
        source_metadata = await asyncio.to_thread(read_track_metadata, source_file)
        dir_meta = (dir_inferred or {}).get(source_file)
        match_metadata = _metadata_for_matching(source_metadata, source_file, dir_meta=dir_meta)
        needs_update = _metadata_missing(source_metadata, config.required_metadata)
        metadata = _merge_metadata(source_metadata, match_metadata)
        candidate_count = 0
        tag_writer = self.tag_writer
        if needs_update:
            candidates = await self._search_metadata_candidates(source_metadata, match_metadata)
            candidate_count = len(candidates)
            looked_up = _select_metadata_candidate(
                match_metadata,
                candidates,
                config.required_metadata,
            )
            if looked_up is None:
                return (
                    ScrapingFileResult(
                        source_path=source_file,
                        library_path=None,
                        metadata=source_metadata,
                        status="failed",
                        error_message=_candidate_failure_message(
                            match_metadata,
                            config.required_metadata,
                            candidates,
                        ),
                        stage="metadata_candidate",
                        needs_metadata_update=needs_update,
                        candidate_count=candidate_count,
                    ),
                    0,
                    0,
                    0,
                )
            if tag_writer is None:
                return (
                    ScrapingFileResult(
                        source_path=source_file,
                        library_path=None,
                        metadata=source_metadata,
                        status="failed",
                        error_message="标签写入器不可用。",
                        stage="tag_writer",
                        needs_metadata_update=needs_update,
                        candidate_count=candidate_count,
                    ),
                    0,
                    0,
                    0,
                )
            metadata = _merge_metadata(metadata, looked_up)

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

        duplicate = _find_duplicate_media(
            _duplicate_metadata_candidates(source_metadata, match_metadata, metadata),
            (*library_tracks, *media_history),
        )
        overwrite_duplicate = False
        current_size = await asyncio.to_thread(_file_size, source_file)
        if duplicate is not None:
            if config.duplicate_handling == "ignore":
                return (
                    ScrapingFileResult(
                        source_path=source_file,
                        library_path=None,
                        metadata=metadata,
                        status="skipped",
                        error_message=_duplicate_skip_message(
                            metadata,
                            duplicate,
                            current_size,
                            reason="音乐库已存在，重复文件处理为不处理",
                        ),
                        stage="skip_duplicate",
                        needs_metadata_update=needs_update,
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
                    return (
                        ScrapingFileResult(
                            source_path=source_file,
                            library_path=None,
                            metadata=metadata,
                            status="skipped",
                            error_message=_duplicate_skip_message(
                                metadata,
                                duplicate,
                                current_size,
                                reason=reason,
                            ),
                            stage="skip_smaller_duplicate",
                            needs_metadata_update=needs_update,
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
        if config.mode == "mapped":
            mapped_result = await asyncio.to_thread(
                _copy_to_mapping,
                source_file,
                config,
                hardlink=not needs_update,
                overwrite=not _will_classify_or_rename(config),
            )
            working_file = mapped_result.path
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
            overwritten_existing_target = mapped_result.overwritten_existing
            mapped_files += 1

        if needs_update:
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
        return (
            ScrapingFileResult(
                source_path=source_file,
                library_path=final_file,
                metadata=metadata,
                status="success",
                error_message=remark,
                needs_metadata_update=needs_update,
                candidate_count=candidate_count,
            ),
            mapped_files,
            updated_files,
            moved_files,
        )

    async def _search_metadata_candidates(
        self,
        source_metadata: TrackMetadata,
        match_metadata: TrackMetadata,
    ) -> tuple[TrackMetadata, ...]:
        # Build search tuples: (title, artist) from various sources
        searches: list[tuple[str, str | None]] = []
        seen_queries: set[tuple[str, str | None]] = set()

        for title, artist in [
            (match_metadata.title, match_metadata.artist),
            (source_metadata.title, source_metadata.artist),
        ]:
            if not title:
                continue
            # Search with each alias of the artist
            if self.artist_service is not None and artist:
                aliases = await self.artist_service.get_aliases(artist)
                for alias in aliases:
                    query = (title, alias)
                    if query not in seen_queries:
                        seen_queries.add(query)
                        searches.append(query)
            else:
                query = (title, artist)
                if query not in seen_queries:
                    seen_queries.add(query)
                    searches.append(query)

        # Also add a pure title search as fallback
        for title in (match_metadata.title, source_metadata.title):
            if title:
                query = (title, None)
                if query not in seen_queries:
                    seen_queries.add(query)
                    searches.append((title, None))

        candidates: list[TrackMetadata] = []
        seen: set[tuple[str, str, str]] = set()
        for title, artist in searches:
            if not title:
                continue
            for candidate in await self.metadata.search_metadata(
                title=title,
                artist=artist,
                limit=5,
            ):
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


def scraping_config_from_payload(payload: dict[str, object]) -> ScrapingConfig:
    scraping = payload.get("scraping")
    if not isinstance(scraping, dict):
        scraping = {}
    mode = str(scraping.get("mode") or "mapped")
    classify_by = str(scraping.get("classify_by") or "artist")
    duplicate_handling = str(scraping.get("duplicate_handling") or "ignore")
    required = scraping.get("required_metadata")
    if mode not in {"source", "mapped", "copy"}:
        mode = "mapped"
    if duplicate_handling not in {"ignore", "overwrite", "keep_largest"}:
        duplicate_handling = "ignore"
    return ScrapingConfig(
        enabled=bool(scraping.get("enabled")),
        mode=mode,
        source_directory=_optional_path(scraping.get("source_directory")),
        mapped_directory=_optional_path(scraping.get("mapped_directory")),
        required_metadata=_required_metadata(required),
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
            )
        else:
            result[f] = TrackMetadata(
                title=title_no_track or stem,
                artist=info.artist,
                album=info.album,
            )

    return result


def _analyze_directory(dir_path: Path, children: list[Path]) -> _DirInferredInfo:
    """Analyze a single directory name and its child files for metadata.

    Returns inferred artist/album or None if the directory name is not
    informative (e.g. root directories, generic names).
    """
    dir_name = dir_path.name.strip()
    if not dir_name or dir_name in {".", "..", "downloads", "music", "library"}:
        return _DirInferredInfo()

    # Strip noise
    cleaned = _DIR_NOISE_RE.sub("", dir_name).strip()
    if not cleaned:
        cleaned = dir_name

    # Strip leading year patterns: "2014 周杰伦 - 哎呦" → "周杰伦 - 哎呦"
    cleaned = re.sub(r"^\d{4}\s+", "", cleaned).strip()

    # Try "Artist - Album" pattern
    parts = _ARTIST_SEP_RE.split(cleaned, maxsplit=1)
    if len(parts) == 2:
        artist_part = parts[0].strip()
        album_part = parts[1].strip()

        # Validate: artist part shouldn't look like a generic word or noise
        if artist_part and len(artist_part) >= 1:
            return _DirInferredInfo(artist=artist_part, album=album_part)

    # No artist separator found. Always check grandparent as potential artist,
    # then decide whether current dir is an album or standalone artist dir.
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
            # Grandparent has "Artist - Album"
            return _DirInferredInfo(artist=gp_parts[0].strip(), album=cleaned)
        elif gp_cleaned and len(gp_cleaned) >= 2:
            # Grandparent is the artist, current dir is the album
            return _DirInferredInfo(artist=gp_cleaned, album=cleaned)

    # No grandparent or grandparent not usable. Try to determine if current
    # dir is an artist name or album name by checking child stems.
    child_stems = [c.stem for c in children]
    match_count = sum(
        1 for s in child_stems
        if _normalize_match_text(cleaned) in _normalize_match_text(s)
    )
    if children and match_count / len(children) >= 0.5:
        # Dir name matches child stems → it's an album
        return _DirInferredInfo(artist=None, album=cleaned)

    # Default: the dir name is the artist name (and also album)
    return _DirInferredInfo(artist=cleaned, album=cleaned)


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
        return _PathOperationResult(target)
    overwritten_existing = overwrite and target.exists()
    target.parent.mkdir(parents=True, exist_ok=True)
    if hardlink:
        try:
            if overwritten_existing:
                _remove_existing_target(target)
            os.link(source_file, target)
            return _PathOperationResult(target, overwritten_existing=overwritten_existing)
        except OSError:
            pass
    if overwritten_existing:
        _remove_existing_target(target)
    shutil.copy2(source_file, target)
    return _PathOperationResult(target, overwritten_existing=overwritten_existing)


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
        return _PathOperationResult(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    overwritten_existing = overwrite and target.exists()
    if overwritten_existing:
        _remove_existing_target(target)
    shutil.move(str(path), str(target))
    return _PathOperationResult(target, overwritten_existing=overwritten_existing)


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


def _find_duplicate_media(
    candidates: tuple[TrackMetadata, ...],
    tracks: tuple[LibraryTrackSnapshot, ...],
) -> LibraryTrackSnapshot | None:
    best: LibraryTrackSnapshot | None = None
    best_score = 0
    for metadata in candidates:
        title = _normalize_match_text(metadata.title)
        artist = _normalize_match_text(metadata.artist)
        album = _normalize_match_text(metadata.album)
        if not title:
            continue
        for track in tracks:
            if _normalize_match_text(track.title) != title:
                continue
            track_artist = _normalize_match_text(track.artist)
            track_album = _normalize_match_text(track.album)
            if artist and track_artist and artist != track_artist:
                continue
            score = 1
            if artist and track_artist == artist:
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
        return TrackMetadata(
            title=metadata.title,
            artist=dir_meta.artist,
            album=dir_meta.album or metadata.album,
            year=metadata.year,
            track_number=metadata.track_number,
            lyrics=metadata.lyrics,
            cover_url=metadata.cover_url,
            extra=metadata.extra,
        )

    return metadata


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


def _strip_track_prefix(value: str) -> str:
    return re.sub(r"^\s*(?:cd\s*)?\d{1,3}(?:[.\-_、\s]+)", "", value, flags=re.I).strip()


_MATCH_SCORE_THRESHOLD = 1  # Minimum total score to accept a candidate


def _select_metadata_candidate(
    existing: TrackMetadata,
    candidates: tuple[TrackMetadata, ...],
    required: tuple[RequiredMetadata, ...],
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
        score = _metadata_match_score(existing, candidate)
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


def _candidate_failure_message(
    metadata: TrackMetadata,
    required: tuple[RequiredMetadata, ...],
    candidates: tuple[TrackMetadata, ...],
) -> str:
    required_text = ", ".join(required) if required else "none"
    score_text = _best_candidate_score_text(metadata, candidates)
    return (
        "未找到可信的刮削候选。"
        f"title={metadata.title!r}, artist={metadata.artist!r}, "
        f"required={required_text}, candidates={len(candidates)}"
        f"{score_text}"
    )


def _best_candidate_score_text(
    metadata: TrackMetadata,
    candidates: tuple[TrackMetadata, ...],
) -> str:
    best_candidate = None
    best_score = _MatchScore()
    for candidate in candidates:
        score = _metadata_match_score(metadata, candidate)
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


def _metadata_match_score(existing: TrackMetadata, scraped: TrackMetadata) -> _MatchScore:
    title_score = _match_score(existing.title, scraped.title)
    artist_score = _match_artist(existing.artist, scraped.artist)
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
    return 0


def _match_artist(left: str | None, right: str | None) -> int:
    if not left or not right:
        return 0
    return max(_match_score(left, item) for item in re.split(r"[,，、/&]+", right))


def _normalize_match_text(value: str | None) -> str:
    if not value:
        return ""
    # Remove content in brackets/parens (version info, quality tags)
    text = re.sub(r"\[[^\]]+\]|\([^\)]*\)", " ", value)
    # Traditional \u2192 Simplified
    text = _t2s.convert(text)
    # Keep only alphanumeric and CJK
    text = re.sub(r"[^0-9a-zA-Z\u4e00-\u9fff]+", "", text)
    return text.casefold()


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
