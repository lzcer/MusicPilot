from __future__ import annotations

import asyncio
from pathlib import Path

import httpx

from musicpilot.ports.metadata import AlbumIdentity, TrackMetadata


class MutagenTagWriter:
    async def write(
        self,
        path: Path,
        metadata: TrackMetadata,
        album_identity: AlbumIdentity | None = None,
    ) -> None:
        cover = await _fetch_cover(metadata.cover_url)
        await asyncio.to_thread(
            _write_tags_sync,
            path,
            metadata,
            cover,
            album_identity,
        )


def _write_tags_sync(
    path: Path,
    metadata: TrackMetadata,
    cover: tuple[bytes, str] | None = None,
    album_identity: AlbumIdentity | None = None,
) -> None:
    from mutagen import File as MutagenFile

    audio = MutagenFile(path, easy=True)
    if audio is None:
        return

    try:
        if audio.tags is None:
            audio.add_tags()
    except Exception:
        _close_audio(audio)
        return

    _set_tag(audio, "title", metadata.title)
    _set_tag(audio, "artist", metadata.artist, split_commas=True)
    _set_tag(audio, "album", metadata.album)
    if album_identity is None:
        _set_tag(audio, "albumartist", metadata.album_artist)
    else:
        _set_or_clear_tag(audio, "albumartist", album_identity.album_artist)
        _set_or_clear_tag(
            audio,
            "musicbrainz_albumid",
            album_identity.musicbrainz_album_id,
        )
    year = str(metadata.year) if metadata.year is not None else None
    _set_tag(audio, "date", year)
    _set_tag(audio, "year", year)
    _set_tag(
        audio,
        "tracknumber",
        str(metadata.track_number) if metadata.track_number is not None else None,
    )
    if metadata.lyrics:
        _set_tag(audio, "lyrics", metadata.lyrics)
    audio.save()
    _close_audio(audio)
    if album_identity is not None:
        _write_album_identity_sync(path, album_identity)
    if metadata.lyrics:
        _write_lyrics_sync(path, metadata.lyrics)
    if cover is not None:
        _write_cover_sync(path, cover[0], cover[1])


def _set_tag(
    audio: object,
    key: str,
    value: str | None,
    *,
    split_commas: bool = False,
) -> None:
    if value:
        try:
            values = (
                [item.strip() for item in value.split(",") if item.strip()]
                if split_commas
                else [value]
            )
            audio[key] = values
        except Exception:
            return


def _set_or_clear_tag(audio: object, key: str, value: str | None) -> None:
    try:
        if value:
            audio[key] = [value]
        else:
            del audio[key]
    except (KeyError, TypeError, ValueError):
        return


def _write_album_identity_sync(path: Path, identity: AlbumIdentity) -> None:
    from mutagen import File as MutagenFile
    from mutagen.flac import FLAC
    from mutagen.id3 import TDRL, TXXX
    from mutagen.mp3 import MP3
    from mutagen.mp4 import MP4
    from mutagen.oggopus import OggOpus
    from mutagen.oggvorbis import OggVorbis

    audio = MutagenFile(path)
    if audio is None:
        return
    try:
        if isinstance(audio, MP3):
            if audio.tags is None:
                audio.add_tags()
            audio.tags.delall("TXXX:ALBUMVERSION")
            if identity.album_version:
                audio.tags.add(
                    TXXX(
                        encoding=3,
                        desc="ALBUMVERSION",
                        text=[identity.album_version],
                    )
                )
            audio.tags.delall("TDRL")
            if identity.release_date:
                audio.tags.add(
                    TDRL(
                        encoding=3,
                        text=[identity.release_date],
                    )
                )
        elif isinstance(audio, FLAC | OggVorbis | OggOpus):
            _set_or_clear_native_tag(audio, "ALBUMVERSION", identity.album_version)
            _set_or_clear_native_tag(audio, "RELEASEDATE", identity.release_date)
        elif isinstance(audio, MP4):
            _set_or_clear_mp4_freeform(
                audio,
                "----:com.apple.iTunes:ALBUMVERSION",
                identity.album_version,
            )
            _set_or_clear_native_tag(audio, "\xa9day", identity.release_date)
            _set_or_clear_mp4_freeform(
                audio,
                "----:com.apple.iTunes:RELEASEDATE",
                None,
            )
        audio.save()
    finally:
        _close_audio(audio)


def _set_or_clear_native_tag(audio: object, key: str, value: str | None) -> None:
    if value:
        audio[key] = [value]
        return
    try:
        del audio[key]
    except KeyError:
        return


def _set_or_clear_mp4_freeform(audio: object, key: str, value: str | None) -> None:
    if value:
        audio[key] = [value.encode("utf-8")]
        return
    try:
        del audio[key]
    except KeyError:
        return


async def _fetch_cover(cover_url: str | None) -> tuple[bytes, str] | None:
    if not cover_url:
        return None
    try:
        async with httpx.AsyncClient(timeout=20, follow_redirects=True) as client:
            response = await client.get(cover_url)
            response.raise_for_status()
    except Exception:
        return None
    content_type = response.headers.get("content-type", "").split(";", 1)[0].strip().lower()
    if content_type not in {"image/jpeg", "image/png", "image/webp"}:
        if response.content.startswith(b"\xff\xd8"):
            content_type = "image/jpeg"
        elif response.content.startswith(b"\x89PNG"):
            content_type = "image/png"
        elif response.content.startswith(b"RIFF") and response.content[8:12] == b"WEBP":
            content_type = "image/webp"
        else:
            return None
    if not response.content or len(response.content) > 10 * 1024 * 1024:
        return None
    return response.content, content_type


def _write_cover_sync(path: Path, cover_data: bytes, mime: str) -> None:
    from mutagen import File as MutagenFile
    from mutagen.flac import FLAC, Picture
    from mutagen.id3 import APIC
    from mutagen.mp3 import MP3
    from mutagen.mp4 import MP4, MP4Cover

    audio = MutagenFile(path)
    if audio is None:
        return
    try:
        if isinstance(audio, MP3):
            if audio.tags is None:
                audio.add_tags()
            audio.tags.delall("APIC")
            audio.tags.add(APIC(encoding=3, mime=mime, type=3, desc="Cover", data=cover_data))
        elif isinstance(audio, FLAC):
            picture = Picture()
            picture.type = 3
            picture.mime = mime
            picture.desc = "Cover"
            picture.data = cover_data
            audio.clear_pictures()
            audio.add_picture(picture)
        elif isinstance(audio, MP4):
            if mime not in {"image/jpeg", "image/png"}:
                return
            image_format = MP4Cover.FORMAT_PNG if mime == "image/png" else MP4Cover.FORMAT_JPEG
            audio["covr"] = [MP4Cover(cover_data, imageformat=image_format)]
        audio.save()
    finally:
        _close_audio(audio)


def _write_lyrics_sync(path: Path, lyrics: str) -> None:
    from mutagen import File as MutagenFile
    from mutagen.flac import FLAC
    from mutagen.id3 import USLT
    from mutagen.mp3 import MP3
    from mutagen.mp4 import MP4
    from mutagen.oggopus import OggOpus
    from mutagen.oggvorbis import OggVorbis

    audio = MutagenFile(path)
    if audio is None:
        return
    try:
        if isinstance(audio, MP3):
            if audio.tags is None:
                audio.add_tags()
            audio.tags.delall("USLT")
            audio.tags.add(USLT(encoding=3, lang="eng", desc="", text=lyrics))
        elif isinstance(audio, FLAC | OggVorbis | OggOpus):
            audio["LYRICS"] = [lyrics]
        elif isinstance(audio, MP4):
            audio["\xa9lyr"] = [lyrics]
        audio.save()
    finally:
        _close_audio(audio)


def _close_audio(audio: object) -> None:
    close = getattr(audio, "close", None)
    if callable(close):
        close()
