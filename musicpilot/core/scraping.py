from __future__ import annotations

import asyncio
import os
import re
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from musicpilot.core.metadata import MetadataCascade
from musicpilot.ports.metadata import TrackMetadata
from musicpilot.ports.tag_writer import TagWriter

ScrapingMode = Literal["source", "mapped", "copy"]
RequiredMetadata = Literal["album", "artist", "lyrics"]
ClassifyBy = Literal["artist", "album"]

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


@dataclass(frozen=True, slots=True)
class ScrapingFileResult:
    source_path: Path
    library_path: Path | None
    metadata: TrackMetadata
    status: Literal["success", "failed"]
    error_message: str | None = None


@dataclass(frozen=True, slots=True)
class ScrapingSummary:
    source_files: int = 0
    mapped_files: int = 0
    updated_files: int = 0
    moved_files: int = 0
    failed_files: int = 0
    results: tuple[ScrapingFileResult, ...] = ()


class LocalMusicScraper:
    def __init__(
        self,
        *,
        metadata: MetadataCascade,
        tag_writer: TagWriter | None,
    ) -> None:
        self.metadata = metadata
        self.tag_writer = tag_writer

    async def process_download(
        self,
        *,
        task_name: str,
        save_path: str | None,
        config: ScrapingConfig,
    ) -> ScrapingSummary:
        if not config.enabled:
            return ScrapingSummary()
        source_files = await asyncio.to_thread(_download_audio_files, task_name, save_path)
        if not source_files:
            return ScrapingSummary()

        mapped_files = 0
        updated_files = 0
        moved_files = 0
        results: list[ScrapingFileResult] = []
        for source_file in source_files:
            try:
                result, mapped, updated, moved = await self._process_file(source_file, config)
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
                )
                mapped = updated = moved = 0
            results.append(result)
            mapped_files += mapped
            updated_files += updated
            moved_files += moved

        return ScrapingSummary(
            source_files=len(source_files),
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
    ) -> tuple[ScrapingFileResult, int, int, int]:
        working_file = source_file
        mapped_files = 0
        updated_files = 0
        moved_files = 0
        source_metadata = await asyncio.to_thread(read_track_metadata, source_file)
        needs_update = _metadata_missing(source_metadata, config.required_metadata)
        metadata = source_metadata
        if needs_update:
            candidates = await self.metadata.search_metadata(
                title=source_metadata.title,
                artist=source_metadata.artist,
                limit=8,
            )
            looked_up = _select_metadata_candidate(
                source_metadata,
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
                        error_message="未找到可信的刮削候选。",
                    ),
                    0,
                    0,
                    0,
                )
            if self.tag_writer is None:
                return (
                    ScrapingFileResult(
                        source_path=source_file,
                        library_path=None,
                        metadata=source_metadata,
                        status="failed",
                        error_message="标签写入器不可用。",
                    ),
                    0,
                    0,
                    0,
                )
            metadata = _merge_metadata(source_metadata, looked_up)

        if config.mode == "mapped":
            working_file = await asyncio.to_thread(
                _copy_to_mapping,
                source_file,
                config,
                hardlink=not needs_update,
            )
            mapped_files += 1
        elif config.mode == "copy":
            working_file = await asyncio.to_thread(
                _copy_to_mapping,
                source_file,
                config,
                hardlink=False,
            )
            mapped_files += 1

        if needs_update:
            await self.tag_writer.write(working_file, metadata)
            updated_files += 1

        final_file = await asyncio.to_thread(
            _classify_or_rename,
            working_file,
            metadata,
            config,
        )
        if final_file != working_file:
            moved_files += 1
        return (
            ScrapingFileResult(
                source_path=source_file,
                library_path=final_file,
                metadata=metadata,
                status="success",
            ),
            mapped_files,
            updated_files,
            moved_files,
        )


def scraping_config_from_payload(payload: dict[str, object]) -> ScrapingConfig:
    scraping = payload.get("scraping")
    if not isinstance(scraping, dict):
        scraping = {}
    mode = str(scraping.get("mode") or "mapped")
    classify_by = str(scraping.get("classify_by") or "artist")
    required = scraping.get("required_metadata")
    if mode not in {"source", "mapped", "copy"}:
        mode = "mapped"
    return ScrapingConfig(
        enabled=bool(scraping.get("enabled")),
        mode=mode,
        source_directory=_optional_path(scraping.get("source_directory")),
        mapped_directory=_optional_path(scraping.get("mapped_directory")),
        required_metadata=_required_metadata(required),
        auto_rename=bool(scraping.get("auto_rename")),
        auto_classify=bool(scraping.get("auto_classify")),
        classify_by="album" if classify_by == "album" else "artist",
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


def _copy_to_mapping(source_file: Path, config: ScrapingConfig, *, hardlink: bool) -> Path:
    if config.mapped_directory is None:
        raise RuntimeError("Target directory is required for mapped or copy scraping.")
    relative = source_file.name
    if config.source_directory is not None:
        try:
            relative = str(source_file.relative_to(config.source_directory))
        except ValueError:
            relative = source_file.name
    target = _unique_path(config.mapped_directory / relative)
    target.parent.mkdir(parents=True, exist_ok=True)
    if hardlink:
        try:
            os.link(source_file, target)
            return target
        except OSError:
            pass
    shutil.copy2(source_file, target)
    return target


def _classify_or_rename(path: Path, metadata: TrackMetadata, config: ScrapingConfig) -> Path:
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
    target = _unique_path(target_dir / target_name, current=path)
    if target == path:
        return path
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(path), str(target))
    return target


def _metadata_missing(metadata: TrackMetadata, required: tuple[RequiredMetadata, ...]) -> bool:
    for field in required:
        value = getattr(metadata, field)
        if not isinstance(value, str) or not value.strip():
            return True
    return False


def _select_metadata_candidate(
    existing: TrackMetadata,
    candidates: tuple[TrackMetadata, ...],
    required: tuple[RequiredMetadata, ...],
) -> TrackMetadata | None:
    ranked: list[tuple[int, TrackMetadata]] = []
    for candidate in candidates:
        if not _candidate_fills_required(existing, candidate, required):
            continue
        score = _metadata_match_score(existing, candidate)
        if score >= 4:
            ranked.append((score, candidate))
    if not ranked:
        return None
    ranked.sort(key=lambda item: item[0], reverse=True)
    return ranked[0][1]


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


def _metadata_match_score(existing: TrackMetadata, scraped: TrackMetadata) -> int:
    existing_title = _normalize_match_text(existing.title)
    scraped_title = _normalize_match_text(scraped.title)
    if not existing_title or not scraped_title:
        return 0
    if existing_title != scraped_title:
        return 0
    score = 4
    if existing.artist and scraped.artist:
        existing_artist = _normalize_match_text(existing.artist)
        scraped_artist = _normalize_match_text(scraped.artist)
        if (
            existing_artist
            and scraped_artist
            and existing_artist not in scraped_artist
            and scraped_artist not in existing_artist
        ):
            return 0
        score += 2
    if existing.album and scraped.album:
        existing_album = _normalize_match_text(existing.album)
        scraped_album = _normalize_match_text(scraped.album)
        if existing_album and scraped_album and existing_album == scraped_album:
            score += 1
    if scraped.lyrics:
        score += 1
    if scraped.cover_url:
        score += 1
    return score


def _normalize_match_text(value: str | None) -> str:
    if not value:
        return ""
    text = re.sub(r"\[[^\]]+\]|\([^\)]*\)", " ", value)
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
