from __future__ import annotations

import asyncio
import contextlib
import logging
from collections.abc import Awaitable, Callable
from contextvars import ContextVar
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Protocol, TypeVar

logger = logging.getLogger(__name__)
T = TypeVar("T")
SCRAPE_WORKER_TASK_TYPES = frozenset(
    {
        "DOWNLOAD_ITEM_SCRAPE",
        "MANUAL_FILE_SCRAPE",
        "MANUAL_SCRAPE",
    }
)


class TaskLeaseLostError(RuntimeError):
    pass


class TaskManagerStoppingError(TaskLeaseLostError):
    pass


@dataclass(frozen=True, slots=True)
class TaskExecutionContext:
    task_id: int
    task_type: str
    attempt: int
    payload: dict[str, Any]


_TASK_EXECUTION_CONTEXT: ContextVar[TaskExecutionContext | None] = ContextVar(
    "musicpilot_task_execution_context",
    default=None,
)


def current_task_execution_context() -> TaskExecutionContext | None:
    return _TASK_EXECUTION_CONTEXT.get()


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
        max_concurrent_scrape_tasks: int = 3,
    ) -> None:
        self.repository = repository
        self.executors = executors
        self._log = log
        self.poll_interval_seconds = poll_interval_seconds
        self.lease_seconds = lease_seconds
        self.retry_delay_seconds = retry_delay_seconds
        self.max_concurrent_tasks = max(1, max_concurrent_tasks)
        self.max_concurrent_scrape_tasks = max(1, max_concurrent_scrape_tasks)
        self._condition = asyncio.Condition()
        self._admission_lock = asyncio.Lock()
        self._worker: asyncio.Task[None] | None = None
        self._running_tasks: set[asyncio.Task[None]] = set()
        self._running_task_by_id: dict[int, asyncio.Task[None]] = {}
        self._running_task_type_by_id: dict[int, str] = {}
        self._exclusive_calls: set[asyncio.Task[Any]] = set()
        self._exclusive_task_by_id: dict[int, asyncio.Task[Any]] = {}
        self._force_interrupted_task_ids: set[int] = set()
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
                if task.status in {"SUCCEEDED", "FAILED", "INTERRUPTED"}:
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
        current_call = asyncio.current_task()
        if current_call is None:
            raise RuntimeError("Exclusive task requires an active asyncio task.")
        self._exclusive_calls.add(current_call)
        task = None
        logged_wait = False
        try:
            while not self._stopping:
                async with self._admission_lock:
                    scrape_capacity_available = (
                        task_type not in SCRAPE_WORKER_TASK_TYPES
                        or sum(
                            running_type in SCRAPE_WORKER_TASK_TYPES
                            for running_type in self._running_task_type_by_id.values()
                        )
                        < self.max_concurrent_scrape_tasks
                    )
                    if scrape_capacity_available:
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
                            task_id = int(task.id)
                            self._running_task_type_by_id[task_id] = str(task.task_type)
                            self._exclusive_task_by_id[task_id] = current_call
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
                raise TaskManagerStoppingError(
                    "Task manager stopped before task resources were available."
                )
            self._log(
                "task",
                "System task started: "
                f"id={task.id}, type={task.task_type}, resources={resource_keys}",
                "INFO",
            )
            expected_attempt = int(task.attempts)
            try:
                result = await self._run_with_lease(task, runner)
            except TaskManagerStoppingError:
                with contextlib.suppress(Exception):
                    await asyncio.shield(
                        self.repository.interrupt_running_system_tasks(
                            [int(task.id)],
                            error_message="Exclusive task stopped with task manager.",
                            restore_attempt=True,
                        )
                    )
                raise asyncio.CancelledError() from None
            except asyncio.CancelledError:
                task_id = int(task.id)
                if task_id in self._force_interrupted_task_ids:
                    with contextlib.suppress(Exception):
                        await asyncio.shield(
                            self.repository.interrupt_running_system_tasks(
                                [task_id],
                                error_message="Task force interrupted by user.",
                            )
                        )
                    self._force_interrupted_task_ids.discard(task_id)
                elif self._stopping:
                    with contextlib.suppress(Exception):
                        await asyncio.shield(
                            self.repository.interrupt_running_system_tasks(
                                [task_id],
                                error_message="Exclusive task stopped with task manager.",
                                restore_attempt=True,
                            )
                        )
                else:
                    await self.repository.fail_system_task(
                        int(task.id),
                        expected_attempt=expected_attempt,
                        error_message="Task cancelled.",
                        retry_delay_seconds=0,
                    )
                raise
            except Exception as exc:  # noqa: BLE001
                await self.repository.fail_system_task(
                    int(task.id),
                    expected_attempt=expected_attempt,
                    error_message=str(exc),
                    retry_delay_seconds=0,
                )
                raise
            task_id = int(task.id)
            if task_id in self._force_interrupted_task_ids:
                await self.repository.interrupt_running_system_tasks(
                    [task_id],
                    error_message="Task force interrupted by user.",
                )
                self._force_interrupted_task_ids.discard(task_id)
                raise asyncio.CancelledError() from None
            completed = await self.repository.complete_system_task(
                task_id,
                expected_attempt=expected_attempt,
                result={"mode": "exclusive"},
                next_tasks=[],
            )
            if completed is None:
                raise TaskLeaseLostError(
                    f"Task ownership lost before completion: id={task.id}, "
                    f"attempt={expected_attempt}"
                )
            self._log(
                "task",
                f"System task completed: id={task.id}, type={task.task_type}",
                "INFO",
            )
            return result
        finally:
            if task is not None:
                task_id = int(task.id)
                self._running_task_type_by_id.pop(task_id, None)
                self._exclusive_task_by_id.pop(task_id, None)
                self._force_interrupted_task_ids.discard(task_id)
            self._exclusive_calls.discard(current_call)
            with contextlib.suppress(BaseException):
                await asyncio.shield(self.wake())

    async def _run_with_lease(
        self,
        task: Any,
        runner: Callable[[], Awaitable[T]],
    ) -> T:
        task_id = int(task.id)
        expected_attempt = int(task.attempts)
        context = TaskExecutionContext(
            task_id=task_id,
            task_type=str(task.task_type),
            attempt=expected_attempt,
            payload=dict(task.payload or {}),
        )
        token = _TASK_EXECUTION_CONTEXT.set(context)
        try:
            business_task = asyncio.create_task(
                runner(),
                name=f"musicpilot-task-business-{task_id}-{expected_attempt}",
            )
        finally:
            _TASK_EXECUTION_CONTEXT.reset(token)
        lease_refresher = asyncio.create_task(
            self._refresh_task_lease(task_id, expected_attempt),
            name=f"musicpilot-task-lease-{task_id}-{expected_attempt}",
        )
        try:
            done, _pending = await asyncio.wait(
                (business_task, lease_refresher),
                return_when=asyncio.FIRST_COMPLETED,
            )
            if business_task in done:
                lease_refresher.cancel()
                with contextlib.suppress(BaseException):
                    await lease_refresher
                return await business_task
            business_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await business_task
            await lease_refresher
            raise TaskLeaseLostError(
                f"Task lease refresher stopped unexpectedly: id={task_id}, "
                f"attempt={expected_attempt}"
            )
        except BaseException:
            business_task.cancel()
            lease_refresher.cancel()
            await asyncio.gather(
                business_task,
                lease_refresher,
                return_exceptions=True,
            )
            raise

    async def _refresh_task_lease(self, task_id: int, expected_attempt: int) -> None:
        interval = max(0.1, self.lease_seconds / 3)
        while not self._stopping:
            await asyncio.sleep(interval)
            refreshed = await self.repository.refresh_system_task_lease(
                task_id,
                expected_attempt=expected_attempt,
                lease_seconds=self.lease_seconds,
            )
            if not refreshed:
                raise TaskLeaseLostError(
                    f"Task lease lost: id={task_id}, attempt={expected_attempt}"
                )
        raise TaskManagerStoppingError(
            f"Task manager stopped lease refresh: id={task_id}, attempt={expected_attempt}"
        )

    def start(self) -> None:
        if self._worker is not None and not self._worker.done():
            return
        self._stopping = False
        self._worker = asyncio.create_task(self._run(), name="musicpilot-task-manager")

    async def stop(self) -> None:
        self._stopping = True
        await self.wake()
        if self._worker is not None:
            self._worker.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._worker
        current_task = asyncio.current_task()
        active_tasks = set(self._running_tasks)
        active_tasks.update(
            task for task in self._exclusive_calls if task is not current_task
        )
        for task in active_tasks:
            task.cancel()
        if active_tasks:
            await asyncio.gather(*active_tasks, return_exceptions=True)

    async def wake(self) -> None:
        async with self._condition:
            self._condition.notify_all()

    async def force_interrupt_system_tasks(self, task_ids: list[int]) -> list[int]:
        interrupted: list[int] = []
        runners: set[asyncio.Task[Any]] = set()
        current_task = asyncio.current_task()
        for task_id in sorted(set(task_ids)):
            runner = self._running_task_by_id.get(task_id)
            if runner is None:
                runner = self._exclusive_task_by_id.get(task_id)
            if runner is None or runner is current_task or runner.done():
                continue
            self._force_interrupted_task_ids.add(task_id)
            if not runner.cancel():
                self._force_interrupted_task_ids.discard(task_id)
                continue
            runners.add(runner)
            interrupted.append(task_id)
        if interrupted:
            await asyncio.gather(*runners, return_exceptions=True)
            await self.wake()
        return interrupted

    async def _run(self) -> None:
        recovered = await self.repository.recover_stale_system_tasks(recover_all_running=True)
        if recovered:
            self._log("task", f"Recovered {recovered} stale system task(s).", "WARNING")
        while not self._stopping:
            try:
                recovered = await self.repository.recover_stale_system_tasks(
                    excluded_task_ids=self._running_task_type_by_id,
                )
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
        async with self._admission_lock:
            return await self._run_once_admitted()

    async def _run_once_admitted(self) -> bool:
        available_slots = self.max_concurrent_tasks - len(self._running_tasks)
        if available_slots <= 0:
            return False
        page_size = max(available_slots * 8, 32)
        cursor: tuple[int, datetime, int] | None = None
        scheduled = False
        running_scrape_tasks = sum(
            task_type in SCRAPE_WORKER_TASK_TYPES
            for task_type in self._running_task_type_by_id.values()
        )
        while len(self._running_tasks) < self.max_concurrent_tasks:
            excluded_task_types = (
                SCRAPE_WORKER_TASK_TYPES
                if running_scrape_tasks >= self.max_concurrent_scrape_tasks
                else None
            )
            tasks = await self.repository.list_ready_system_tasks(
                limit=page_size,
                after=cursor,
                excluded_task_types=excluded_task_types,
            )
            if not tasks:
                break
            for task in tasks:
                if len(self._running_tasks) >= self.max_concurrent_tasks:
                    break
                task_type = str(task.task_type)
                if (
                    task_type in SCRAPE_WORKER_TASK_TYPES
                    and running_scrape_tasks >= self.max_concurrent_scrape_tasks
                ):
                    continue
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
                self._running_task_by_id[int(claimed.id)] = runner
                self._running_task_type_by_id[int(claimed.id)] = task_type
                if task_type in SCRAPE_WORKER_TASK_TYPES:
                    running_scrape_tasks += 1
                runner.add_done_callback(self._system_task_done)
                scheduled = True
            last_task = tasks[-1]
            cursor = (
                int(last_task.priority),
                last_task.created_at,
                int(last_task.id),
            )
            if len(tasks) < page_size:
                break
        return scheduled

    def _system_task_done(self, task: asyncio.Task[None]) -> None:
        self._running_tasks.discard(task)
        for task_id, runner in tuple(self._running_task_by_id.items()):
            if runner is task:
                self._running_task_by_id.pop(task_id, None)
                self._running_task_type_by_id.pop(task_id, None)
                break
        if not task.cancelled():
            try:
                task.result()
            except Exception as exc:  # noqa: BLE001
                logger.exception("System task runner crashed")
                self._log("task", f"System task runner crashed: {exc}", "ERROR")
        if not self._stopping:
            asyncio.create_task(self.wake())

    async def _execute_claimed(self, task: Any) -> None:
        task_id = int(task.id)
        expected_attempt = int(task.attempts)
        executor = self.executors.get(str(task.task_type))
        if executor is None:
            await self.repository.fail_system_task(
                task_id,
                expected_attempt=expected_attempt,
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
        try:
            result = await self._run_with_lease(task, lambda: executor.execute(task))
        except TaskManagerStoppingError:
            with contextlib.suppress(Exception):
                await asyncio.shield(
                    self.repository.requeue_system_task(
                        task_id,
                        expected_attempt=expected_attempt,
                        error_message="Task stopped with task manager; restored to WAIT.",
                        restore_attempt=True,
                    )
                )
            await self.wake()
            return
        except asyncio.CancelledError:
            if task_id in self._force_interrupted_task_ids:
                with contextlib.suppress(Exception):
                    await asyncio.shield(
                        self.repository.interrupt_running_system_tasks(
                            [task_id],
                            error_message="Task force interrupted by user.",
                        )
                    )
                self._force_interrupted_task_ids.discard(task_id)
            else:
                with contextlib.suppress(Exception):
                    await asyncio.shield(
                        self.repository.requeue_system_task(
                            task_id,
                            expected_attempt=expected_attempt,
                            error_message=(
                                "Task stopped with task manager; restored to WAIT."
                                if self._stopping
                                else "Task cancelled; restored to WAIT."
                            ),
                            restore_attempt=self._stopping,
                        )
                    )
            await self.wake()
            raise
        except Exception as exc:  # noqa: BLE001
            if task_id in self._force_interrupted_task_ids:
                await self.repository.interrupt_running_system_tasks(
                    [task_id],
                    error_message="Task force interrupted by user.",
                )
                self._force_interrupted_task_ids.discard(task_id)
            else:
                await self.repository.fail_system_task(
                    task_id,
                    expected_attempt=expected_attempt,
                    error_message=str(exc),
                    retry_delay_seconds=self.retry_delay_seconds,
                )
                self._log("task", f"System task failed: id={task.id}, error={exc}", "ERROR")
            await self.wake()
            return
        if task_id in self._force_interrupted_task_ids:
            await self.repository.interrupt_running_system_tasks(
                [task_id],
                error_message="Task force interrupted by user.",
            )
            self._force_interrupted_task_ids.discard(task_id)
            await self.wake()
            return
        completed = await self.repository.complete_system_task(
            task_id,
            expected_attempt=expected_attempt,
            result=result.result,
            next_tasks=[item.to_payload() for item in result.next_tasks],
        )
        if completed is None:
            self._log(
                "task",
                "System task completion skipped after ownership changed: "
                f"id={task.id}, attempt={expected_attempt}",
                "WARNING",
            )
            await self.wake()
            return
        self._log(
            "task",
            f"System task completed: id={task.id}, next={len(result.next_tasks)}",
            "INFO",
        )
        await self.wake()
