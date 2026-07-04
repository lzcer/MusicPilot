from __future__ import annotations

import asyncio
import contextlib
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Protocol, TypeVar

logger = logging.getLogger(__name__)
T = TypeVar("T")


@dataclass(frozen=True, slots=True)
class TaskCreate:
    task_type: str
    payload: dict[str, Any] = field(default_factory=dict)
    resource_keys: list[str] = field(default_factory=list)
    chain_id: str | None = None
    parent_task_id: int | None = None
    inheritable_key: str | None = None
    priority: int = 0
    max_attempts: int = 1
    available_at: datetime | None = None
    idempotency_key: str | None = None

    def to_payload(self) -> dict[str, Any]:
        return {
            "task_type": self.task_type,
            "payload": self.payload,
            "resource_keys": self.resource_keys,
            "chain_id": self.chain_id,
            "parent_task_id": self.parent_task_id,
            "inheritable_key": self.inheritable_key,
            "priority": self.priority,
            "max_attempts": self.max_attempts,
            "available_at": self.available_at,
            "idempotency_key": self.idempotency_key,
        }


@dataclass(frozen=True, slots=True)
class TaskExecutionResult:
    result: dict[str, Any] = field(default_factory=dict)
    next_tasks: list[TaskCreate] = field(default_factory=list)


class TaskExecutor(Protocol):
    async def execute(self, task: Any) -> TaskExecutionResult: ...


class TaskExecutorRegistry:
    def __init__(self) -> None:
        self._executors: dict[str, TaskExecutor] = {}

    def register(self, task_type: str, executor: TaskExecutor) -> None:
        self._executors[task_type] = executor

    def get(self, task_type: str) -> TaskExecutor | None:
        return self._executors.get(task_type)


class TaskManager:
    def __init__(
        self,
        *,
        repository: Any,
        executors: TaskExecutorRegistry,
        log: Callable[[str, str, str], None],
        poll_interval_seconds: float = 1.0,
        lease_seconds: int = 300,
        retry_delay_seconds: int = 60,
        max_concurrent_tasks: int = 8,
    ) -> None:
        self.repository = repository
        self.executors = executors
        self._log = log
        self.poll_interval_seconds = poll_interval_seconds
        self.lease_seconds = lease_seconds
        self.retry_delay_seconds = retry_delay_seconds
        self.max_concurrent_tasks = max(1, max_concurrent_tasks)
        self._condition = asyncio.Condition()
        self._worker: asyncio.Task[None] | None = None
        self._running_tasks: set[asyncio.Task[None]] = set()
        self._stopping = False

    async def enqueue(self, task: TaskCreate) -> int:
        row = await self.repository.create_system_task(
            task_type=task.task_type,
            payload=task.payload,
            resource_keys=task.resource_keys,
            chain_id=task.chain_id,
            parent_task_id=task.parent_task_id,
            inheritable_key=task.inheritable_key,
            priority=task.priority,
            max_attempts=task.max_attempts,
            available_at=task.available_at,
            idempotency_key=task.idempotency_key,
        )
        self._log(
            "task",
            f"System task enqueued: id={row.id}, type={row.task_type}, chain={row.chain_id}",
            "INFO",
        )
        await self.wake()
        return int(row.id)

    async def wait_for_task(self, task_id: int, *, wait_timeout: float | None = None) -> Any:
        async def wait_loop() -> Any:
            while True:
                task = await self.repository.get_system_task(task_id)
                if task is None:
                    raise RuntimeError(f"System task not found: id={task_id}")
                if task.status in {"SUCCEEDED", "FAILED"}:
                    return task
                async with self._condition:
                    with contextlib.suppress(asyncio.TimeoutError):
                        await asyncio.wait_for(
                            self._condition.wait(),
                            timeout=self.poll_interval_seconds,
                        )

        if wait_timeout is None:
            return await wait_loop()
        return await asyncio.wait_for(wait_loop(), timeout=wait_timeout)

    async def run_exclusive(
        self,
        *,
        task_type: str,
        resource_keys: list[str],
        runner: Callable[[], Awaitable[T]],
        payload: dict[str, Any] | None = None,
        chain_id: str | None = None,
        parent_task_id: int | None = None,
        inheritable_key: str | None = None,
        priority: int = 0,
        max_attempts: int = 1,
        wait_log_message: str | None = None,
    ) -> T:
        task = None
        logged_wait = False
        while not self._stopping:
            task = await self.repository.try_start_system_task(
                task_type=task_type,
                payload=payload or {},
                resource_keys=resource_keys,
                chain_id=chain_id,
                parent_task_id=parent_task_id,
                inheritable_key=inheritable_key,
                priority=priority,
                max_attempts=max_attempts,
                lease_seconds=self.lease_seconds,
            )
            if task is not None:
                break
            if wait_log_message and not logged_wait:
                self._log("task", wait_log_message, "INFO")
                logged_wait = True
            async with self._condition:
                with contextlib.suppress(asyncio.TimeoutError):
                    await asyncio.wait_for(
                        self._condition.wait(),
                        timeout=self.poll_interval_seconds,
                    )
        if task is None:
            raise RuntimeError("Task manager stopped before task resources were available.")
        self._log(
            "task",
            f"System task started: id={task.id}, type={task.task_type}, resources={resource_keys}",
            "INFO",
        )
        lease_refresher = asyncio.create_task(
            self._refresh_task_lease(int(task.id)),
            name=f"musicpilot-task-lease-{task.id}",
        )
        try:
            result = await runner()
        except asyncio.CancelledError:
            lease_refresher.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await lease_refresher
            await self.repository.fail_system_task(
                int(task.id),
                error_message="Task cancelled.",
                retry_delay_seconds=0,
            )
            await self.wake()
            raise
        except Exception as exc:  # noqa: BLE001
            lease_refresher.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await lease_refresher
            await self.repository.fail_system_task(
                int(task.id),
                error_message=str(exc),
                retry_delay_seconds=0,
            )
            await self.wake()
            raise
        lease_refresher.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await lease_refresher
        await self.repository.complete_system_task(
            int(task.id),
            result={"mode": "exclusive"},
            next_tasks=[],
        )
        self._log(
            "task",
            f"System task completed: id={task.id}, type={task.task_type}",
            "INFO",
        )
        await self.wake()
        return result

    async def _refresh_task_lease(self, task_id: int) -> None:
        interval = max(5.0, self.lease_seconds / 3)
        while not self._stopping:
            await asyncio.sleep(interval)
            refreshed = await self.repository.refresh_system_task_lease(
                task_id,
                lease_seconds=self.lease_seconds,
            )
            if not refreshed:
                return

    def start(self) -> None:
        if self._worker is not None and not self._worker.done():
            return
        self._stopping = False
        self._worker = asyncio.create_task(self._run(), name="musicpilot-task-manager")

    async def stop(self) -> None:
        self._stopping = True
        await self.wake()
        if self._worker is None:
            return
        self._worker.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await self._worker
        for task in tuple(self._running_tasks):
            task.cancel()
        for task in tuple(self._running_tasks):
            with contextlib.suppress(asyncio.CancelledError):
                await task

    async def wake(self) -> None:
        async with self._condition:
            self._condition.notify_all()

    async def _run(self) -> None:
        recovered = await self.repository.recover_stale_system_tasks(recover_all_running=True)
        if recovered:
            self._log("task", f"Recovered {recovered} stale system task(s).", "WARNING")
        while not self._stopping:
            try:
                recovered = await self.repository.recover_stale_system_tasks()
                if recovered:
                    self._log(
                        "task",
                        f"Recovered {recovered} expired system task(s).",
                        "WARNING",
                    )
                worked = await self.run_once()
            except Exception as exc:  # noqa: BLE001
                logger.exception("System task scheduler failed")
                self._log("task", f"System task scheduler failed: {exc}", "ERROR")
                worked = False
            if worked:
                continue
            async with self._condition:
                with contextlib.suppress(asyncio.TimeoutError):
                    await asyncio.wait_for(
                        self._condition.wait(),
                        timeout=self.poll_interval_seconds,
                    )

    async def run_once(self) -> bool:
        available_slots = self.max_concurrent_tasks - len(self._running_tasks)
        if available_slots <= 0:
            return False
        tasks = await self.repository.list_ready_system_tasks(limit=max(available_slots * 2, 1))
        if not tasks:
            return False
        scheduled = False
        for task in tasks:
            if len(self._running_tasks) >= self.max_concurrent_tasks:
                break
            claimed = await self.repository.try_claim_system_task(
                int(task.id),
                lease_seconds=self.lease_seconds,
            )
            if claimed is None:
                continue
            runner = asyncio.create_task(
                self._execute_claimed(claimed),
                name=f"musicpilot-system-task-{claimed.id}",
            )
            self._running_tasks.add(runner)
            runner.add_done_callback(self._system_task_done)
            scheduled = True
        return scheduled

    def _system_task_done(self, task: asyncio.Task[None]) -> None:
        self._running_tasks.discard(task)
        if not task.cancelled():
            with contextlib.suppress(Exception):
                task.result()
        if not self._stopping:
            asyncio.create_task(self.wake())

    async def _execute_claimed(self, task: Any) -> None:
        executor = self.executors.get(str(task.task_type))
        if executor is None:
            await self.repository.fail_system_task(
                int(task.id),
                error_message=f"No executor registered for task type {task.task_type}.",
                retry_delay_seconds=self.retry_delay_seconds,
            )
            self._log(
                "task",
                f"System task failed without executor: id={task.id}, type={task.task_type}",
                "ERROR",
            )
            await self.wake()
            return
        self._log(
            "task",
            f"System task started: id={task.id}, type={task.task_type}, chain={task.chain_id}",
            "INFO",
        )
        lease_refresher = asyncio.create_task(
            self._refresh_task_lease(int(task.id)),
            name=f"musicpilot-task-lease-{task.id}",
        )
        try:
            result = await executor.execute(task)
        except asyncio.CancelledError:
            lease_refresher.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await lease_refresher
            with contextlib.suppress(Exception):
                await asyncio.shield(
                    self.repository.requeue_system_task(
                        int(task.id),
                        error_message="Task cancelled; restored to WAIT.",
                    )
                )
            await self.wake()
            raise
        except Exception as exc:  # noqa: BLE001
            lease_refresher.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await lease_refresher
            await self.repository.fail_system_task(
                int(task.id),
                error_message=str(exc),
                retry_delay_seconds=self.retry_delay_seconds,
            )
            self._log("task", f"System task failed: id={task.id}, error={exc}", "ERROR")
            await self.wake()
            return
        lease_refresher.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await lease_refresher
        await self.repository.complete_system_task(
            int(task.id),
            result=result.result,
            next_tasks=[item.to_payload() for item in result.next_tasks],
        )
        self._log(
            "task",
            f"System task completed: id={task.id}, next={len(result.next_tasks)}",
            "INFO",
        )
        await self.wake()
