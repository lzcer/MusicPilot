from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator

from musicpilot.core.events import Event


class EventBus:
    """Single-process async event bus backed by asyncio.Queue."""

    def __init__(self, maxsize: int = 1000) -> None:
        self._queue: asyncio.Queue[Event] = asyncio.Queue(maxsize=maxsize)

    async def publish(self, event: Event) -> None:
        try:
            self._queue.put_nowait(event)
        except asyncio.QueueFull:
            # Queue is at capacity — discard oldest event to make room
            try:
                self._queue.get_nowait()
                self._queue.task_done()
            except asyncio.QueueEmpty:
                pass
            self._queue.put_nowait(event)

    async def next(self) -> Event:
        return await self._queue.get()

    def task_done(self) -> None:
        self._queue.task_done()

    async def join(self) -> None:
        await self._queue.join()

    def qsize(self) -> int:
        return self._queue.qsize()

    async def listen(self) -> AsyncIterator[Event]:
        while True:
            event = await self.next()
            try:
                yield event
            finally:
                self.task_done()
