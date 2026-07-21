from __future__ import annotations

import asyncio
import contextlib
import logging
import time
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from html import escape
from secrets import token_urlsafe
from typing import Any, TypeVar
from urllib.parse import urlparse

import httpx
from aiogram.__meta__ import __version__ as aiogram_version
from aiogram.client.session.aiohttp import AiohttpSession
from aiohttp import ClientSession
from aiohttp.hdrs import USER_AGENT
from aiohttp.http import SERVER_SOFTWARE

from musicpilot.core.events import NotifyEvent, SearchResult
from musicpilot.infra.api.schemas import MediaCandidateResponse

logger = logging.getLogger(__name__)

TELEGRAM_BOT_COMMANDS = (
    ("downloading", "查看当前下载任务"),
    ("info", "查看 MusicPilot 概览"),
    ("playlist", "查看或导入歌单"),
    ("playlist_sync", "同步系统歌单到音乐库"),
    ("musicservice_refresh", "刷新音乐服务媒体库"),
)

MediaSearch = Callable[[str, str | None], Awaitable[list[MediaCandidateResponse]]]
TorrentSearch = Callable[[MediaCandidateResponse], Awaitable[list[SearchResult]]]
DownloadSubmitter = Callable[[SearchResult, MediaCandidateResponse], Awaitable[None]]


@dataclass(frozen=True, slots=True)
class TelegramDownloadTask:
    name: str
    submitted_at: datetime | None
    progress: float


@dataclass(frozen=True, slots=True)
class TelegramDashboard:
    app_version: str
    library_songs: int
    library_albums: int
    library_artists: int
    library_recent_7d_songs: int
    downloads_active: int
    downloads_completed_7d: int
    downloads_failed: int
    playlists: int
    playlist_pending_tracks: int
    tasks_waiting: int
    tasks_running: int
    tasks_failed: int


@dataclass(frozen=True, slots=True)
class TelegramPlaylist:
    id: int | None
    name: str
    platform: str
    track_count: int
    owner_name: str | None = None
    description: str | None = None
    import_token: str | None = None


@dataclass(frozen=True, slots=True)
class TelegramMusicServiceUser:
    id: str
    name: str
    username: str = ""


@dataclass(frozen=True, slots=True)
class TelegramPlaylistSyncSummary:
    service_name: str
    username: str
    public: bool
    playlists_synced: int
    tracks_synced: int
    skipped_playlists: int
    failed_playlists: int


ActiveDownloads = Callable[[], Awaitable[list[TelegramDownloadTask]]]
DashboardProvider = Callable[[], Awaitable[TelegramDashboard]]
PlaylistProvider = Callable[[], Awaitable[list[TelegramPlaylist]]]
PlaylistPreviewer = Callable[[str], Awaitable[TelegramPlaylist]]
PlaylistImporter = Callable[[str], Awaitable[TelegramPlaylist]]
MusicServiceRefresher = Callable[[], Awaitable[str]]
MusicServiceUsersProvider = Callable[[], Awaitable[list[TelegramMusicServiceUser]]]
PlaylistSynchronizer = Callable[[int, str, bool], Awaitable[TelegramPlaylistSyncSummary]]
T = TypeVar("T")


@dataclass(slots=True)
class _Interaction:
    chat_id: int
    message_id: int
    media: list[MediaCandidateResponse]
    created_at: float
    stage: str = "media"
    page: int = 0
    selected_media: MediaCandidateResponse | None = None
    torrents: list[SearchResult] = field(default_factory=list)


class TelegramAiohttpSession(AiohttpSession):
    def __init__(self, proxy: str | None) -> None:
        scheme = urlparse(proxy or "").scheme.casefold()
        self._http_proxy = proxy if scheme in {"http", "https"} else None
        super().__init__(proxy=None if self._http_proxy else proxy)

    async def create_session(self) -> ClientSession:
        if self._http_proxy is None:
            return await super().create_session()
        if self._should_reset_connector:
            await self.close()
        if self._session is None or self._session.closed:
            self._session = ClientSession(
                connector=self._connector_type(**self._connector_init),
                headers={USER_AGENT: f"{SERVER_SOFTWARE} aiogram/{aiogram_version}"},
                proxy=self._http_proxy,
            )
            self._should_reset_connector = False
        return self._session


class TelegramBotAdapter:
    _MEDIA_PAGE_SIZE = 5
    _TORRENT_PAGE_SIZE = 10
    _SESSION_TTL_SECONDS = 30 * 60

    def __init__(
        self,
        *,
        token: str,
        chat_ids: tuple[int, ...] = (),
        proxy: str | None = None,
        search_media: MediaSearch,
        search_torrents: TorrentSearch,
        submit_download: DownloadSubmitter,
        list_active_downloads: ActiveDownloads,
        dashboard: DashboardProvider,
        list_playlists: PlaylistProvider,
        preview_playlist: PlaylistPreviewer,
        import_playlist: PlaylistImporter,
        refresh_music_service: MusicServiceRefresher,
        list_music_service_users: MusicServiceUsersProvider,
        sync_playlists: PlaylistSynchronizer,
    ) -> None:
        self.token = token
        self.chat_ids = chat_ids
        self.proxy = proxy
        self.search_media = search_media
        self.search_torrents = search_torrents
        self.submit_download = submit_download
        self.list_active_downloads = list_active_downloads
        self.dashboard = dashboard
        self.list_playlists = list_playlists
        self.preview_playlist = preview_playlist
        self.import_playlist = import_playlist
        self.refresh_music_service = refresh_music_service
        self.list_music_service_users = list_music_service_users
        self.sync_playlists = sync_playlists
        self._bot: Any = None
        self._dispatcher: Any = None
        self._task: asyncio.Task[None] | None = None
        self._sessions: dict[str, _Interaction] = {}
        self._session_messages: dict[tuple[int, int], str] = {}

    @property
    def name(self) -> str:
        return "telegram"

    async def start(self) -> None:
        from aiogram import Bot, Dispatcher, F
        from aiogram.filters import Command
        from aiogram.types import BotCommand, CallbackQuery, Message

        self._bot = Bot(self.token, session=TelegramAiohttpSession(self.proxy))
        self._dispatcher = Dispatcher()
        await self._sync_commands(BotCommand)

        async def handle_text(message: Message) -> None:
            if not message.text:
                return
            query = message.text.strip()
            if not query or query.startswith("/"):
                return
            logger.info("Telegram message received: chat=%s, type=text", _chat_log_label(message))
            if query.isdigit() and await self._handle_reply_selection(message, int(query)):
                return
            await self._start_media_search(message, query)

        async def handle_downloading(message: Message) -> None:
            logger.info(
                "Telegram command received: chat=%s, command=downloading",
                _chat_log_label(message),
            )
            tasks = await self.list_active_downloads()
            if not tasks:
                await message.answer("<b>当前下载任务</b>\n暂无活跃下载。", parse_mode="HTML")
                logger.info(
                    "Telegram command completed: chat=%s, command=downloading, tasks=0",
                    _chat_log_label(message),
                )
                return
            lines = ["<b>当前下载任务</b>"]
            for index, task in enumerate(tasks, start=1):
                submitted_at = (
                    task.submitted_at.strftime("%Y-%m-%d %H:%M") if task.submitted_at else "未知"
                )
                lines.extend(
                    (
                        f"\n{index}. <b>{escape(_short(task.name, 240))}</b>",
                        f"下载时间：{submitted_at}",
                        f"进度：{_progress_text(task.progress)}",
                    )
                )
            await message.answer("\n".join(lines), parse_mode="HTML")
            logger.info(
                "Telegram command completed: chat=%s, command=downloading, tasks=%d",
                _chat_log_label(message),
                len(tasks),
            )

        async def handle_info(message: Message) -> None:
            logger.info(
                "Telegram command received: chat=%s, command=info",
                _chat_log_label(message),
            )
            info = await self.dashboard()
            text = "\n".join(
                (
                    "<b>MusicPilot 概览</b>",
                    "",
                    "<b>音乐库</b>",
                    (
                        f"歌曲 {info.library_songs} · 专辑 {info.library_albums} "
                        f"· 歌手 {info.library_artists}"
                    ),
                    f"近 7 天新增 {info.library_recent_7d_songs} 首",
                    "",
                    "<b>下载</b>",
                    (
                        f"活跃 {info.downloads_active} · 近 7 天完成 "
                        f"{info.downloads_completed_7d} · 失败 {info.downloads_failed}"
                    ),
                    "",
                    "<b>歌单与队列</b>",
                    f"歌单 {info.playlists} · 待处理曲目 {info.playlist_pending_tracks}",
                    (
                        f"任务：运行中 {info.tasks_running} · 等待 {info.tasks_waiting} "
                        f"· 失败 {info.tasks_failed}"
                    ),
                )
            )
            await message.answer(
                f"{text}\n\n系统版本：{escape(info.app_version)}",
                parse_mode="HTML",
            )
            logger.info(
                "Telegram command completed: chat=%s, command=info",
                _chat_log_label(message),
            )

        async def handle_playlist(message: Message) -> None:
            arguments = (message.text or "").partition(" ")[2].strip()
            if not arguments:
                await self._list_playlists(message)
                return
            await self._preview_playlist(message, arguments)

        async def handle_musicservice_refresh(message: Message) -> None:
            logger.info(
                "Telegram command received: chat=%s, command=musicservice_refresh",
                _chat_log_label(message),
            )
            await message.answer("正在请求音乐服务扫描…")
            try:
                server_name = await self.refresh_music_service()
            except Exception as exc:  # noqa: BLE001
                logger.exception("Telegram music service refresh failed")
                await message.answer(
                    f"音乐服务扫描请求失败：{escape(_error_text(exc))}",
                    parse_mode="HTML",
                )
                return
            await message.answer(
                f"已请求 <b>{escape(_short(server_name, 120))}</b> 扫描音乐媒体库。",
                parse_mode="HTML",
            )

        async def handle_playlist_sync(message: Message) -> None:
            await self._show_playlist_sync_playlists(message)

        async def handle_callback(callback: CallbackQuery) -> None:
            data = callback.data or ""
            parts = data.split(":")
            if len(parts) != 4 or parts[0] != "tg":
                return
            message = callback.message
            if parts[1] == "p":
                if message is None or not hasattr(message, "message_id"):
                    await callback.answer("该操作已失效。", show_alert=True)
                    return
                await callback.answer()
                await self._import_playlist(message, parts[2])
                return
            if parts[1] == "u":
                if message is None or not hasattr(message, "message_id"):
                    await callback.answer("该操作已失效。", show_alert=True)
                    return
                await callback.answer()
                await self._show_playlist_sync_visibility(message, parts[2], parts[3])
                return
            if parts[1] == "v":
                if message is None or not hasattr(message, "message_id"):
                    await callback.answer("该操作已失效。", show_alert=True)
                    return
                await callback.answer()
                user_id, separator, playlist_id_text = parts[2].partition("|")
                if not separator or not playlist_id_text.isdigit():
                    await message.edit_text("无效的歌单选择。", reply_markup=None)
                    return
                await self._sync_playlists(
                    message,
                    int(playlist_id_text),
                    user_id,
                    parts[3] == "1",
                )
                return
            if parts[1] == "l":
                if message is None or not hasattr(message, "message_id"):
                    await callback.answer("该操作已失效。", show_alert=True)
                    return
                await callback.answer()
                await self._show_playlist_sync_users(message, parts[2])
                return
            if message is None or not hasattr(message, "message_id"):
                await callback.answer("该操作已失效。", show_alert=True)
                return
            session = self._get_session(parts[2], message.chat.id, message.message_id)
            if session is None:
                await callback.answer("该搜索已过期，请重新发送歌曲名。", show_alert=True)
                return
            try:
                value = int(parts[3])
            except ValueError:
                await callback.answer("无效的选择。", show_alert=True)
                return
            logger.info(
                "Telegram callback received: chat=%s, action=%s",
                _chat_log_label(message),
                parts[1],
            )
            await callback.answer()
            if parts[1] == "m":
                await self._change_page(message, session, value, "media")
            elif parts[1] == "t":
                await self._change_page(message, session, value, "torrent")
            elif parts[1] == "s":
                await self._select_media(message, session, value)
            elif parts[1] == "d":
                await self._select_torrent(message, session, value)
            logger.info(
                "Telegram callback completed: chat=%s, action=%s",
                _chat_log_label(message),
                parts[1],
            )

        self._dispatcher.message.register(handle_downloading, Command("downloading"))
        self._dispatcher.message.register(handle_info, Command("info"))
        self._dispatcher.message.register(handle_playlist, Command("playlist"))
        self._dispatcher.message.register(
            handle_musicservice_refresh,
            Command("musicservice_refresh"),
        )
        self._dispatcher.message.register(handle_playlist_sync, Command("playlist_sync"))
        self._dispatcher.callback_query.register(handle_callback, F.data.startswith("tg:"))
        self._dispatcher.message.register(handle_text, F.text)
        self._task = asyncio.create_task(
            self._run_polling(),
            name="musicpilot-telegram-bot",
        )

    async def _sync_commands(self, bot_command_type: type[Any]) -> None:
        if self._bot is None:
            return
        try:
            await self._bot.set_my_commands(
                [
                    bot_command_type(command=name, description=description)
                    for name, description in TELEGRAM_BOT_COMMANDS
                ]
            )
            logger.info(
                "Telegram command menu synchronized: commands=%d",
                len(TELEGRAM_BOT_COMMANDS),
            )
        except Exception:
            logger.exception("Unable to synchronize Telegram command menu")

    async def _list_playlists(self, message: Any) -> None:
        logger.info(
            "Telegram command received: chat=%s, command=playlist",
            _chat_log_label(message),
        )
        playlists = await self.list_playlists()
        if not playlists:
            await message.answer("<b>系统歌单</b>\n暂无已导入歌单。", parse_mode="HTML")
            return
        lines = [f"<b>系统歌单（{len(playlists)}）</b>"]
        for index, playlist in enumerate(playlists, start=1):
            owner = f" · {escape(_short(playlist.owner_name, 80))}" if playlist.owner_name else ""
            lines.append(
                f"\n{index}. <b>{escape(_short(playlist.name, 180))}</b>\n"
                f"{escape(playlist.platform)}{owner} · {playlist.track_count} 首"
            )
        await message.answer(_short("\n".join(lines), 4000), parse_mode="HTML")

    async def _preview_playlist(self, message: Any, url: str) -> None:
        await message.answer("正在解析歌单链接…")
        try:
            playlist = await self.preview_playlist(url)
        except Exception as exc:  # noqa: BLE001
            logger.exception("Telegram playlist parsing failed")
            await message.answer(f"歌单解析失败：{escape(_error_text(exc))}", parse_mode="HTML")
            return
        if not playlist.import_token:
            await message.answer("歌单解析失败：未生成导入凭据。")
            return
        from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

        lines = [
            "<b>歌单解析结果</b>",
            f"名称：<b>{escape(_short(playlist.name, 240))}</b>",
            f"平台：{escape(playlist.platform)}",
            f"曲目：{playlist.track_count} 首",
        ]
        if playlist.owner_name:
            lines.append(f"创建者：{escape(_short(playlist.owner_name, 120))}")
        if playlist.description:
            lines.append(f"简介：{escape(_short(playlist.description, 500))}")
        await message.answer(
            "\n".join(lines),
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(
                            text="导入",
                            callback_data=f"tg:p:{playlist.import_token}:0",
                        )
                    ]
                ]
            ),
        )

    async def _import_playlist(self, message: Any, import_token: str) -> None:
        await message.edit_text("正在导入歌单…", reply_markup=None)
        try:
            playlist = await self.import_playlist(import_token)
        except Exception as exc:  # noqa: BLE001
            logger.exception("Telegram playlist import failed")
            await message.edit_text(
                f"歌单导入失败：{escape(_error_text(exc))}",
                parse_mode="HTML",
                reply_markup=None,
            )
            return
        await message.edit_text(
            "<b>歌单已导入</b>\n"
            f"名称：<b>{escape(_short(playlist.name, 240))}</b>\n"
            f"平台：{escape(playlist.platform)} · 曲目：{playlist.track_count} 首",
            parse_mode="HTML",
            reply_markup=None,
        )

    async def _show_playlist_sync_playlists(self, message: Any) -> None:
        from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

        playlists = await self.list_playlists()
        selectable = [playlist for playlist in playlists if playlist.id is not None]
        if not selectable:
            await message.answer("暂无可同步的系统歌单。")
            return
        lines = [f"<b>系统歌单（{len(selectable)}）</b>", "请选择要同步的歌单："]
        buttons = []
        for index, playlist in enumerate(selectable, start=1):
            lines.append(f"{index}. {escape(_short(playlist.name, 180))}")
            buttons.append(
                InlineKeyboardButton(
                    text=str(index),
                    callback_data=f"tg:l:{playlist.id}:0",
                )
            )
        rows = [buttons[index : index + 5] for index in range(0, len(buttons), 5)]
        await message.answer(
            _short("\n".join(lines), 4000),
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
        )

    async def _show_playlist_sync_users(self, message: Any, playlist_id: str) -> None:
        from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

        if not playlist_id.isdigit():
            await message.edit_text("无效的歌单选择。", reply_markup=None)
            return
        users = await self.list_music_service_users()
        if not users:
            await message.edit_text("未配置已启用的音乐库用户。", reply_markup=None)
            return
        rows = []
        for user in users:
            label = _short(f"同步到 {user.name}（{user.username or '-'}）", 60)
            rows.append(
                [
                    InlineKeyboardButton(
                        text=label,
                        callback_data=f"tg:u:{user.id}:{playlist_id}",
                    )
                ]
            )
        await message.edit_text(
            "<b>同步歌单</b>\n请选择音乐库用户：",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
        )

    async def _show_playlist_sync_visibility(
        self,
        message: Any,
        user_id: str,
        playlist_id: str,
    ) -> None:
        from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

        users = await self.list_music_service_users()
        user = next((item for item in users if item.id == user_id), None)
        if user is None or not playlist_id.isdigit():
            await message.edit_text("音乐库用户不存在或已停用。", reply_markup=None)
            return
        await message.edit_text(
            "<b>同步系统歌单</b>\n"
            f"目标：{escape(_short(user.name, 120))}"
            f"（{escape(_short(user.username or '-', 80))}）\n"
            "请选择同步歌单的可见性：",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(
                            text="公开",
                            callback_data=f"tg:v:{user.id}|{playlist_id}:1",
                        ),
                        InlineKeyboardButton(
                            text="私有",
                            callback_data=f"tg:v:{user.id}|{playlist_id}:0",
                        ),
                    ]
                ]
            ),
        )

    async def _sync_playlists(
        self,
        message: Any,
        playlist_id: int,
        user_id: str,
        public: bool,
    ) -> None:
        visibility = "公开" if public else "私有"
        await message.edit_text(f"正在将系统歌单同步为{visibility}歌单…", reply_markup=None)
        try:
            summary = await self.sync_playlists(playlist_id, user_id, public)
        except Exception as exc:  # noqa: BLE001
            logger.exception("Telegram playlist synchronization failed")
            await message.edit_text(
                f"歌单同步失败：{escape(_error_text(exc))}",
                parse_mode="HTML",
                reply_markup=None,
            )
            return
        await message.edit_text(
            "<b>歌单同步完成</b>\n"
            f"目标：{escape(_short(summary.service_name, 120))}"
            f"（{escape(_short(summary.username or '-', 80))}）\n"
            f"可见性：{'公开' if summary.public else '私有'}\n"
            f"已同步：{summary.playlists_synced} 个歌单，{summary.tracks_synced} 首歌曲\n"
            f"跳过：{summary.skipped_playlists} 个，失败：{summary.failed_playlists} 个",
            parse_mode="HTML",
            reply_markup=None,
        )

    async def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
            self._task = None
        if self._bot is not None:
            await self._bot.session.close()
            self._bot = None
        self._dispatcher = None

    async def send_notification(self, event: NotifyEvent) -> None:
        if self._bot is None:
            return
        text = _telegram_message_text(event)
        logger.info("Telegram notification sending: recipients=%d", len(self.chat_ids))
        for chat_id in self.chat_ids:
            await self._bot.send_message(chat_id, text, parse_mode="HTML")
        logger.info("Telegram notification completed: recipients=%d", len(self.chat_ids))

    async def notify(self, event: NotifyEvent) -> None:
        await self.send_notification(event)

    async def _start_media_search(self, message: Any, query: str) -> None:
        title, artist = _split_query(query)
        logger.info("Telegram media search started: chat=%s", _chat_log_label(message))
        try:
            candidates = await self.search_media(title, artist)
        except Exception as exc:  # noqa: BLE001
            logger.exception("Telegram media search failed")
            await message.answer(f"媒体搜索失败：{escape(_error_text(exc))}", parse_mode="HTML")
            return
        if not candidates:
            await message.answer("没有找到匹配的媒体信息，请调整歌名或歌手后重试。")
            logger.info(
                "Telegram media search completed: chat=%s, candidates=0",
                _chat_log_label(message),
            )
            return
        response = await message.answer("正在整理媒体搜索结果…")
        session_id = token_urlsafe(6)
        session = _Interaction(
            chat_id=response.chat.id,
            message_id=response.message_id,
            media=candidates,
            created_at=time.monotonic(),
        )
        self._store_session(session_id, session)
        await self._render_media(response, session_id, session)
        logger.info(
            "Telegram media search completed: chat=%s, candidates=%d",
            _chat_log_label(message),
            len(candidates),
        )

    async def _handle_reply_selection(self, message: Any, selection: int) -> bool:
        reply = getattr(message, "reply_to_message", None)
        if reply is None:
            return False
        session_id = self._session_messages.get((message.chat.id, reply.message_id))
        if session_id is None:
            return False
        session = self._get_session(session_id, message.chat.id, reply.message_id)
        if session is None:
            await message.answer("该搜索已过期，请重新发送歌曲名。")
            return True
        if session.stage == "media":
            await self._select_media(reply, session, self._page_selection_index(session, selection))
            return True
        if session.stage == "torrent":
            await self._select_torrent(
                reply, session, self._page_selection_index(session, selection)
            )
            return True
        return False

    async def _change_page(
        self,
        message: Any,
        session: _Interaction,
        page: int,
        stage: str,
    ) -> None:
        if session.stage != stage:
            return
        values: Sequence[object] = session.media if stage == "media" else session.torrents
        page_size = self._MEDIA_PAGE_SIZE if stage == "media" else self._TORRENT_PAGE_SIZE
        pages = _page_count(len(values), page_size)
        if not 0 <= page < pages:
            return
        session.page = page
        session_id = self._session_messages[(session.chat_id, session.message_id)]
        if stage == "media":
            await self._render_media(message, session_id, session)
        else:
            await self._render_torrents(message, session_id, session)

    async def _select_media(self, message: Any, session: _Interaction, index: int) -> None:
        if session.stage != "media" or not 0 <= index < len(session.media):
            return
        selected = session.media[index]
        session.selected_media = selected
        session.stage = "searching_torrents"
        logger.info("Telegram torrent search started: chat=%s", _chat_log_label(message))
        await message.edit_text("正在搜索可下载的种子…", reply_markup=None)
        try:
            torrents = await self.search_torrents(selected)
        except Exception as exc:  # noqa: BLE001
            logger.exception("Telegram torrent search failed")
            session.stage = "media"
            session_id = self._session_messages[(session.chat_id, session.message_id)]
            await self._render_media(message, session_id, session)
            await message.answer(f"种子搜索失败：{escape(_error_text(exc))}", parse_mode="HTML")
            return
        if not torrents:
            session.stage = "media"
            session_id = self._session_messages[(session.chat_id, session.message_id)]
            await self._render_media(message, session_id, session)
            await message.answer("没有找到可下载的种子，请选择其他媒体信息。")
            logger.info(
                "Telegram torrent search completed: chat=%s, results=0",
                _chat_log_label(message),
            )
            return
        session.torrents = torrents
        session.stage = "torrent"
        session.page = 0
        session_id = self._session_messages[(session.chat_id, session.message_id)]
        await self._render_torrents(message, session_id, session)
        logger.info(
            "Telegram torrent search completed: chat=%s, results=%d",
            _chat_log_label(message),
            len(torrents),
        )

    async def _select_torrent(self, message: Any, session: _Interaction, index: int) -> None:
        if (
            session.stage != "torrent"
            or session.selected_media is None
            or not 0 <= index < len(session.torrents)
        ):
            return
        torrent = session.torrents[index]
        logger.info("Telegram download submission started: chat=%s", _chat_log_label(message))
        await message.edit_text(
            f"正在提交下载：<b>{escape(_short(torrent.title, 240))}</b>",
            parse_mode="HTML",
            reply_markup=None,
        )
        try:
            await self.submit_download(torrent, session.selected_media)
        except Exception as exc:  # noqa: BLE001
            logger.exception("Telegram download submission failed")
            session_id = self._session_messages[(session.chat_id, session.message_id)]
            await self._render_torrents(message, session_id, session)
            await message.answer(f"下载提交失败：{escape(_error_text(exc))}", parse_mode="HTML")
            return
        self._remove_session(session.chat_id, session.message_id)
        await message.edit_text(
            f"<b>已提交下载</b>\n{escape(_short(torrent.title, 600))}",
            parse_mode="HTML",
            reply_markup=None,
        )
        logger.info("Telegram download submission completed: chat=%s", _chat_log_label(message))

    async def _run_polling(self) -> None:
        logger.info(
            "Telegram bot polling starting: proxy=%s, recipients=%d",
            "on" if self.proxy else "off",
            len(self.chat_ids),
        )
        try:
            await self._dispatcher.start_polling(self._bot)
        except asyncio.CancelledError:
            logger.info("Telegram bot polling stopped")
            raise
        except Exception:  # noqa: BLE001
            logger.exception("Telegram bot polling stopped unexpectedly")

    async def _render_media(self, message: Any, session_id: str, session: _Interaction) -> None:
        page_items = _page_items(session.media, session.page, self._MEDIA_PAGE_SIZE)
        pages = _page_count(len(session.media), self._MEDIA_PAGE_SIZE)
        lines = [f"<b>媒体搜索结果（第 {session.page + 1}/{pages} 页）</b>"]
        for index, item in page_items:
            artist = item.artist or "未知歌手"
            albums = item.albums or ([item.album] if item.album else [])
            album_text = " / ".join(_short(album, 80) for album in albums[:5]) or "未知专辑"
            lines.extend(
                (
                    (
                        f"\n{index + 1}. <b>{escape(_short(item.title, 180))} - "
                        f"{escape(_short(artist, 120))}</b>"
                    ),
                    f"专辑：{escape(album_text)}",
                )
            )
            if item.exists_in_library:
                lines.append("【已在库】")
        await message.edit_text(
            "\n".join(lines),
            parse_mode="HTML",
            reply_markup=self._media_keyboard(session_id, session, len(session.media)),
        )

    async def _render_torrents(self, message: Any, session_id: str, session: _Interaction) -> None:
        page_items = _page_items(session.torrents, session.page, self._TORRENT_PAGE_SIZE)
        pages = _page_count(len(session.torrents), self._TORRENT_PAGE_SIZE)
        lines = [f"<b>种子搜索结果（第 {session.page + 1}/{pages} 页）</b>"]
        for index, item in page_items:
            source = item.source or "未知"
            published_at = item.published_at or "未知"
            lines.extend(
                (
                    f"\n{index + 1}. <b>{escape(_short(item.title, 220))}</b>",
                    (
                        f"站点：{escape(_short(source, 80))} "
                        f"· 大小：{_format_size(item.size_bytes)}"
                    ),
                    (
                        f"发布时间：{escape(_short(published_at, 80))} · 做种：{item.seeders} "
                        f"· 下载：{item.leechers}"
                    ),
                )
            )
            if item.promotion:
                lines.append(f"促销：{escape(_short(item.promotion, 80))}")
        await message.edit_text(
            "\n".join(lines),
            parse_mode="HTML",
            reply_markup=self._torrent_keyboard(session_id, session, len(session.torrents)),
        )

    def _media_keyboard(self, session_id: str, session: _Interaction, total: int) -> object:
        return self._keyboard(session_id, session, total, self._MEDIA_PAGE_SIZE, "s", "m")

    def _torrent_keyboard(self, session_id: str, session: _Interaction, total: int) -> object:
        return self._keyboard(session_id, session, total, self._TORRENT_PAGE_SIZE, "d", "t")

    def _keyboard(
        self,
        session_id: str,
        session: _Interaction,
        total: int,
        page_size: int,
        select_action: str,
        page_action: str,
    ) -> object:
        from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

        start = session.page * page_size
        buttons = [
            InlineKeyboardButton(
                text=str(number),
                callback_data=f"tg:{select_action}:{session_id}:{start + number - 1}",
            )
            for number in range(1, min(page_size, total - start) + 1)
        ]
        rows = [buttons[index : index + 5] for index in range(0, len(buttons), 5)]
        pages = _page_count(total, page_size)
        navigation = []
        if session.page > 0:
            navigation.append(
                InlineKeyboardButton(
                    text="上一页",
                    callback_data=f"tg:{page_action}:{session_id}:{session.page - 1}",
                )
            )
        if session.page < pages - 1:
            navigation.append(
                InlineKeyboardButton(
                    text="下一页",
                    callback_data=f"tg:{page_action}:{session_id}:{session.page + 1}",
                )
            )
        if navigation:
            rows.append(navigation)
        return InlineKeyboardMarkup(inline_keyboard=rows)

    def _page_selection_index(self, session: _Interaction, selection: int) -> int:
        page_size = self._MEDIA_PAGE_SIZE if session.stage == "media" else self._TORRENT_PAGE_SIZE
        return session.page * page_size + selection - 1

    def _store_session(self, session_id: str, session: _Interaction) -> None:
        self._cleanup_sessions()
        self._sessions[session_id] = session
        self._session_messages[(session.chat_id, session.message_id)] = session_id

    def _get_session(self, session_id: str, chat_id: int, message_id: int) -> _Interaction | None:
        self._cleanup_sessions()
        session = self._sessions.get(session_id)
        if session is None or (session.chat_id, session.message_id) != (chat_id, message_id):
            return None
        return session

    def _remove_session(self, chat_id: int, message_id: int) -> None:
        session_id = self._session_messages.pop((chat_id, message_id), None)
        if session_id is not None:
            self._sessions.pop(session_id, None)

    def _cleanup_sessions(self) -> None:
        expires_before = time.monotonic() - self._SESSION_TTL_SECONDS
        for session_id, session in list(self._sessions.items()):
            if session.created_at < expires_before:
                self._sessions.pop(session_id, None)
                self._session_messages.pop((session.chat_id, session.message_id), None)


class TelegramHttpNotifier:
    def __init__(
        self,
        *,
        token: str,
        chat_ids: tuple[int, ...],
        proxy: str | None = None,
    ) -> None:
        self.token = token
        self.chat_ids = chat_ids
        self.proxy = proxy

    @property
    def name(self) -> str:
        return "telegram-http"

    async def notify(self, event: NotifyEvent) -> None:
        if not self.chat_ids:
            return
        text = _telegram_message_text(event)
        async with httpx.AsyncClient(timeout=20, proxy=self.proxy) as client:
            for chat_id in self.chat_ids:
                response = await client.post(
                    f"https://api.telegram.org/bot{self.token}/sendMessage",
                    json={"chat_id": chat_id, "text": text, "parse_mode": "HTML"},
                )
                response.raise_for_status()


def _split_query(query: str) -> tuple[str, str | None]:
    title, separator, artist = query.partition(" ")
    return title.strip(), artist.strip() or None if separator else None


def _chat_log_label(message: Any) -> str:
    chat_id = getattr(getattr(message, "chat", None), "id", None)
    if chat_id is None:
        return "-"
    value = str(chat_id)
    return f"…{value[-4:]}"


def _page_count(total: int, page_size: int) -> int:
    return max((total + page_size - 1) // page_size, 1)


def _page_items(values: Sequence[T], page: int, page_size: int) -> list[tuple[int, T]]:
    start = page * page_size
    return list(enumerate(values[start : start + page_size], start=start))


def _progress_text(progress: float) -> str:
    return f"{max(0, min(progress, 1)) * 100:.0f}%"


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


def _short(value: str, length: int) -> str:
    return value if len(value) <= length else f"{value[: length - 1]}…"


def _error_text(error: Exception) -> str:
    detail = getattr(error, "detail", None)
    return str(detail if detail is not None else error)


def _telegram_message_text(event: NotifyEvent) -> str:
    title = f"<b>{escape(event.title)}</b>"
    if "<b>" in event.text or "<strong>" in event.text:
        return f"{title}\n{event.text}"
    return f"{title}\n{escape(event.text)}"
