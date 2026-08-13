from __future__ import annotations

import asyncio
import html
import re
from collections.abc import Awaitable, Callable
from typing import Any, cast

import httpx

from musicpilot.ports.discovery import (
    DiscoveryChartItem,
    DiscoveryChartPage,
    DiscoveryItemDetail,
    DiscoveryResourceType,
    DiscoveryTrack,
)

QQ_MUSIC_API_URL = "https://u.y.qq.com/cgi-bin/musicu.fcg"
QQ_MUSIC_PLAYLIST_CHART_URL = (
    "https://c.y.qq.com/splcloud/fcgi-bin/fcg_get_diss_by_tag.fcg"
)


class QQMusicDiscoveryError(RuntimeError):
    pass


class QQMusicResourceNotFound(QQMusicDiscoveryError):
    pass


class QQMusicDiscoveryAdapter:
    def __init__(
        self,
        client: httpx.AsyncClient | None = None,
        proxy_loader: Callable[[], Awaitable[str | None]] | None = None,
    ) -> None:
        self._client = client or httpx.AsyncClient(
            timeout=30,
            follow_redirects=True,
            trust_env=False,
        )
        self._owns_client = client is None
        self._proxy_loader = proxy_loader
        self._proxy_url: str | None = None
        self._proxy_client: httpx.AsyncClient | None = None
        self._proxy_client_lock = asyncio.Lock()

    async def close(self) -> None:
        if self._proxy_client is not None:
            await self._proxy_client.aclose()
            self._proxy_client = None
            self._proxy_url = None
        if self._owns_client:
            await self._client.aclose()

    async def chart(
        self,
        resource_type: DiscoveryResourceType,
        *,
        offset: int = 0,
        limit: int = 20,
    ) -> DiscoveryChartPage:
        if resource_type == "songs":
            return await self._song_chart(offset, limit)
        if resource_type == "albums":
            return await self._album_chart(offset, limit)
        if resource_type == "playlists":
            return await self._playlist_chart(offset, limit)
        raise ValueError(f"Unsupported QQ Music resource type: {resource_type}")

    async def detail(
        self,
        resource_type: DiscoveryResourceType,
        item_id: str,
    ) -> DiscoveryItemDetail:
        if resource_type == "songs":
            return await self._song_detail(item_id)
        if resource_type == "albums":
            return await self._album_detail(item_id)
        if resource_type == "playlists":
            return await self._playlist_detail(item_id)
        raise ValueError(f"Unsupported QQ Music resource type: {resource_type}")

    async def _song_chart(self, offset: int, limit: int) -> DiscoveryChartPage:
        toplists = await self._musicu(
            "musicToplist.ToplistInfoServer",
            "GetAll",
            {},
        )
        hot_chart: dict[str, Any] | None = None
        for group in _list(toplists.get("group")):
            for item in _list(_mapping(group).get("toplist")):
                chart = _mapping(item)
                if _optional_string(chart.get("title")) == "热歌榜":
                    hot_chart = chart
                    break
            if hot_chart is not None:
                break
        if hot_chart is None:
            raise QQMusicDiscoveryError("QQ 音乐热歌榜不存在。")
        top_id = _optional_int(hot_chart.get("topId"))
        if top_id is None:
            raise QQMusicDiscoveryError("QQ 音乐热歌榜 ID 无效。")
        data = await self._musicu(
            "musicToplist.ToplistInfoServer",
            "GetDetail",
            {
                "topid": top_id,
                "offset": offset,
                "num": max(1, min(limit, 100)),
                "period": _optional_string(hot_chart.get("period")) or "",
            },
        )
        items: list[DiscoveryChartItem] = []
        raw_items = _list(data.get("songInfoList"))
        for rank, raw in enumerate(raw_items, start=offset + 1):
            track = _mapping(raw)
            item_id = _optional_string(track.get("id"))
            name = _optional_string(track.get("title") or track.get("name"))
            if not item_id or not name:
                continue
            album = _mapping(track.get("album"))
            items.append(
                DiscoveryChartItem(
                    id=item_id,
                    resource_type="songs",
                    rank=rank,
                    name=name,
                    artist_name=_singer_names(track.get("singer")),
                    artwork_url=_album_artwork(album),
                    release_date=_optional_string(
                        track.get("time_public") or album.get("time_public")
                    ),
                )
            )
        next_offset = offset + len(raw_items)
        has_more = len(raw_items) == max(1, min(limit, 100))
        return DiscoveryChartPage(
            items=tuple(items),
            next_offset=next_offset if has_more else None,
            has_more=has_more,
        )

    async def _album_chart(self, offset: int, limit: int) -> DiscoveryChartPage:
        bounded_limit = max(1, min(limit, 50))
        data = await self._musicu(
            "newalbum.NewAlbumServer",
            "get_new_album_info",
            {"area": 1, "start": offset, "num": bounded_limit},
        )
        items: list[DiscoveryChartItem] = []
        raw_items = _list(data.get("albums"))
        for rank, raw in enumerate(raw_items, start=offset + 1):
            album = _mapping(raw)
            album_mid = _optional_string(album.get("mid"))
            name = _optional_string(album.get("name"))
            if not album_mid or not name:
                continue
            items.append(
                DiscoveryChartItem(
                    id=album_mid,
                    resource_type="albums",
                    rank=rank,
                    name=name,
                    artist_name=_singer_names(album.get("singers")),
                    artwork_url=qq_album_artwork(album_mid),
                    release_date=_optional_string(album.get("release_time")),
                )
            )
        next_offset = offset + len(raw_items)
        total = _optional_int(data.get("total"))
        has_more = next_offset < total if total is not None else len(raw_items) == bounded_limit
        return DiscoveryChartPage(
            items=tuple(items),
            next_offset=next_offset if has_more else None,
            has_more=has_more,
        )

    async def _playlist_chart(self, offset: int, limit: int) -> DiscoveryChartPage:
        bounded_limit = max(1, min(limit, 50))
        payload = await self._get_json(
            QQ_MUSIC_PLAYLIST_CHART_URL,
            params={
                "categoryId": 10000000,
                "sortId": 5,
                "sin": offset,
                "ein": offset + bounded_limit - 1,
                "format": "json",
                "inCharset": "utf8",
                "outCharset": "utf-8",
            },
            headers={"Referer": "https://y.qq.com/"},
        )
        data = _mapping(payload.get("data"))
        items: list[DiscoveryChartItem] = []
        raw_items = _list(data.get("list"))
        for rank, raw in enumerate(raw_items, start=offset + 1):
            playlist = _mapping(raw)
            item_id = _optional_string(playlist.get("dissid"))
            name = _optional_string(playlist.get("dissname"))
            if not item_id or not name:
                continue
            items.append(
                DiscoveryChartItem(
                    id=item_id,
                    resource_type="playlists",
                    rank=rank,
                    name=name,
                    artist_name=_optional_string(
                        _mapping(playlist.get("creator")).get("name")
                    ),
                    artwork_url=_https_url(playlist.get("imgurl")),
                    playcount=_optional_int(playlist.get("listennum")),
                )
            )
        next_offset = offset + len(raw_items)
        total = _optional_int(data.get("sum"))
        has_more = next_offset < total if total is not None else len(raw_items) == bounded_limit
        return DiscoveryChartPage(
            items=tuple(items),
            next_offset=next_offset if has_more else None,
            has_more=has_more,
        )

    async def _song_detail(self, item_id: str) -> DiscoveryItemDetail:
        data = await self._musicu(
            "music.pf_song_detail_svr",
            "get_song_detail_yqq",
            {"song_id": _numeric_id(item_id)},
        )
        track = _mapping(data.get("track_info"))
        if not track or _optional_int(track.get("id")) is None:
            raise QQMusicResourceNotFound("QQ 音乐歌曲不存在。")
        album = _mapping(track.get("album"))
        info = _mapping(data.get("info"))
        return DiscoveryItemDetail(
            id=_optional_string(track.get("id")) or item_id,
            resource_type="songs",
            name=_optional_string(track.get("title") or track.get("name")) or item_id,
            artist_name=_singer_names(track.get("singer")),
            album_name=_optional_string(album.get("title") or album.get("name")),
            description=_info_value(info, "intro"),
            artwork_url=_album_artwork(album),
            external_url=f"https://y.qq.com/n/ryqq/songDetail/{track.get('mid')}",
            release_date=_optional_string(
                track.get("time_public") or album.get("time_public")
            ),
            genres=_info_values(info, "genre"),
            duration_seconds=_optional_int(track.get("interval")),
        )

    async def _album_detail(self, item_id: str) -> DiscoveryItemDetail:
        detail_data, tracks_data = await asyncio.gather(
            self._musicu(
                "music.musichallAlbum.AlbumInfoServer",
                "GetAlbumDetail",
                {"albumMid": item_id},
            ),
            self._musicu(
                "music.musichallAlbum.AlbumSongList",
                "GetAlbumSongList",
                {"albumMid": item_id, "begin": 0, "num": 500},
            ),
        )
        basic = _mapping(detail_data.get("basicInfo"))
        if not basic or not _optional_string(basic.get("albumMid")):
            raise QQMusicResourceNotFound("QQ 音乐专辑不存在。")
        tracks = _tracks_from_wrapped_song_list(tracks_data.get("songList"))
        artist_name = _singer_names(detail_data.get("singer"))
        if not artist_name and tracks:
            artist_name = tracks[0].artist_name
        return DiscoveryItemDetail(
            id=_optional_string(basic.get("albumMid")) or item_id,
            resource_type="albums",
            name=_optional_string(basic.get("albumName")) or item_id,
            artist_name=artist_name,
            description=_optional_string(basic.get("desc")),
            artwork_url=qq_album_artwork(item_id),
            external_url=f"https://y.qq.com/n/ryqq/albumDetail/{item_id}",
            release_date=_optional_string(basic.get("publishDate")),
            track_count=_optional_int(tracks_data.get("totalNum")) or len(tracks),
            tracks=tracks,
        )

    async def _playlist_detail(self, item_id: str) -> DiscoveryItemDetail:
        first_page = await self._playlist_page(item_id, begin=0, count=500)
        playlist = _mapping(first_page.get("dirinfo"))
        if not playlist or _optional_int(playlist.get("id")) is None:
            raise QQMusicResourceNotFound("QQ 音乐歌单不存在。")
        raw_tracks = _list(first_page.get("songlist"))
        total = _optional_int(first_page.get("total_song_num")) or _optional_int(
            playlist.get("songnum")
        ) or len(raw_tracks)
        begin = len(raw_tracks)
        while begin < total:
            page = await self._playlist_page(item_id, begin=begin, count=500)
            page_tracks = _list(page.get("songlist"))
            if not page_tracks:
                break
            raw_tracks.extend(page_tracks)
            begin += len(page_tracks)
        tracks = _tracks(raw_tracks)
        return DiscoveryItemDetail(
            id=item_id,
            resource_type="playlists",
            name=_optional_string(playlist.get("title")) or item_id,
            artist_name=_optional_string(playlist.get("host_nick")),
            description=_clean_html(playlist.get("desc")),
            artwork_url=_https_url(playlist.get("picurl")),
            external_url=f"https://y.qq.com/n/ryqq/playlist/{item_id}",
            track_count=total,
            playcount=_optional_int(playlist.get("listennum")),
            tracks=tracks,
        )

    async def _playlist_page(
        self,
        item_id: str,
        *,
        begin: int,
        count: int,
    ) -> dict[str, Any]:
        data = await self._musicu(
            "music.srfDissInfo.aiDissInfo",
            "uniform_get_Dissinfo",
            {
                "disstid": _numeric_id(item_id),
                "enc_host_uin": "",
                "tag": 1,
                "userinfo": 1,
                "song_begin": begin,
                "song_num": count,
            },
        )
        if _optional_int(data.get("code")) not in {None, 0} or _optional_int(
            data.get("subcode")
        ) not in {None, 0}:
            raise QQMusicDiscoveryError("QQ 音乐歌单接口返回错误。")
        return data

    async def _musicu(
        self,
        module: str,
        method: str,
        params: dict[str, object],
    ) -> dict[str, Any]:
        payload = await self._post_json(
            QQ_MUSIC_API_URL,
            json={
                "comm": {
                    "ct": 24,
                    "cv": 0,
                    "format": "json",
                    "inCharset": "utf-8",
                    "outCharset": "utf-8",
                    "notice": 0,
                    "platform": "yqq.json",
                    "needNewCode": 1,
                    "uin": 0,
                },
                "req": {"module": module, "method": method, "param": params},
            },
            headers={
                "Referer": "https://y.qq.com/",
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/145.0 Safari/537.36"
                ),
            },
        )
        request = _mapping(payload.get("req"))
        if _optional_int(payload.get("code")) not in {None, 0} or _optional_int(
            request.get("code")
        ) not in {None, 0}:
            raise QQMusicDiscoveryError(
                f"QQ 音乐接口返回错误：{request.get('code') or payload.get('code')}"
            )
        data = request.get("data")
        if not isinstance(data, dict):
            raise QQMusicDiscoveryError("QQ 音乐接口响应格式无效。")
        return cast(dict[str, Any], data)

    async def _post_json(self, url: str, **kwargs: Any) -> dict[str, Any]:
        return await self._request_json("POST", url, **kwargs)

    async def _get_json(self, url: str, **kwargs: Any) -> dict[str, Any]:
        return await self._request_json("GET", url, **kwargs)

    async def _request_json(self, method: str, url: str, **kwargs: Any) -> dict[str, Any]:
        try:
            response = await self._client.request(method, url, **kwargs)
        except httpx.TransportError:
            proxy_client = await self._proxy_fallback_client()
            if proxy_client is None:
                raise
            response = await proxy_client.request(method, url, **kwargs)
        response.raise_for_status()
        try:
            payload = response.json()
        except ValueError as exc:
            raise QQMusicDiscoveryError("QQ 音乐接口响应格式无效。") from exc
        if not isinstance(payload, dict):
            raise QQMusicDiscoveryError("QQ 音乐接口响应格式无效。")
        return cast(dict[str, Any], payload)

    async def _proxy_fallback_client(self) -> httpx.AsyncClient | None:
        proxy_url = await self._proxy_loader() if self._proxy_loader is not None else None
        if not proxy_url:
            return None
        if self._proxy_client is not None and self._proxy_url == proxy_url:
            return self._proxy_client
        async with self._proxy_client_lock:
            if self._proxy_client is None or self._proxy_url != proxy_url:
                previous_client = self._proxy_client
                self._proxy_client = httpx.AsyncClient(
                    timeout=30,
                    follow_redirects=True,
                    proxy=proxy_url,
                    trust_env=False,
                )
                self._proxy_url = proxy_url
                if previous_client is not None:
                    await previous_client.aclose()
        return self._proxy_client


def qq_album_artwork(album_mid: str, *, size: int = 800) -> str:
    return f"https://y.gtimg.cn/music/photo_new/T002R{size}x{size}M000{album_mid}.jpg"


def _tracks_from_wrapped_song_list(value: object) -> tuple[DiscoveryTrack, ...]:
    return _tracks([_mapping(item).get("songInfo") for item in _list(value)])


def _tracks(value: object) -> tuple[DiscoveryTrack, ...]:
    tracks: list[DiscoveryTrack] = []
    for position, raw in enumerate(_list(value), start=1):
        item = _mapping(raw)
        item_id = _optional_string(item.get("id") or item.get("songid"))
        name = _optional_string(item.get("title") or item.get("name") or item.get("songname"))
        if not item_id or not name:
            continue
        album = _mapping(item.get("album"))
        album_mid = _optional_string(album.get("mid") or item.get("albummid"))
        tracks.append(
            DiscoveryTrack(
                id=item_id,
                position=position,
                name=name,
                artist_name=_singer_names(item.get("singer")),
                album_name=_optional_string(
                    album.get("title") or album.get("name") or item.get("albumname")
                ),
                artwork_url=qq_album_artwork(album_mid) if album_mid else None,
                duration_seconds=_optional_int(item.get("interval")),
            )
        )
    return tuple(tracks)


def _album_artwork(album: dict[str, Any]) -> str | None:
    album_mid = _optional_string(album.get("mid"))
    return qq_album_artwork(album_mid) if album_mid else None


def _singer_names(value: object) -> str | None:
    if isinstance(value, dict):
        values = value.get("singerList") or value.get("list") or [value]
    else:
        values = value
    names = [
        name
        for raw in _list(values)
        if (name := _optional_string(_mapping(raw).get("name") or _mapping(raw).get("singerName")))
    ]
    return " / ".join(names) or None


def _info_values(info: dict[str, Any], key: str) -> tuple[str, ...]:
    content = _list(_mapping(info.get(key)).get("content"))
    return tuple(
        value
        for raw in content
        if (value := _optional_string(_mapping(raw).get("value")))
    )


def _info_value(info: dict[str, Any], key: str) -> str | None:
    values = _info_values(info, key)
    return "\n".join(values) or None


def _clean_html(value: object) -> str | None:
    text = _optional_string(value)
    if not text:
        return None
    return html.unescape(re.sub(r"<[^>]+>", "", text)).strip() or None


def _https_url(value: object) -> str | None:
    url = _optional_string(value)
    if not url:
        return None
    if url.startswith("//"):
        return f"https:{url}"
    if url.startswith("http://"):
        return url.replace("http://", "https://", 1)
    return url


def _numeric_id(value: str) -> int:
    try:
        return int(value)
    except ValueError as exc:
        raise QQMusicResourceNotFound("QQ 音乐资源 ID 无效。") from exc


def _mapping(value: object) -> dict[str, Any]:
    return cast(dict[str, Any], value) if isinstance(value, dict) else {}


def _list(value: object) -> list[Any]:
    return cast(list[Any], value) if isinstance(value, list) else []


def _optional_string(value: object) -> str | None:
    text = str(value).strip() if value is not None else ""
    return text or None


def _optional_int(value: object) -> int | None:
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None
