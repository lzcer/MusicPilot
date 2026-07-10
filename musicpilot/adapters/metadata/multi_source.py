from __future__ import annotations

import base64
import hashlib
import random
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TypeVar
from uuid import uuid1

import httpx
from opencc import OpenCC

from musicpilot.ports.metadata import TrackMetadata

_OPENCC_T2S = OpenCC("t2s")
_RESOURCE_ORDER = ("qmusic", "netease", "migu", "kuwo")
T = TypeVar("T")


@dataclass(frozen=True, slots=True)
class _SourceSong:
    source: str
    song_id: str
    name: str
    artist: str
    album: str
    album_img: str | None = None
    year: str | None = None


class MultiSourceMusicProvider:
    def __init__(
        self,
        client: httpx.AsyncClient | None = None,
        source_gate: Callable[[str, Callable[[], Awaitable[T]]], Awaitable[T]] | None = None,
    ) -> None:
        self._client = client or httpx.AsyncClient(timeout=20, follow_redirects=True)
        self._owns_client = client is None
        self._kuwo_token = _generate_kw_token()
        self._kuwo_cross = _sha1_and_md5(self._kuwo_token)
        self._source_gate = source_gate
        self._source_rotation = random.randrange(len(_RESOURCE_ORDER))

    @property
    def name(self) -> str:
        return "multi-source"

    async def close(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    async def lookup(self, *, title: str, artist: str | None = None) -> TrackMetadata | None:
        candidates = await self.search_metadata(title=title, artist=artist, limit=1)
        return candidates[0] if candidates else None

    async def search_metadata(
        self,
        *,
        title: str,
        artist: str | None = None,
        limit: int = 5,
    ) -> tuple[TrackMetadata, ...]:
        async for candidates in self.iter_metadata_batches(
            title=title,
            artist=artist,
            limit=limit,
        ):
            return candidates
        return ()

    async def search_metadata_from_source(
        self,
        source: str,
        *,
        title: str,
        artist: str | None = None,
        limit: int = 5,
    ) -> tuple[TrackMetadata, ...]:
        if source not in _RESOURCE_ORDER:
            raise ValueError(f"Unsupported metadata source: {source}")
        return await self._run_with_source_gate(
            source,
            lambda: self._metadata_batch_for_resource(
                source,
                title=title,
                artist=artist,
                limit=limit,
            ),
        )

    async def iter_metadata_batches(
        self,
        *,
        title: str,
        artist: str | None = None,
        limit: int = 5,
    ) -> AsyncIterator[tuple[TrackMetadata, ...]]:
        for resource in self._next_resource_order():
            batch = await self._run_with_source_gate(
                resource,
                lambda resource=resource: self._metadata_batch_for_resource(
                    resource,
                    title=title,
                    artist=artist,
                    limit=limit,
                ),
            )
            if not batch:
                continue
            yield batch

    async def _run_with_source_gate(
        self,
        resource: str,
        runner: Callable[[], Awaitable[T]],
    ) -> T:
        if self._source_gate is None:
            return await runner()
        return await self._source_gate(resource, runner)

    def _next_resource_order(self) -> tuple[str, ...]:
        start = self._source_rotation % len(_RESOURCE_ORDER)
        self._source_rotation += 1
        return (*_RESOURCE_ORDER[start:], *_RESOURCE_ORDER[:start])

    async def _metadata_batch_for_resource(
        self,
        resource: str,
        *,
        title: str,
        artist: str | None,
        limit: int,
    ) -> tuple[TrackMetadata, ...]:
        songs = await self._fetch_id3_by_title(resource, title, artist=artist)
        matched = _matched_songs(title, artist or "", songs, limit)
        if not matched:
            return ()
        results = []
        for song in matched:
            lyrics = await self._fetch_lyric(song)
            results.append(_song_metadata(song, lyrics))
        return tuple(results)

    async def _fetch_id3_by_title(
        self,
        resource: str,
        title: str,
        artist: str | None = None,
    ) -> tuple[_SourceSong, ...]:
        try:
            if resource == "qmusic":
                return await self._fetch_qmusic_id3_by_title(title, artist=artist)
            if resource == "netease":
                return await self._fetch_netease_id3_by_title(title, artist=artist)
            if resource == "migu":
                return await self._fetch_migu_id3_by_title(title, artist=artist)
            if resource == "kuwo":
                return await self._fetch_kuwo_id3_by_title(title, artist=artist)
        except Exception:
            return ()
        return ()

    async def _fetch_lyric(self, song: _SourceSong) -> str | None:
        try:
            if song.source == "qmusic":
                return await self._fetch_qmusic_lyric(song.song_id)
            if song.source == "netease":
                return await self._fetch_netease_lyric(song.song_id)
            if song.source == "migu":
                return await self._fetch_migu_lyric(song.song_id)
            if song.source == "kuwo":
                return await self._fetch_kuwo_lyric(song.song_id)
        except Exception:
            return None
        return None

    async def _fetch_qmusic_id3_by_title(
        self,
        title: str,
        artist: str | None = None,
    ) -> tuple[_SourceSong, ...]:
        query = _search_query(title, artist)
        payload = {
            "comm": {
                "wid": "",
                "tmeAppID": "qqmusic",
                "authst": "",
                "uid": "",
                "gray": "0",
                "OpenUDID": "2d484d3157d4ed482e406e6c5fdcf8c3d3275deb",
                "ct": "6",
                "patch": "2",
                "psrf_qqopenid": "",
                "sid": "",
                "psrf_access_token_expiresAt": "",
                "cv": "80600",
                "gzip": "0",
                "qq": "",
                "nettype": "2",
                "psrf_qqunionid": "",
                "psrf_qqaccess_token": "",
                "tmeLoginType": "2",
            },
            "music.search.SearchCgiService.DoSearchForQQMusicDesktop": {
                "module": "music.search.SearchCgiService",
                "method": "DoSearchForQQMusicDesktop",
                "param": {
                    "num_per_page": 15,
                    "page_num": 1,
                    "remoteplace": "txt.mac.search",
                    "search_type": 0,
                    "query": query,
                    "grp": 1,
                    "searchid": str(uuid1()),
                    "nqc_flag": 0,
                },
            },
        }
        response = await self._client.post(
            "https://u.y.qq.com/cgi-bin/musicu.fcg",
            json=payload,
            headers={
                "referer": "https://y.qq.com/portal/profile.html",
                "Content-Type": "json/application;charset=utf-8",
                "user-agent": "QQ%E9%9F%B3%E4%B9%90/73222 CFNetwork/1406.0.3 Darwin/22.4.0",
            },
        )
        response.raise_for_status()
        body = response.json()
        data = body["music.search.SearchCgiService.DoSearchForQQMusicDesktop"]["data"]
        songs = data.get("body", {}).get("song", {}).get("list", [])
        results: list[_SourceSong] = []
        for item in songs:
            album = item.get("album") if isinstance(item.get("album"), dict) else {}
            file_info = item.get("file") if isinstance(item.get("file"), dict) else {}
            singers = item.get("singer") if isinstance(item.get("singer"), list) else []
            album_mid = str(album.get("mid") or "")
            results.append(
                _SourceSong(
                    source="qmusic",
                    song_id=str(item.get("mid") or file_info.get("media_mid") or ""),
                    name=str(item.get("title") or ""),
                    artist=",".join(str(singer.get("name") or "") for singer in singers),
                    album=str(album.get("title") or "未分类专辑"),
                    album_img=(
                        f"http://y.qq.com/music/photo_new/T002R300x300M000{album_mid}.jpg"
                        if album_mid
                        else None
                    ),
                    year=str(item.get("time_public") or ""),
                )
            )
        return tuple(item for item in results if item.song_id and item.name)

    async def _fetch_qmusic_lyric(self, song_id: str) -> str | None:
        response = await self._client.get(
            "https://c.y.qq.com/lyric/fcgi-bin/fcg_query_lyric_new.fcg",
            params={
                "g_tk": 5381,
                "format": "json",
                "inCharset": "utf-8",
                "outCharset": "utf-8",
                "notice": 0,
                "platform": "h5",
                "needNewCode": 1,
                "ct": 121,
                "cv": 0,
                "songmid": song_id,
            },
            headers={"Referer": "http://y.qq.com"},
        )
        response.raise_for_status()
        lyric = response.json().get("lyric")
        if not isinstance(lyric, str) or not lyric:
            return None
        return base64.b64decode(lyric).decode("utf-8", errors="ignore").strip() or None

    async def _fetch_netease_id3_by_title(
        self,
        title: str,
        artist: str | None = None,
    ) -> tuple[_SourceSong, ...]:
        query = _search_query(title, artist)
        response = await self._client.get(
            "https://music.163.com/api/search/get/web",
            params={"s": query, "type": 1, "limit": 10, "offset": 0},
            headers={
                "Referer": "https://music.163.com/",
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"
                ),
            },
        )
        response.raise_for_status()
        songs = response.json().get("result", {}).get("songs", [])
        results: list[_SourceSong] = []
        for song in songs:
            album = song.get("album") if isinstance(song.get("album"), dict) else {}
            artists = song.get("artists") if isinstance(song.get("artists"), list) else []
            results.append(
                _SourceSong(
                    source="netease",
                    song_id=str(song.get("id") or ""),
                    name=str(song.get("name") or ""),
                    artist=",".join(str(item.get("name") or "") for item in artists),
                    album=str(album.get("name") or ""),
                    album_img=_optional_string(album.get("picUrl")),
                    year=_timestamp_year_text(album.get("publishTime")),
                )
            )
        return tuple(item for item in results if item.song_id and item.name)

    async def _fetch_netease_lyric(self, song_id: str) -> str | None:
        response = await self._client.get(
            "https://music.163.com/api/song/lyric",
            params={"id": song_id, "lv": -1, "kv": -1, "tv": -1},
            headers={"Referer": "https://music.163.com/"},
        )
        response.raise_for_status()
        lyric = response.json().get("lrc", {}).get("lyric")
        return lyric.strip() if isinstance(lyric, str) and lyric.strip() else None

    async def _fetch_migu_id3_by_title(
        self,
        title: str,
        artist: str | None = None,
    ) -> tuple[_SourceSong, ...]:
        query = _search_query(title, artist)
        response = await self._client.get(
            "https://c.musicapp.migu.cn/v1.0/content/search_all.do",
            params={
                "text": query,
                "pageNo": 1,
                "pageSize": 10,
                "isCopyright": 1,
                "sort": 1,
                "searchSwitch": (
                    '{"song":1,"album":0,"singer":0,"tagSong":1,"mvSong":0,"bestShow":1}'
                ),
            },
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/148.0.0.0 Safari/537.36"
                ),
                "Accept": "application/json, text/plain, */*",
                "Origin": "https://h5.nf.migu.cn",
                "Referer": "https://h5.nf.migu.cn/",
                "ua": "Android_migu",
                "version": "6.8.8",
                "channel": "014021I",
                "subchannel": "014021I",
            },
        )
        response.raise_for_status()
        songs = response.json().get("songResultData", {}).get("result", [])
        return tuple(
            _SourceSong(
                source="migu",
                song_id=str(song.get("copyrightId") or ""),
                name=str(song.get("name") or song.get("songName") or ""),
                artist=",".join(
                    str(singer.get("name") or "")
                    for singer in song.get("singers", song.get("singerList", []))
                    if isinstance(singer, dict)
                ) or str(song.get("singerName") or ""),
                album=",".join(
                    str(album.get("name") or "")
                    for album in song.get("albums", [])
                    if isinstance(album, dict)
                ) or str(song.get("albumName") or ""),
                album_img=_migu_cover_url(song),
                year="",
            )
            for song in songs
            if song.get("copyrightId") and (song.get("name") or song.get("songName"))
        )

    async def _fetch_migu_lyric(self, song_id: str) -> str | None:
        response = await self._client.get(
            "https://music.migu.cn/v3/api/music/audioPlayer/getLyric",
            params={"copyrightId": song_id},
        )
        response.raise_for_status()
        lyric = response.json().get("lyric")
        return lyric.strip() if isinstance(lyric, str) and lyric.strip() else None

    async def _fetch_kuwo_id3_by_title(
        self,
        title: str,
        artist: str | None = None,
    ) -> tuple[_SourceSong, ...]:
        query = _search_query(title, artist)
        response = await self._client.get(
            "https://www.kuwo.cn/search/searchMusicBykeyWord",
            params={
                "vipver": 1,
                "client": "kt",
                "ft": "music",
                "cluster": 0,
                "strategy": 2012,
                "encoding": "utf8",
                "rformat": "json",
                "mobi": 1,
                "issubtitle": 1,
                "show_copyright_off": 1,
                "pn": 0,
                "rn": 10,
                "all": query,
            },
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/134.0.0.0 Safari/537.36"
                ),
            },
        )
        response.raise_for_status()
        songs = response.json().get("abslist", [])
        return tuple(
            _SourceSong(
                source="kuwo",
                song_id=str(song.get("MUSICRID") or song.get("rid") or "").removeprefix("MUSIC_"),
                name=str(song.get("SONGNAME") or song.get("NAME") or song.get("name") or ""),
                artist=str(song.get("ARTIST") or song.get("artist") or ""),
                album=str(song.get("ALBUM") or song.get("album") or ""),
                album_img=_optional_string(song.get("hts_MVPIC") or song.get("albumpic")),
                year="",
            )
            for song in songs
            if (song.get("MUSICRID") or song.get("rid"))
            and (song.get("SONGNAME") or song.get("NAME") or song.get("name"))
        )

    async def _fetch_kuwo_lyric(self, song_id: str) -> str | None:
        response = await self._client.get(
            "http://kuwo.cn/newh5/singles/songinfoandlrc",
            params={
                "musicId": song_id,
                "mid": song_id,
                "type": "music",
                "httpsStatus": 1,
                "plat": "web_www",
            },
            headers=_kuwo_headers(self._kuwo_token, self._kuwo_cross),
        )
        response.raise_for_status()
        lines = response.json().get("data", {}).get("lrclist", [])
        lyric = ""
        for line in lines:
            seconds = int(float(str(line.get("time") or "0")))
            minutes, second = divmod(seconds, 60)
            hour, minutes = divmod(minutes, 60)
            lyric += f"[{hour}:{minutes:02d}:{second:02d}]{line.get('lineLyric') or ''}\n"
        return lyric.strip() or None


def _search_query(title: str, artist: str | None = None) -> str:
    """Build search query: title alone, or title + artist when provided."""
    if artist:
        return f"{title} {artist}"
    return title


def _matched_songs(
    title: str,
    artist: str,
    songs: tuple[_SourceSong, ...],
    limit: int,
) -> tuple[_SourceSong, ...]:
    matched: list[tuple[int, int, _SourceSong]] = []
    for index, song in enumerate(songs):
        title_score = _match_score(title, song.name)
        artist_score = _match_artist(artist if artist else title, song.artist)
        album_score = _match_score(title, song.album)
        if artist and artist_score == 0:
            artist_score = -2
        if not artist and artist_score >= 1 and title_score >= 1:
            title_score = 2
        total = title_score + artist_score + album_score
        if total >= 3 or title_score == 2:
            matched.append((total, -index, song))
    matched.sort(reverse=True)
    return tuple(item[2] for item in matched[:limit])


def _match_score(left: str | None, right: str | None) -> int:
    try:
        left_value = _normalize_source_text(left)
        right_value = _normalize_source_text(right)
        if not left_value or not right_value:
            return 0
        if left_value == right_value:
            return 2
        if left_value in right_value or right_value in left_value:
            return 1
        return 0
    except Exception:
        return 0


def _match_artist(left: str | None, right: str | None) -> int:
    if not right:
        return 0
    if "," in right:
        artists = right.split(",")
        return sum(_match_score(left, item.replace(" ", "")) for item in artists[:2])
    return _match_score(left, right)


def _normalize_source_text(value: str | None) -> str:
    text = str(value or "").lower().replace(" ", "")
    return _OPENCC_T2S.convert(text)


def _song_metadata(song: _SourceSong, lyrics: str | None) -> TrackMetadata:
    return TrackMetadata(
        title=song.name,
        artist=song.artist or None,
        album=song.album or None,
        year=_parse_year(song.year),
        lyrics=lyrics,
        cover_url=song.album_img,
        extra={"source": song.source, "source_id": song.song_id},
    )


def _parse_year(value: str | None) -> int | None:
    if not value:
        return None
    match = next(
        (part for part in str(value).split("-") if part.isdigit() and len(part) == 4),
        None,
    )
    if match is None:
        return None
    try:
        return int(match)
    except ValueError:
        return None


def _timestamp_year_text(value: object) -> str:
    try:
        timestamp = int(str(value)) / 1000
    except (TypeError, ValueError):
        return ""
    try:
        return str(datetime.fromtimestamp(timestamp, UTC).year)
    except (OSError, OverflowError, ValueError):
        return ""


def _optional_string(value: object) -> str | None:
    text = str(value or "").strip()
    return text or None


def _migu_cover_url(song: dict[str, object]) -> str | None:
    images = song.get("imgItems")
    if isinstance(images, list):
        for item in reversed(images):
            if isinstance(item, dict) and (url := _optional_string(item.get("img"))):
                return url
    return _optional_string(song.get("cover"))


def _generate_kw_token(length: int = 32) -> str:
    charset = "0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ"
    return "".join(random.choices(charset, k=length))


def _sha1_and_md5(token: str) -> str:
    hash_value = hashlib.sha1(token.encode("utf-8")).hexdigest()
    return hashlib.md5(hash_value.encode("utf-8")).hexdigest()


def _kuwo_headers(token: str, cross: str) -> dict[str, str]:
    return {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Safari/537.36"
        ),
        "Referer": "http://www.kuwo.cn/",
        "Cross": cross,
        "Cookie": f"Hm_token={token}",
    }
