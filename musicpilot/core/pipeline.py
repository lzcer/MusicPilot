from __future__ import annotations

import asyncio
import contextlib
import logging
from collections.abc import Awaitable, Callable, Iterable

from musicpilot.core.event_bus import EventBus
from musicpilot.core.events import (
    DownloadCompletedEvent,
    DownloadEvent,
    Event,
    EventType,
    MediaProcessedEvent,
    NotifyEvent,
    SearchCompletedEvent,
    SearchEvent,
    SearchResult,
)
from musicpilot.core.processor import MediaProcessor
from musicpilot.ports.downloader import Downloader
from musicpilot.ports.indexer import Indexer
from musicpilot.ports.notifier import Notifier

logger = logging.getLogger(__name__)
SearchRunner = Callable[[Indexer, str, int], Awaitable[tuple[str, tuple[SearchResult, ...]]]]


class MusicPipeline:
    def __init__(
        self,
        *,
        event_bus: EventBus,
        indexers: Iterable[Indexer] = (),
        downloader: Downloader | None = None,
        media_processor: MediaProcessor | None = None,
        notifiers: Iterable[Notifier] = (),
        search_runner: SearchRunner | None = None,
    ) -> None:
        self.event_bus = event_bus
        self.indexers = tuple(indexers)
        self.downloader = downloader
        self.media_processor = media_processor
        self.notifiers = tuple(notifiers)
        self.search_runner = search_runner
        self._worker: asyncio.Task[None] | None = None

    async def search(self, event: SearchEvent) -> tuple[SearchResult, ...]:
        if not self.indexers:
            logger.info("Search skipped for %s because no indexer is configured", event.query)
            return ()

        logger.info("Searching %s indexer(s) for %s", len(self.indexers), event.query)
        if self.search_runner is None:
            result_groups = await asyncio.gather(
                *(indexer.search(event.query, limit=event.limit) for indexer in self.indexers),
                return_exceptions=True,
            )
        else:
            result_groups = await asyncio.gather(
                *(
                    self.search_runner(indexer, event.query, event.limit)
                    for indexer in self.indexers
                ),
                return_exceptions=True,
            )
        results: list[SearchResult] = []
        for indexer, group in zip(self.indexers, result_groups, strict=True):
            if isinstance(group, Exception):
                logger.warning("Indexer %s failed: %s", indexer.name, group)
                continue
            if self.search_runner is None:
                results.extend(group)
            else:
                results.extend(group[1])

        ranked = self._dedupe_and_rank(results, event.limit)
        logger.info("Search finished for %s with %s result(s)", event.query, len(ranked))
        return ranked

    async def handle(self, event: Event) -> None:
        if event.event_type == EventType.SEARCH_REQUESTED and isinstance(event, SearchEvent):
            results = await self.search(event)
            await self.event_bus.publish(
                SearchCompletedEvent(event.query, results, correlation_id=event.correlation_id)
            )
            return

        if event.event_type == EventType.DOWNLOAD_REQUESTED and isinstance(event, DownloadEvent):
            if self.downloader is None or event.result is None:
                logger.info("Download requested but no downloader is configured.")
                return
            logger.info("Adding torrent to downloader: %s", event.result.title)
            await self.downloader.add_torrent(event.result.download_url, category=event.category)
            logger.info("Torrent submitted to downloader: %s", event.result.title)
            return

        if event.event_type == EventType.DOWNLOAD_COMPLETED and isinstance(
            event, DownloadCompletedEvent
        ):
            if self.media_processor is None:
                logger.info("Download completed but no media processor is configured.")
                return
            logger.info("Processing completed download: %s", event.torrent_hash)
            processed = await self.media_processor.process_download(event)
            logger.info(
                "Processed completed download %s into %s item(s)",
                event.torrent_hash,
                len(processed),
            )
            await self.event_bus.publish(MediaProcessedEvent(event.torrent_hash, processed))
            if processed:
                await self.event_bus.publish(
                    NotifyEvent(
                        title="MusicPilot 已入库",
                        text=f"已处理 {len(processed)} 个音频文件。",
                    )
                )
            return

        if event.event_type == EventType.NOTIFY_REQUESTED and isinstance(event, NotifyEvent):
            logger.info(
                "Sending notification %s to %s notifier(s)",
                event.title,
                len(self.notifiers),
            )
            await asyncio.gather(*(notifier.notify(event) for notifier in self.notifiers))
            logger.info("Notification sent: %s", event.title)

    def start(self) -> None:
        if self._worker is not None and not self._worker.done():
            return
        self._worker = asyncio.create_task(self._run(), name="musicpilot-pipeline")

    async def stop(self) -> None:
        if self._worker is None:
            return
        self._worker.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await self._worker

    async def _run(self) -> None:
        async for event in self.event_bus.listen():
            await self.handle(event)

    @staticmethod
    def _dedupe_and_rank(results: list[SearchResult], limit: int) -> tuple[SearchResult, ...]:
        by_key: dict[tuple[str, str], SearchResult] = {}
        for result in results:
            current = by_key.get(result.identity_key)
            if current is None or result.seeders > current.seeders:
                by_key[result.identity_key] = result
        ranked = sorted(by_key.values(), key=lambda item: item.seeders, reverse=True)
        return tuple(ranked[:limit])
