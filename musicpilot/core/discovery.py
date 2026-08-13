from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import TypeVar, cast

from musicpilot.ports.discovery import (
    DiscoveryChartPage,
    DiscoveryItemDetail,
    DiscoveryProvider,
    DiscoveryResourceType,
)

T = TypeVar("T")


@dataclass(slots=True)
class _CacheEntry:
    expires_at: float
    value: object


class DiscoveryService:
    def __init__(
        self,
        provider: DiscoveryProvider,
        *,
        cache_namespace: str,
        chart_ttl_seconds: float = 5 * 60,
        detail_ttl_seconds: float = 30 * 60,
        request_timeout_seconds: float = 30,
    ) -> None:
        self._provider = provider
        self._cache_namespace = cache_namespace
        self._chart_ttl_seconds = chart_ttl_seconds
        self._detail_ttl_seconds = detail_ttl_seconds
        self._request_timeout_seconds = request_timeout_seconds
        self._cache: dict[str, _CacheEntry] = {}
        self._inflight: dict[str, asyncio.Task[object]] = {}
        self._lock = asyncio.Lock()

    async def chart(
        self,
        resource_type: DiscoveryResourceType,
        *,
        offset: int = 0,
        limit: int = 20,
    ) -> DiscoveryChartPage:
        key = f"{self._cache_namespace}:chart:{resource_type}:{offset}:{limit}"
        return await self._cached(
            key,
            self._chart_ttl_seconds,
            lambda: self._provider.chart(resource_type, offset=offset, limit=limit),
        )

    async def detail(
        self,
        resource_type: DiscoveryResourceType,
        item_id: str,
    ) -> DiscoveryItemDetail:
        key = f"{self._cache_namespace}:detail:{resource_type}:{item_id}"
        return await self._cached(
            key,
            self._detail_ttl_seconds,
            lambda: self._provider.detail(resource_type, item_id),
        )

    async def clear(self) -> None:
        async with self._lock:
            self._cache.clear()
            for task in self._inflight.values():
                task.cancel()
            self._inflight.clear()

    async def _cached(
        self,
        key: str,
        ttl_seconds: float,
        loader: Callable[[], Awaitable[T]],
    ) -> T:
        now = time.monotonic()
        async with self._lock:
            entry = self._cache.get(key)
            if entry is not None and entry.expires_at > now:
                return cast(T, entry.value)
            task = self._inflight.get(key)
            if task is None:
                task = asyncio.create_task(
                    self._load(loader),
                    name=f"musicpilot-discovery:{key}",
                )
                self._inflight[key] = task
        try:
            value = await asyncio.shield(task)
        except BaseException:
            if task.done():
                async with self._lock:
                    if self._inflight.get(key) is task:
                        self._inflight.pop(key, None)
            raise
        else:
            async with self._lock:
                self._cache[key] = _CacheEntry(
                    expires_at=time.monotonic() + ttl_seconds,
                    value=value,
                )
                if self._inflight.get(key) is task:
                    self._inflight.pop(key, None)
        return cast(T, value)

    async def _load(self, loader: Callable[[], Awaitable[T]]) -> T:
        async with asyncio.timeout(self._request_timeout_seconds):
            return await loader()
