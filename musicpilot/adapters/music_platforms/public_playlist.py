from __future__ import annotations

import base64
import copy
import hashlib
import hmac
import json
import re
import time
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any, cast
from urllib.parse import parse_qs, urljoin, urlparse, urlunparse

import httpx

from musicpilot.adapters.music_platforms.apple_music import (
    AppleMusicWebTokenProvider,
    apple_music_artwork_url,
    apple_music_description,
    apple_music_headers,
)

QQ_MUSIC_HOSTS = {
    "y.qq.com",
    "i.y.qq.com",
    "m.y.qq.com",
    "c.y.qq.com",
    "c6.y.qq.com",
    "music.qq.com",
}
NETEASE_MUSIC_HOSTS = {
    "music.163.com",
    "y.music.163.com",
    "m.music.163.com",
    "3g.music.163.com",
    "163cn.tv",
}
KUWO_MUSIC_HOSTS = {"kuwo.cn", "www.kuwo.cn", "m.kuwo.cn", "mobile.kuwo.cn"}
KUGOU_MUSIC_HOSTS = {"www.kugou.com", "m.kugou.com", "kugou.com", "h5.kugou.com"}
SPOTIFY_MUSIC_HOSTS = {"open.spotify.com", "spotify.link", "play.spotify.com", "spotify.com"}
APPLE_MUSIC_HOSTS = {"music.apple.com"}


@dataclass
class PublicPlaylistTrack:
    external_id: str
    position: int
    title: str
    artist: str | None = None
    album: str | None = None
    duration: int | None = None
    cover_url: str | None = None
    raw_payload: dict[str, Any] = field(default_factory=dict)


@dataclass
class PublicPlaylist:
    platform: str
    external_id: str
    name: str
    source_url: str
    owner_name: str | None = None
    description: str | None = None
    cover_url: str | None = None
    raw_payload: dict[str, Any] = field(default_factory=dict)
    tracks: list[PublicPlaylistTrack] = field(default_factory=list)


class PublicPlaylistParseError(RuntimeError):
    pass


class UnsupportedPublicPlaylistURL(PublicPlaylistParseError):
    pass


class PublicPlaylistImporter:
    def __init__(
        self,
        client: httpx.AsyncClient | None = None,
        apple_token_provider: AppleMusicWebTokenProvider | None = None,
    ) -> None:
        self._client = client or httpx.AsyncClient(
            timeout=30,
            follow_redirects=True,
            trust_env=False,
        )
        self._owns_client = client is None
        self._apple_token_provider = apple_token_provider or AppleMusicWebTokenProvider(
            self._client
        )

    async def close(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    async def parse(self, playlist_url: str, *, proxy_url: str | None = None) -> PublicPlaylist:
        original_url = playlist_url.strip()
        is_apple_music_playlist = _host_matches(
            _hostname(original_url), APPLE_MUSIC_HOSTS
        ) and "/playlist/" in urlparse(original_url).path
        if is_apple_music_playlist:
            try:
                return await self._parse_url(original_url)
            except httpx.TransportError:
                if not proxy_url:
                    raise
        if proxy_url:
            async with httpx.AsyncClient(
                timeout=30,
                follow_redirects=True,
                proxy=proxy_url,
                trust_env=False,
            ) as client:
                importer = PublicPlaylistImporter(client)
                importer._apple_token_provider.copy_cache_from(self._apple_token_provider)
                try:
                    return await importer.parse(playlist_url)
                finally:
                    self._apple_token_provider.copy_cache_from(importer._apple_token_provider)
        return await self._parse_url(original_url)

    async def _parse_url(self, original_url: str) -> PublicPlaylist:
        if _host_matches(_hostname(original_url), APPLE_MUSIC_HOSTS) and "/playlist/" in urlparse(
            original_url
        ).path:
            url = original_url
        else:
            url = await self._resolve_url(original_url)
        url = _preserve_original_fragment(url, original_url)
        hostname = _hostname(url)
        if _host_matches(hostname, QQ_MUSIC_HOSTS):
            return await self._parse_qq(url)
        if _host_matches(hostname, NETEASE_MUSIC_HOSTS):
            return await self._parse_netease(url)
        if _host_matches(hostname, KUWO_MUSIC_HOSTS):
            return await self._parse_kuwo(url)
        if _host_matches(hostname, KUGOU_MUSIC_HOSTS):
            return await self._parse_kugou(url)
        if _host_matches(hostname, SPOTIFY_MUSIC_HOSTS):
            return await self._parse_spotify(url)
        if _host_matches(hostname, APPLE_MUSIC_HOSTS):
            return await self._parse_apple_music(url)
        raise UnsupportedPublicPlaylistURL("暂不支持该歌单链接。")

    async def _resolve_url(self, playlist_url: str) -> str:
        url = playlist_url.strip()
        if not url:
            raise UnsupportedPublicPlaylistURL("歌单链接不能为空。")
        try:
            response = await self._client.head(url, follow_redirects=True)
            response.raise_for_status()
            return str(response.url)
        except Exception:
            response = await self._client.get(url, follow_redirects=True)
            response.raise_for_status()
            return str(response.url)

    async def _parse_qq(self, playlist_url: str) -> PublicPlaylist:
        parsed = urlparse(playlist_url)
        playlist_id = _first_query_value(parsed.query, "id")
        if not playlist_id:
            playlist_id = _path_id(parsed.path)
        if not playlist_id:
            raise PublicPlaylistParseError("无法识别 QQ 音乐歌单 ID。")
        try:
            numeric_id = int(playlist_id)
        except ValueError as exc:
            raise PublicPlaylistParseError("QQ 音乐歌单 ID 无效。") from exc
        payload = await self._qq_playlist_page(numeric_id, begin=0, count=500)
        playlist_data = payload.get("dirinfo")
        if not isinstance(playlist_data, dict) or not playlist_data.get("id"):
            raise PublicPlaylistParseError("QQ 音乐歌单不存在或无法访问。")
        raw_tracks = payload.get("songlist")
        raw_tracks = raw_tracks if isinstance(raw_tracks, list) else []
        total = _optional_int(payload.get("total_song_num")) or _optional_int(
            playlist_data.get("songnum")
        ) or len(raw_tracks)
        begin = len(raw_tracks)
        while begin < total:
            page = await self._qq_playlist_page(numeric_id, begin=begin, count=500)
            page_tracks = page.get("songlist")
            if not isinstance(page_tracks, list) or not page_tracks:
                break
            raw_tracks.extend(page_tracks)
            begin += len(page_tracks)
        tracks = [
            _qq_track(track, index)
            for index, track in enumerate(raw_tracks, start=1)
            if isinstance(track, dict)
        ]
        return PublicPlaylist(
            platform="qq",
            external_id=playlist_id,
            name=_optional_string(playlist_data.get("title")) or f"playlist-{playlist_id}",
            source_url=playlist_url,
            owner_name=_optional_string(playlist_data.get("host_nick")),
            description=_optional_string(playlist_data.get("desc")),
            cover_url=_optional_string(playlist_data.get("picurl")),
            raw_payload=payload,
            tracks=[track for track in tracks if track is not None],
        )

    async def _qq_playlist_page(
        self,
        playlist_id: int,
        *,
        begin: int,
        count: int,
    ) -> dict[str, Any]:
        response = await self._client.post(
            "https://u.y.qq.com/cgi-bin/musicu.fcg",
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
                "req": {
                    "module": "music.srfDissInfo.aiDissInfo",
                    "method": "uniform_get_Dissinfo",
                    "param": {
                        "disstid": playlist_id,
                        "enc_host_uin": "",
                        "tag": 1,
                        "userinfo": 1,
                        "song_begin": begin,
                        "song_num": count,
                    },
                },
            },
            headers={"Referer": "https://y.qq.com/"},
        )
        response.raise_for_status()
        payload = response.json()
        request = payload.get("req") if isinstance(payload, dict) else None
        if not isinstance(request, dict) or _optional_int(request.get("code")) not in {
            None,
            0,
        }:
            raise PublicPlaylistParseError("QQ 音乐歌单接口返回错误。")
        data = request.get("data")
        if not isinstance(data, dict):
            raise PublicPlaylistParseError("QQ 音乐歌单接口响应格式无效。")
        if _optional_int(data.get("code")) not in {None, 0} or _optional_int(
            data.get("subcode")
        ) not in {None, 0}:
            raise PublicPlaylistParseError("QQ 音乐歌单不存在或无法访问。")
        return data

    async def _parse_netease(self, playlist_url: str) -> PublicPlaylist:
        parsed = urlparse(playlist_url)
        playlist_id = _fragment_query_value(parsed.fragment, "id")
        if not playlist_id:
            playlist_id = _first_query_value(parsed.query, "id")
        if not playlist_id:
            playlist_id = _path_id(parsed.path)
        if not playlist_id:
            raise PublicPlaylistParseError("无法识别网易云音乐歌单 ID。")
        response = await self._client.post(
            "https://music.163.com/api/v6/playlist/detail",
            data={"id": playlist_id},
            headers={"Referer": "https://music.163.com/"},
        )
        response.raise_for_status()
        payload = response.json()
        playlist_data = payload.get("playlist") if isinstance(payload.get("playlist"), dict) else {}
        raw_tracks = playlist_data.get("tracks") if isinstance(playlist_data, dict) else []
        if not raw_tracks:
            track_ids = [
                item.get("id")
                for item in (playlist_data.get("trackIds") or [])
                if isinstance(item, dict) and item.get("id")
            ]
            raw_tracks = await self._netease_track_details(track_ids)
        tracks = [
            _netease_track(track, index)
            for index, track in enumerate(raw_tracks or [], start=1)
            if isinstance(track, dict)
        ]
        return PublicPlaylist(
            platform="netease",
            external_id=playlist_id,
            name=_optional_string(playlist_data.get("name")) or f"playlist-{playlist_id}",
            source_url=playlist_url,
            owner_name=_optional_string(_safe_get(playlist_data, ["creator", "nickname"], None)),
            description=_optional_string(playlist_data.get("description")),
            cover_url=_optional_string(playlist_data.get("coverImgUrl")),
            raw_payload=payload,
            tracks=[track for track in tracks if track is not None],
        )

    async def _netease_track_details(self, track_ids: list[object]) -> list[dict[str, Any]]:
        tracks: list[dict[str, Any]] = []
        for offset in range(0, len(track_ids), 500):
            ids = track_ids[offset : offset + 500]
            response = await self._client.post(
                "https://interface3.music.163.com/api/v3/song/detail",
                data={"c": json.dumps([{"id": item, "v": 0} for item in ids])},
                headers={"Referer": "https://music.163.com/"},
            )
            response.raise_for_status()
            payload = response.json()
            page_tracks = payload.get("songs") if isinstance(payload, dict) else []
            tracks.extend(item for item in page_tracks if isinstance(item, dict))
        return tracks

    async def _parse_kuwo(self, playlist_url: str) -> PublicPlaylist:
        parsed = urlparse(playlist_url)
        playlist_id = _first_query_value(parsed.query, "id")
        if not playlist_id:
            playlist_id = _path_id(parsed.path)
        if not playlist_id:
            raise PublicPlaylistParseError("无法识别酷我音乐歌单 ID。")
        raw_tracks: list[dict[str, Any]] = []
        first_payload: dict[str, Any] = {}
        page = 1
        while True:
            response = await self._client.get(
                "https://m.kuwo.cn/newh5app/wapi/api/www/playlist/playListInfo",
                params={"pid": playlist_id, "pn": page, "rn": 100},
            )
            response.raise_for_status()
            payload = response.json()
            music_list = _safe_get(payload, ["data", "musicList"], []) or []
            if not isinstance(music_list, list) or not music_list:
                break
            if not first_payload:
                first_payload = copy.deepcopy(payload)
            raw_tracks.extend(item for item in music_list if isinstance(item, dict))
            total = _optional_int(_safe_get(payload, ["data", "total"], 0)) or 0
            if total <= len(raw_tracks):
                break
            page += 1
        deduped_tracks = list({str(item.get("musicrid")): item for item in raw_tracks}.values())
        tracks = [
            _kuwo_track(track, index)
            for index, track in enumerate(deduped_tracks, start=1)
            if isinstance(track, dict)
        ]
        return PublicPlaylist(
            platform="kuwo",
            external_id=playlist_id,
            name=_optional_string(_safe_get(first_payload, ["data", "name"], None))
            or f"playlist-{playlist_id}",
            source_url=playlist_url,
            cover_url=_optional_string(_safe_get(first_payload, ["data", "img"], None)),
            raw_payload=first_payload,
            tracks=[track for track in tracks if track is not None],
        )

    async def _parse_kugou(self, playlist_url: str) -> PublicPlaylist:
        parsed = urlparse(playlist_url)
        if "special/single/" not in parsed.path:
            raise UnsupportedPublicPlaylistURL(
                '酷狗歌单链接需要类似 "https://www.kugou.com/yy/special/single/6914288.html"。'
            )
        playlist_id = _first_query_value(parsed.query, "id")
        if not playlist_id:
            playlist_id = _path_id(parsed.path)
        if not playlist_id:
            raise PublicPlaylistParseError("无法识别酷狗音乐歌单 ID。")
        headers = {
            "User-Agent": "Android9-AndroidPhone-11239-18-0-playlist-wifi",
            "Host": "gatewayretry.kugou.com",
            "x-router": "pubsongscdn.kugou.com",
            "mid": "239526275778893399526700786998289824956",
            "dfid": "-",
            "clienttime": str(time.time()).split(".")[0],
        }
        raw_tracks: list[dict[str, Any]] = []
        first_payload: dict[str, Any] = {}
        page = 1
        while True:
            api_url = (
                "http://gatewayretry.kugou.com/v2/get_other_list_file"
                f"?specialid={playlist_id}&need_sort=1&module=CloudMusic&clientver=11239"
                f"&pagesize=300&specalidpgc={playlist_id}&userid=0&page={page}"
                "&type=0&area_code=1&appid=1005"
            )
            response = await self._client.get(
                f"{api_url}&signature={_kugou_signature(api_url)}",
                headers=headers,
            )
            response.raise_for_status()
            payload = response.json()
            page_tracks = _safe_get(payload, ["data", "info"], []) or []
            if not isinstance(page_tracks, list) or not page_tracks:
                break
            if not first_payload:
                first_payload = copy.deepcopy(payload)
            raw_tracks.extend(item for item in page_tracks if isinstance(item, dict))
            total = _optional_int(_safe_get(payload, ["data", "count"], 0)) or 0
            if total <= len(raw_tracks):
                break
            page += 1
        deduped_tracks = list({str(item.get("hash")): item for item in raw_tracks}.values())
        tracks = [
            _kugou_track(track, index)
            for index, track in enumerate(deduped_tracks, start=1)
            if isinstance(track, dict)
        ]
        return PublicPlaylist(
            platform="kugou",
            external_id=playlist_id,
            name=await self._kugou_playlist_name(playlist_url, playlist_id),
            source_url=playlist_url,
            raw_payload=first_payload,
            tracks=[track for track in tracks if track is not None],
        )

    async def _kugou_playlist_name(self, playlist_url: str, playlist_id: str) -> str:
        try:
            response = await self._client.get(
                playlist_url,
                headers={"referer": "https://www.kugou.com/songlist/"},
            )
            response.raise_for_status()
            match = re.search(r"var\s+specialInfo\s*=\s*(\{.*?\});", response.text, re.S)
            if match:
                payload = json.loads(match.group(1))
                name = _optional_string(payload.get("name"))
                if name:
                    return name
        except Exception:
            pass
        return f"playlist-{playlist_id}"

    async def _parse_spotify(self, playlist_url: str) -> PublicPlaylist:
        parsed = urlparse(playlist_url)
        playlist_id = _path_id(parsed.path)
        if not playlist_id:
            raise PublicPlaylistParseError("无法识别 Spotify 歌单 ID。")
        session_data = await self._spotify_session_data()
        secret_data = _spotify_latest_totp_secret()
        token_data = await self._spotify_access_token(
            _spotify_generate_totp(secret_data["secret"]),
            secret_data["version"],
        )
        client_token = await self._spotify_client_token(
            session_data["client_version"],
            str(token_data.get("clientId") or ""),
            session_data["device_id"],
        )
        tracks, first_payload = await self._spotify_all_tracks(
            access_token=str(token_data.get("accessToken") or ""),
            client_token=client_token,
            client_version=session_data["client_version"],
            playlist_id=playlist_id,
            js_pack=session_data["js_pack"],
        )
        parsed_tracks = [
            _spotify_track(track, index)
            for index, track in enumerate(tracks, start=1)
            if isinstance(track, dict)
        ]
        playlist_data = _safe_get(first_payload, ["data", "playlistV2"], {}) or {}
        return PublicPlaylist(
            platform="spotify_public",
            external_id=playlist_id,
            name=_optional_string(playlist_data.get("name")) or f"playlist-{playlist_id}",
            source_url=playlist_url,
            owner_name=_optional_string(
                _safe_get(playlist_data, ["ownerV2", "data", "name"], None)
            ),
            description=_optional_string(playlist_data.get("description")),
            cover_url=_spotify_first_cover(_safe_get(playlist_data, ["images", "items"], None)),
            raw_payload=first_payload,
            tracks=[track for track in parsed_tracks if track is not None],
        )

    async def _parse_apple_music(self, playlist_url: str) -> PublicPlaylist:
        parsed = urlparse(playlist_url)
        path_parts = [part for part in parsed.path.split("/") if part]
        try:
            playlist_part = path_parts.index("playlist")
        except ValueError as exc:
            raise UnsupportedPublicPlaylistURL("该 Apple Music 链接不是歌单分享链接。") from exc
        storefront = path_parts[0].lower() if path_parts else ""
        playlist_id = _optional_string(path_parts[-1])
        if (
            not re.fullmatch(r"[a-z]{2}", storefront)
            or playlist_part + 2 >= len(path_parts)
            or not playlist_id
        ):
            raise PublicPlaylistParseError("无法识别 Apple Music 歌单地区或 ID。")

        token = await self._apple_token_provider.token()
        headers = apple_music_headers(token)
        response = await self._client.get(
            f"https://amp-api.music.apple.com/v1/catalog/{storefront}/playlists/{playlist_id}",
            headers=headers,
            params={"include": "tracks", "limit[tracks]": 100},
        )
        if response.status_code == 401:
            token = await self._apple_token_provider.token(force_refresh=True)
            headers = apple_music_headers(token)
            response = await self._client.get(
                f"https://amp-api.music.apple.com/v1/catalog/{storefront}/playlists/{playlist_id}",
                headers=headers,
                params={"include": "tracks", "limit[tracks]": 100},
            )
        if response.status_code in {401, 403, 404}:
            raise PublicPlaylistParseError(
                "无法访问该 Apple Music 歌单，请确认分享链接可在浏览器中直接打开。"
            )
        response.raise_for_status()
        payload = response.json()
        playlist_data = _safe_get(payload, ["data", 0], {}) or {}
        if not isinstance(playlist_data, dict):
            raise PublicPlaylistParseError("Apple Music 未返回有效的歌单信息。")
        attributes_value = playlist_data.get("attributes")
        attributes = (
            cast(dict[str, Any], attributes_value) if isinstance(attributes_value, dict) else {}
        )
        tracks_relationship = _safe_get(playlist_data, ["relationships", "tracks"], {}) or {}
        raw_tracks = (
            list(tracks_relationship.get("data") or [])
            if isinstance(tracks_relationship, dict)
            else []
        )
        next_url = (
            _optional_string(tracks_relationship.get("next"))
            if isinstance(tracks_relationship, dict)
            else None
        )
        visited_pages: set[str] = set()
        while next_url and next_url not in visited_pages:
            visited_pages.add(next_url)
            page_response = await self._client.get(
                urljoin("https://amp-api.music.apple.com", next_url),
                headers=headers,
            )
            page_response.raise_for_status()
            page_payload = page_response.json()
            page_tracks = page_payload.get("data") if isinstance(page_payload, dict) else []
            if isinstance(page_tracks, list):
                raw_tracks.extend(page_tracks)
            next_url = (
                _optional_string(page_payload.get("next"))
                if isinstance(page_payload, dict)
                else None
            )
        tracks = [
            _apple_music_track(track, index)
            for index, track in enumerate(raw_tracks, start=1)
            if isinstance(track, dict)
        ]
        return PublicPlaylist(
            platform="apple_music",
            external_id=playlist_id,
            name=_optional_string(attributes.get("name")) or f"playlist-{playlist_id}",
            source_url=playlist_url,
            owner_name=_optional_string(attributes.get("curatorName")),
            description=apple_music_description(attributes.get("description")),
            cover_url=apple_music_artwork_url(attributes.get("artwork")),
            raw_payload=payload,
            tracks=[track for track in tracks if track is not None],
        )

    async def _apple_music_developer_token(self, *, force_refresh: bool = False) -> str:
        return await self._apple_token_provider.token(force_refresh=force_refresh)

    async def _spotify_session_data(self) -> dict[str, str]:
        headers = _spotify_common_headers()
        response = await self._client.get("https://open.spotify.com", headers=headers)
        response.raise_for_status()
        cookie_match = re.search(r"sp_t=([^;]+)", response.headers.get("set-cookie", ""))
        device_id = cookie_match.group(1) if cookie_match else ""
        client_version = ""
        app_config = re.search(
            r'<script id="appServerConfig" type="text/plain">([^<]+)</script>',
            response.text,
        )
        if app_config:
            with context_suppress():
                client_version = str(
                    json.loads(base64.b64decode(app_config.group(1))).get("clientVersion")
                    or ""
                )
        if not client_version:
            match = re.search(r'"clientVersion":"([^"]+)"', response.text)
            client_version = match.group(1) if match else ""
        js_pack_relative = ""
        for link in re.findall(r'<script[^>]+src="([^"]+\.js)"[^>]*>', response.text):
            if "web-player/web-player" in link and link.endswith(".js"):
                js_pack_relative = link
                break
        js_pack = (
            js_pack_relative
            if js_pack_relative.startswith("http")
            else f"https://open.spotify.com{js_pack_relative}" if js_pack_relative else ""
        )
        return {"device_id": device_id, "client_version": client_version, "js_pack": js_pack}

    async def _spotify_access_token(self, totp: str, totp_ver: int) -> dict[str, Any]:
        response = await self._client.get(
            "https://open.spotify.com/api/token",
            params={
                "reason": "init",
                "productType": "web-player",
                "totp": totp,
                "totpVer": str(totp_ver),
                "totpServer": totp,
            },
            headers=_spotify_common_headers(),
        )
        response.raise_for_status()
        return response.json()

    async def _spotify_client_token(
        self,
        client_version: str,
        client_id: str,
        device_id: str,
    ) -> str:
        payload = {
            "client_data": {
                "client_version": client_version,
                "client_id": client_id,
                "js_sdk_data": {
                    "device_brand": "unknown",
                    "device_model": "unknown",
                    "os": "windows",
                    "os_version": "NT 10.0",
                    "device_id": device_id,
                    "device_type": "computer",
                },
            }
        }
        headers = _spotify_common_headers()
        headers.update({"Authority": "clienttoken.spotify.com", "Accept": "application/json"})
        response = await self._client.post(
            "https://clienttoken.spotify.com/v1/clienttoken",
            headers=headers,
            json=payload,
        )
        response.raise_for_status()
        return str(_safe_get(response.json(), ["granted_token", "token"], ""))

    async def _spotify_all_tracks(
        self,
        *,
        access_token: str,
        client_token: str,
        client_version: str,
        playlist_id: str,
        js_pack: str,
    ) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        tracks: list[dict[str, Any]] = []
        offset = 0
        limit = 343
        first_payload: dict[str, Any] = {}
        sha256_hash = await self._spotify_sha256_hash(js_pack)
        while True:
            payload = await self._spotify_fetch_playlist(
                access_token=access_token,
                client_token=client_token,
                client_version=client_version,
                playlist_id=playlist_id,
                sha256_hash=sha256_hash,
                offset=offset,
                limit=limit,
            )
            if not first_payload:
                first_payload = copy.deepcopy(payload)
            content = _safe_get(payload, ["data", "playlistV2", "content"], {}) or {}
            items = content.get("items") if isinstance(content, dict) else []
            if not isinstance(items, list) or not items:
                break
            tracks.extend(item for item in items if isinstance(item, dict))
            total_count = _optional_int(content.get("totalCount")) or 0
            if total_count <= offset + limit:
                break
            offset += limit
        return tracks, first_payload

    async def _spotify_fetch_playlist(
        self,
        *,
        access_token: str,
        client_token: str,
        client_version: str,
        playlist_id: str,
        sha256_hash: str,
        offset: int,
        limit: int,
    ) -> dict[str, Any]:
        payload = {
            "operationName": "fetchPlaylist",
            "variables": {
                "uri": f"spotify:playlist:{playlist_id}",
                "offset": offset,
                "limit": limit,
                "enableWatchFeedEntrypoint": False,
            },
            "extensions": {
                "persistedQuery": {
                    "version": 1,
                    "sha256Hash": sha256_hash,
                }
            },
        }
        headers = _spotify_common_headers()
        headers.update(
            {
                "Authorization": f"Bearer {access_token}",
                "Client-Token": client_token,
                "Spotify-App-Version": client_version,
                "Content-Type": "application/json;charset=UTF-8",
            }
        )
        response = await self._client.post(
            "https://api-partner.spotify.com/pathfinder/v2/query",
            headers=headers,
            json=payload,
        )
        response.raise_for_status()
        return response.json()

    async def _spotify_sha256_hash(self, js_pack: str) -> str:
        fallback_hash = "a67612f8c59f4cb4a9723d8e0e0e7b7cb8c5c3d45e3d8c4f5e6f7e8f9a0b1c2d"
        if not js_pack:
            return fallback_hash
        try:
            response = await self._client.get(js_pack, headers=_spotify_common_headers())
            response.raise_for_status()
            raw_hashes = response.text
            str_mapping, hash_mapping = _spotify_extract_mappings(raw_hashes)
            for chunk in _spotify_combine_chunks(str_mapping, hash_mapping):
                with context_suppress():
                    chunk_response = await self._client.get(
                        f"https://open.spotifycdn.com/cdn/build/web-player/{chunk}",
                        headers=_spotify_common_headers(),
                    )
                    raw_hashes += chunk_response.text
            match = re.search(r'"fetchPlaylist","(?:query|mutation)","([^"]+)"', raw_hashes)
            return match.group(1) if match else fallback_hash
        except Exception:
            return fallback_hash


class context_suppress:
    def __enter__(self) -> None:
        return None

    def __exit__(self, *_exc: object) -> bool:
        return True


def _qq_track(item: dict[str, Any], position: int) -> PublicPlaylistTrack | None:
    external_id = _optional_string(item.get("mid") or item.get("songmid") or item.get("id"))
    title = _optional_string(item.get("title") or item.get("songname"))
    if not external_id or not title:
        return None
    singers = item.get("singer") if isinstance(item.get("singer"), list) else []
    album = item.get("album") if isinstance(item.get("album"), dict) else {}
    album_mid = _optional_string(album.get("mid") or item.get("albummid"))
    return PublicPlaylistTrack(
        external_id=external_id,
        position=position,
        title=title,
        artist=", ".join(
            str(singer.get("name")).strip()
            for singer in singers
            if isinstance(singer, dict) and singer.get("name")
        )
        or None,
        album=_optional_string(album.get("title") or item.get("albumname")),
        duration=_optional_int(item.get("interval")),
        cover_url=f"https://y.gtimg.cn/music/photo_new/T002R800x800M000{album_mid}.jpg"
        if album_mid
        else None,
        raw_payload=item,
    )


def _netease_track(item: dict[str, Any], position: int) -> PublicPlaylistTrack | None:
    external_id = _optional_string(item.get("id"))
    title = _optional_string(item.get("name"))
    if not external_id or not title:
        return None
    artists = _safe_get(item, ["ar"], []) or _safe_get(item, ["artists"], []) or []
    album = _safe_get(item, ["al"], {}) or _safe_get(item, ["album"], {}) or {}
    return PublicPlaylistTrack(
        external_id=external_id,
        position=position,
        title=title,
        artist=", ".join(
            str(artist.get("name")).strip()
            for artist in artists
            if isinstance(artist, dict) and artist.get("name")
        )
        or None,
        album=_optional_string(album.get("name")) if isinstance(album, dict) else None,
        duration=_millis_to_seconds(item.get("dt") or item.get("duration")),
        cover_url=_optional_string(album.get("picUrl")) if isinstance(album, dict) else None,
        raw_payload=item,
    )


def _kuwo_track(item: dict[str, Any], position: int) -> PublicPlaylistTrack | None:
    external_id = _optional_string(item.get("MUSICRID") or item.get("musicrid"))
    title = _optional_string(item.get("SONGNAME") or item.get("name") or item.get("songName"))
    if not external_id or not title:
        return None
    return PublicPlaylistTrack(
        external_id=external_id.removeprefix("MUSIC_"),
        position=position,
        title=title,
        artist=_optional_string(item.get("ARTIST") or item.get("artist")),
        album=_optional_string(item.get("ALBUM") or item.get("album")),
        duration=_optional_int(item.get("DURATION") or item.get("duration")),
        cover_url=_optional_string(
            item.get("hts_MVPIC") or item.get("albumpic") or item.get("pic")
        ),
        raw_payload=item,
    )


def _kugou_track(item: dict[str, Any], position: int) -> PublicPlaylistTrack | None:
    external_id = _optional_string(item.get("hash") or item.get("FileHash"))
    title = _optional_string(
        item.get("songname")
        or item.get("SongName")
        or item.get("songname_original")
        or item.get("OriSongName")
        or item.get("filename")
        or item.get("FileName")
        or item.get("name")
        or item.get("Name")
    )
    if not external_id or not title:
        return None
    singers = item.get("singerinfo") or item.get("Singers") or []
    return PublicPlaylistTrack(
        external_id=external_id,
        position=position,
        title=title,
        artist=_optional_string(item.get("singername") or item.get("SingerName"))
        or ", ".join(
            str(singer.get("name")).strip()
            for singer in singers
            if isinstance(singer, dict) and singer.get("name")
        )
        or None,
        album=_optional_string(
            item.get("album_name")
            or item.get("AlbumName")
            or _safe_get(item, ["albuminfo", "name"], None)
        ),
        duration=_optional_int(item.get("duration") or item.get("Duration"))
        or _millis_to_seconds(item.get("timelen")),
        cover_url=_optional_string(
            _safe_get(item, ["trans_param", "union_cover"], None)
            or item.get("cover_url")
            or item.get("Image")
        ),
        raw_payload=item,
    )


def _spotify_track(item: dict[str, Any], position: int) -> PublicPlaylistTrack | None:
    data = _safe_get(item, ["itemV2", "data"], {}) or _safe_get(item, ["item", "data"], {}) or {}
    uri = _optional_string(data.get("uri"))
    external_id = _optional_string(data.get("id")) or (
        uri.split(":")[2] if uri and ":" in uri else None
    )
    title = _optional_string(data.get("name"))
    if not external_id or not title:
        return None
    artists = _safe_get(data, ["artists", "items"], []) or []
    album = data.get("albumOfTrack") if isinstance(data.get("albumOfTrack"), dict) else {}
    return PublicPlaylistTrack(
        external_id=external_id,
        position=position,
        title=title,
        artist=", ".join(
            str(_safe_get(artist, ["profile", "name"], "")).strip()
            for artist in artists
            if isinstance(artist, dict) and _safe_get(artist, ["profile", "name"], None)
        )
        or None,
        album=_optional_string(album.get("name")),
        duration=_millis_to_seconds(
            _safe_get(data, ["duration", "totalMilliseconds"], None)
            or _safe_get(data, ["trackDuration", "totalMilliseconds"], None)
        ),
        cover_url=_spotify_first_cover(_safe_get(album, ["coverArt", "sources"], None)),
        raw_payload=item,
    )


def _apple_music_track(
    item: dict[str, Any], position: int
) -> PublicPlaylistTrack | None:
    attributes_value = item.get("attributes")
    attributes = (
        cast(dict[str, Any], attributes_value) if isinstance(attributes_value, dict) else {}
    )
    external_id = _optional_string(
        item.get("id") or _safe_get(attributes, ["playParams", "catalogId"], None)
    )
    title = _optional_string(attributes.get("name"))
    if not external_id or not title:
        return None
    return PublicPlaylistTrack(
        external_id=external_id,
        position=position,
        title=title,
        artist=_optional_string(attributes.get("artistName")),
        album=_optional_string(attributes.get("albumName")),
        duration=_millis_to_seconds(attributes.get("durationInMillis")),
        cover_url=apple_music_artwork_url(attributes.get("artwork")),
        raw_payload=item,
    )


def _browser_user_agent() -> str:
    return (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36"
    )


def _spotify_common_headers() -> dict[str, str]:
    browser_version = "145"
    return {
        "Content-Type": "application/json",
        "User-Agent": _browser_user_agent(),
        "Sec-Ch-Ua": (
            f'"Chromium";v="{browser_version}", "Not(A:Brand";v="24", '
            f'"Google Chrome";v="{browser_version}"'
        ),
    }


def _spotify_latest_totp_secret(version: int = 61) -> dict[str, Any]:
    version_to_secret = {
        59: [
            123, 105, 79, 70, 110, 59, 52, 125, 60, 49, 80, 70, 89, 75, 80, 86,
            63, 53, 123, 37, 117, 49, 52, 93, 77, 62, 47, 86, 48, 104, 68, 72,
        ],
        60: [
            79, 109, 69, 123, 90, 65, 46, 74, 94, 34, 58, 48, 70, 71, 92, 85,
            122, 63, 91, 64, 87, 87,
        ],
        61: [
            44, 55, 47, 42, 70, 40, 34, 114, 76, 74, 50, 111, 120, 97, 75, 76,
            94, 102, 43, 69, 49, 120, 118, 80, 64, 78,
        ],
    }
    return {"version": version, "secret": version_to_secret[version]}


def _spotify_generate_totp(secret: list[int]) -> str:
    transformed = [entry ^ ((index % 33) + 9) for index, entry in enumerate(secret)]
    hex_str = "".join(str(num) for num in transformed).encode("ascii").hex()
    base32_secret = base64.b64encode(bytes.fromhex(hex_str)).decode("utf-8").replace("=", "")
    base32_bytes = base64.b64decode(base32_secret + "==")
    time_hex = format(int(time.time() / 30), "016x")
    digest = hmac.new(base32_bytes, bytes.fromhex(time_hex), hashlib.sha1).digest()
    offset = digest[19] & 0xF
    code = int.from_bytes(digest[offset : offset + 4], byteorder="big") & 0x7FFFFFFF
    return str(code % 1000000).zfill(6)


def _spotify_extract_mappings(js_code: str) -> tuple[dict[str, str], dict[str, str]]:
    matches = re.compile(r'\{\d+:"[^"]+"(?:,\d+:"[^"]+")*\}').findall(js_code)
    if not matches or len(matches) < 5:
        return {}, {}
    return _spotify_parse_mapping(matches[3]), _spotify_parse_mapping(matches[4])


def _spotify_parse_mapping(match_str: str) -> dict[str, str]:
    return {
        key.strip(): value.strip().strip('"')
        for entry in re.split(r",(?=\d+:)", match_str[1:-1])
        for key, separator, value in [entry.partition(":")]
        if separator
    }


def _spotify_combine_chunks(str_mapping: dict[str, str], hash_mapping: dict[str, str]) -> list[str]:
    chunks = []
    for key, string_value in str_mapping.items():
        if hash_value := hash_mapping.get(key):
            chunks.append(f"{string_value}.{hash_value}.js")
    return chunks


def _spotify_first_cover(images: object) -> str | None:
    if not isinstance(images, list):
        return None
    for item in reversed(images):
        if isinstance(item, dict):
            source = item.get("sources")
            if isinstance(source, list):
                nested = _spotify_first_cover(source)
                if nested:
                    return nested
            url = _optional_string(item.get("url"))
            if url:
                return url
    return None


def _hostname(url: str) -> str:
    return (urlparse(url).hostname or "").lower()


def _preserve_original_fragment(resolved_url: str, original_url: str) -> str:
    resolved = urlparse(resolved_url)
    original = urlparse(original_url.strip())
    if resolved.fragment or not original.fragment:
        return resolved_url
    if _hostname(resolved_url) != _hostname(original_url):
        return resolved_url
    return urlunparse(resolved._replace(fragment=original.fragment))


def _host_matches(hostname: str, candidates: Iterable[str]) -> bool:
    return any(hostname == item or hostname.endswith(f".{item}") for item in candidates)


def _path_id(path: str) -> str | None:
    tail = path.strip("/").split("/")[-1] if path.strip("/") else ""
    tail = tail.removesuffix(".html").removesuffix(".htm")
    return _optional_string(tail)


def _first_query_value(query: str, key: str) -> str | None:
    values = parse_qs(query, keep_blank_values=False).get(key)
    if not values:
        return None
    return _optional_string(values[0])


def _fragment_query_value(fragment: str, key: str) -> str | None:
    if not fragment:
        return None
    parsed = urlparse(fragment)
    return _first_query_value(parsed.query, key) or _first_query_value(fragment, key)


def _kugou_signature(api_url: str) -> str:
    query = api_url.split("?", 1)[1]
    raw = (
        "OIlwieks28dk2k092lksi2UIkp"
        + "".join(sorted(query.split("&")))
        + "OIlwieks28dk2k092lksi2UIkp"
    )
    return hashlib.md5(raw.encode("utf-8")).hexdigest()


def _safe_get(source: object, path: list[object], default: object = None) -> Any:
    value = source
    for key in path:
        if isinstance(key, int):
            if not isinstance(value, list) or len(value) <= key:
                return default
            value = value[key]
            continue
        if not isinstance(value, dict) or key not in value:
            return default
        value = value[key]
    return value


def _optional_string(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _optional_int(value: object) -> int | None:
    if value is None:
        return None
    try:
        return int(float(str(value).strip()))
    except (TypeError, ValueError):
        return None


def _millis_to_seconds(value: object) -> int | None:
    millis = _optional_int(value)
    if millis is None:
        return None
    return int(millis / 1000) if millis > 10000 else millis
