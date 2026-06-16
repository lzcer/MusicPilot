from __future__ import annotations

import asyncio
import contextlib
from html import escape

import httpx

from musicpilot.core.event_bus import EventBus
from musicpilot.core.events import NotifyEvent, SearchEvent


class TelegramBotAdapter:
    def __init__(self, *, token: str, event_bus: EventBus, chat_ids: tuple[int, ...] = ()) -> None:
        self.token = token
        self.event_bus = event_bus
        self.chat_ids = chat_ids
        self._bot = None
        self._dispatcher = None
        self._task: asyncio.Task[None] | None = None

    @property
    def name(self) -> str:
        return "telegram"

    async def start(self) -> None:
        from aiogram import Bot, Dispatcher, F
        from aiogram.types import Message

        self._bot = Bot(self.token)
        self._dispatcher = Dispatcher()

        async def handle_text(message: Message) -> None:
            if not message.text:
                return
            query = message.text.strip()
            if not query or query.startswith("/"):
                return
            await self.event_bus.publish(SearchEvent(query))
            await message.answer(f"已收到检索请求：{query}")

        self._dispatcher.message.register(handle_text, F.text)
        self._task = asyncio.create_task(
            self._dispatcher.start_polling(self._bot),
            name="musicpilot-telegram-bot",
        )

    async def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
        if self._bot is not None:
            await self._bot.session.close()

    async def send_notification(self, event: NotifyEvent) -> None:
        if self._bot is None:
            return
        text = _telegram_message_text(event)
        for chat_id in self.chat_ids:
            await self._bot.send_message(chat_id, text, parse_mode="HTML")

    async def notify(self, event: NotifyEvent) -> None:
        await self.send_notification(event)


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


def _telegram_message_text(event: NotifyEvent) -> str:
    title = f"<b>{escape(event.title)}</b>"
    if "<b>" in event.text or "<strong>" in event.text:
        return f"{title}\n{event.text}"
    return f"{title}\n{escape(event.text)}"
