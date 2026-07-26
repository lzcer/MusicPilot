from __future__ import annotations

import asyncio
import contextlib
import logging
import os
import re
import threading
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Literal
from uuid import uuid4

from watchfiles import Change, DefaultFilter, watch

from musicpilot.core.scraping import AUDIO_EXTENSIONS

logger = logging.getLogger(__name__)

DirectoryMonitorMode = Literal["native", "polling"]
FileSubmitter = Callable[[Path, str], Awaitable[bool]]
FailureHandler = Callable[[str, str], Awaitable[None]]
LogSink = Callable[[str, str], None]

_PROBE_PREFIX = ".musicpilot-watch-probe-"
_NATIVE_FALLBACK_POLL_DELAY_MS = 24 * 60 * 60 * 1000
_MOUNTINFO_PATH = Path("/proc/self/mountinfo")
_MOUNTINFO_ESCAPE_PATTERN = re.compile(r"\\([0-7]{3})")
_UNRELIABLE_NATIVE_FILESYSTEMS = frozenset(
    {
        "cifs",
        "fuse.sshfs",
        "nfs",
        "nfs4",
        "smb3",
    }
)


class DirectoryMonitorProbeError(RuntimeError):
    def __init__(self, message: str, *, polling_available: bool = True) -> None:
        super().__init__(message)
        self.polling_available = polling_available


@dataclass(frozen=True, slots=True)
class FileIdentity:
    size: int
    modified_ns: int
    device: int
    inode: int
    created_ns: int

    def same_file(self, other: FileIdentity) -> bool:
        if self.device or self.inode or other.device or other.inode:
            return self.device == other.device and self.inode == other.inode
        return self.created_ns == other.created_ns

    def same_content_state(self, other: FileIdentity) -> bool:
        return self.size == other.size and self.modified_ns == other.modified_ns


DirectorySnapshot = dict[str, tuple[Path, FileIdentity]]


@dataclass(slots=True)
class _Candidate:
    path: Path
    last_identity: FileIdentity
    stable_checks: int = 0
    next_check_at: float = 0.0


async def probe_native_directory(
    root: Path,
    *,
    timeout_seconds: float = 8.0,
) -> None:
    directory = await asyncio.to_thread(_probe_directory_path, root)
    filesystem_type = await asyncio.to_thread(_filesystem_type_for_path, directory)
    if filesystem_type in _UNRELIABLE_NATIVE_FILESYSTEMS:
        raise DirectoryMonitorProbeError(
            f"源目录位于 {filesystem_type.upper()} 网络文件系统，"
            "原生监听无法可靠发现其他客户端写入的文件，请改用轮询监听。"
        )

    probe_path = directory / f"{_PROBE_PREFIX}{uuid4().hex}.probe"
    probe_key = _path_key(probe_path)
    stop_event = threading.Event()
    watcher_ready = threading.Event()
    probe_detected = threading.Event()
    watcher_errors: list[BaseException] = []

    def run_probe_watcher() -> None:
        try:
            for changes in watch(
                directory,
                watch_filter=None,
                stop_event=stop_event,
                rust_timeout=100,
                yield_on_timeout=True,
                force_polling=False,
                poll_delay_ms=_NATIVE_FALLBACK_POLL_DELAY_MS,
                recursive=False,
                ignore_permission_denied=False,
            ):
                watcher_ready.set()
                if any(
                    change == Change.added and _path_key(Path(path)) == probe_key
                    for change, path in changes
                ):
                    probe_detected.set()
                    return
                if stop_event.is_set():
                    return
        except BaseException as exc:  # noqa: BLE001
            watcher_errors.append(exc)
        finally:
            watcher_ready.set()

    thread = threading.Thread(
        target=run_probe_watcher,
        name="MusicPilot-DirectoryNativeProbe",
        daemon=True,
    )
    thread.start()
    try:
        ready = await asyncio.to_thread(watcher_ready.wait, timeout_seconds)
        if not ready:
            raise DirectoryMonitorProbeError("原生监听器启动超时。")
        if watcher_errors:
            raise DirectoryMonitorProbeError(f"原生监听器启动失败：{watcher_errors[0]}")
        try:
            await asyncio.to_thread(_create_probe_file, probe_path)
        except OSError as exc:
            raise DirectoryMonitorProbeError(f"无法在源目录创建探测文件：{exc}") from exc
        detected = await asyncio.to_thread(probe_detected.wait, timeout_seconds)
        if watcher_errors:
            raise DirectoryMonitorProbeError(f"原生监听探测失败：{watcher_errors[0]}")
        if not detected:
            raise DirectoryMonitorProbeError("未在限定时间内收到原生文件新增事件。")
    finally:
        stop_event.set()
        with contextlib.suppress(OSError):
            await asyncio.to_thread(probe_path.unlink, True)
        await asyncio.to_thread(thread.join, 3.0)


class DirectoryMonitorService:
    def __init__(
        self,
        *,
        root: Path,
        mode: DirectoryMonitorMode,
        poll_interval_seconds: int,
        submit_file: FileSubmitter,
        on_failed: FailureHandler,
        log: LogSink,
        recovery_snapshot: DirectorySnapshot | None = None,
        health_check_interval_seconds: float = 60 * 60,
        health_probe_timeout_seconds: float = 10.0,
        stable_check_interval_seconds: float = 10.0,
        required_stable_checks: int = 3,
    ) -> None:
        self.root = root.expanduser().resolve(strict=False)
        self.mode = mode
        self.poll_interval_seconds = max(30, poll_interval_seconds)
        self.generation = uuid4().hex
        self._submit_file = submit_file
        self._on_failed = on_failed
        self._log = log
        self._recovery_snapshot = dict(recovery_snapshot) if recovery_snapshot else None
        self._health_check_interval_seconds = health_check_interval_seconds
        self._health_probe_timeout_seconds = health_probe_timeout_seconds
        self._stable_check_interval_seconds = stable_check_interval_seconds
        self._required_stable_checks = required_stable_checks
        self._known: DirectorySnapshot = {}
        self._added_seen: dict[str, FileIdentity] = {}
        self._candidates: dict[str, _Candidate] = {}
        self._suppressed_until: dict[str, float] = {}
        self._pending_events: dict[str, tuple[Change, str]] = {}
        self._event_signal = asyncio.Event()
        self._loop: asyncio.AbstractEventLoop | None = None
        self._coordinator_task: asyncio.Task[None] | None = None
        self._health_task: asyncio.Task[None] | None = None
        self._failure_task: asyncio.Task[None] | None = None
        self._watch_thread: threading.Thread | None = None
        self._watch_stop = threading.Event()
        self._watch_ready = threading.Event()
        self._watch_startup_error: Exception | None = None
        self._health_probe_event: asyncio.Event | None = None
        self._health_probe_key: str | None = None
        self._stopping = False
        self._failed = False
        self._file_sequence = 0

    @property
    def snapshot(self) -> DirectorySnapshot:
        return dict(self._known)

    async def start(self) -> None:
        if self._coordinator_task is not None and not self._coordinator_task.done():
            return
        self._stopping = False
        self._failed = False
        self._loop = asyncio.get_running_loop()
        await self._start_watcher()
        try:
            snapshot = await asyncio.to_thread(_scan_audio_files, self.root)
        except Exception:
            await self._stop_watcher()
            raise
        if self._failed:
            failure_task = self._failure_task
            if failure_task is not None:
                with contextlib.suppress(asyncio.CancelledError):
                    await failure_task
            await self._stop_watcher()
            raise RuntimeError("目录监听线程在建立基线期间失败。")

        recovered = 0
        if self._recovery_snapshot is None:
            self._known = snapshot
        else:
            self._known = dict(self._recovery_snapshot)
            recovered = self._apply_recovery_snapshot(snapshot)
        self._recovery_snapshot = None
        self._log(
            f"目录监听基线已建立：目录={self.root}，音乐文件={len(snapshot)}，补偿新增={recovered}",
            "INFO",
        )
        self._coordinator_task = asyncio.create_task(
            self._coordinate(),
            name="musicpilot-directory-monitor-coordinator",
        )
        if self.mode == "native":
            self._health_task = asyncio.create_task(
                self._health_loop(),
                name="musicpilot-directory-monitor-health",
            )

    async def stop(self) -> None:
        self._stopping = True
        await self._stop_watcher()
        tasks = (self._coordinator_task, self._health_task, self._failure_task)
        current = asyncio.current_task()
        for task in tasks:
            if task is not None and task is not current:
                task.cancel()
        for task in tasks:
            if task is not None and task is not current:
                with contextlib.suppress(asyncio.CancelledError):
                    await task
        self._coordinator_task = None
        self._health_task = None
        self._failure_task = None
        self._candidates.clear()
        self._pending_events.clear()

    def suppress_paths(self, paths: tuple[Path, ...], *, seconds: float = 10 * 60) -> None:
        expires_at = time.monotonic() + seconds
        for path in paths:
            try:
                normalized = _path_within_root(path, self.root)
            except OSError:
                continue
            if normalized is None:
                continue
            key = _path_key(normalized)
            self._suppressed_until[key] = expires_at
            self._candidates.pop(key, None)
            try:
                identity = _file_identity(normalized)
            except OSError:
                self._known.pop(key, None)
                self._added_seen.pop(key, None)
                continue
            self._known[key] = (normalized, identity)
            self._added_seen[key] = identity

    async def _coordinate(self) -> None:
        event_timeout = min(1.0, max(0.05, self._stable_check_interval_seconds))
        while not self._failed:
            try:
                await asyncio.wait_for(self._event_signal.wait(), timeout=event_timeout)
            except TimeoutError:
                pass
            pending = tuple(self._pending_events.values())
            self._pending_events.clear()
            self._event_signal.clear()
            for change, raw_path in pending:
                await self._handle_event(change, Path(raw_path))
            await self._check_candidates()

    async def _start_watcher(self) -> None:
        await self._stop_watcher()
        self._watch_stop.clear()
        self._watch_ready.clear()
        self._watch_startup_error = None
        self._watch_thread = threading.Thread(
            target=self._watch_forever,
            name=f"MusicPilot-DirectoryWatcher-{self.root.name or 'root'}",
            daemon=True,
        )
        self._watch_thread.start()
        ready = await asyncio.to_thread(self._watch_ready.wait, 10.0)
        if not ready:
            await self._stop_watcher()
            raise TimeoutError("目录监听器启动超时。")
        if self._watch_startup_error is not None:
            startup_error = self._watch_startup_error
            await self._stop_watcher()
            raise RuntimeError(f"目录监听器启动失败：{startup_error}") from startup_error
        mode_label = "原生" if self.mode == "native" else f"轮询（{self.poll_interval_seconds} 秒）"
        self._log(f"目录{mode_label}监听已启动：{self.root}", "INFO")

    async def _stop_watcher(self) -> None:
        thread = self._watch_thread
        if thread is None:
            return
        self._watch_stop.set()
        await asyncio.to_thread(thread.join, 5.0)
        if thread.is_alive():
            self._log(f"目录监听未能在 5 秒内停止：{self.root}", "WARNING")
            return
        self._watch_thread = None

    def _watch_forever(self) -> None:
        try:
            self._watch_once()
            if not self._watch_stop.is_set() and not self._stopping and not self._failed:
                raise RuntimeError("目录监听线程意外退出。")
        except Exception as exc:  # noqa: BLE001
            self._watch_startup_error = exc
            if self._watch_stop.is_set() or self._stopping or self._failed:
                return
            logger.exception("Directory watch failed for %s", self.root)
            if self._loop is not None:
                self._loop.call_soon_threadsafe(
                    self._schedule_failure,
                    "目录监听已停止。",
                    str(exc),
                )
        finally:
            self._watch_ready.set()

    def _watch_once(self) -> None:
        default_filter = DefaultFilter()

        def watch_filter(change: Change, path: str) -> bool:
            if Path(path).name.startswith(_PROBE_PREFIX):
                return True
            return default_filter(change, path)

        force_polling = self.mode == "polling"
        poll_delay_ms = (
            self.poll_interval_seconds * 1000 if force_polling else _NATIVE_FALLBACK_POLL_DELAY_MS
        )
        for changes in watch(
            self.root,
            watch_filter=watch_filter,
            stop_event=self._watch_stop,
            rust_timeout=1000,
            yield_on_timeout=True,
            force_polling=force_polling,
            poll_delay_ms=poll_delay_ms,
            recursive=True,
            ignore_permission_denied=False,
        ):
            self._watch_ready.set()
            if self._watch_stop.is_set() or self._stopping or self._failed:
                return
            if changes and self._loop is not None:
                self._loop.call_soon_threadsafe(self._publish_changes, tuple(changes))

    def _publish_changes(self, changes: tuple[tuple[Change, str], ...]) -> None:
        for change, raw_path in changes:
            path = Path(raw_path)
            key = _path_key(path)
            if key == self._health_probe_key:
                if change == Change.added and self._health_probe_event is not None:
                    self._health_probe_event.set()
                continue
            if change not in {Change.added, Change.modified, Change.deleted}:
                continue
            current = self._pending_events.get(key)
            self._pending_events[key] = (
                (_coalesce_change(current[0], change), raw_path) if current else (change, raw_path)
            )
        if self._pending_events:
            self._event_signal.set()

    async def _handle_event(self, change: Change, path: Path) -> None:
        try:
            normalized = _path_within_root(path, self.root)
        except OSError:
            return
        if normalized is None:
            return
        key = _path_key(normalized)
        if change == Change.deleted:
            self._known.pop(key, None)
            self._added_seen.pop(key, None)
            self._candidates.pop(key, None)
            return
        if not normalized.exists():
            return
        if normalized.is_dir():
            if change != Change.added:
                return
            try:
                discovered = await asyncio.to_thread(_scan_audio_files, normalized, self.root)
            except (OSError, RuntimeError):
                return
            for _, (source_file, identity) in discovered.items():
                self._discover_added(source_file, identity)
            return
        if normalized.suffix.casefold() not in AUDIO_EXTENSIONS:
            return
        try:
            identity = await asyncio.to_thread(_file_identity, normalized)
        except OSError:
            return
        if change == Change.added:
            self._discover_added(normalized, identity)
            return
        candidate = self._candidates.get(key)
        if candidate is None:
            return
        candidate.last_identity = identity
        candidate.stable_checks = 0
        candidate.next_check_at = time.monotonic() + self._stable_check_interval_seconds
        self._known[key] = (normalized, identity)

    def _apply_recovery_snapshot(self, snapshot: DirectorySnapshot) -> int:
        recovered = 0
        removed = set(self._known) - set(snapshot)
        for key in removed:
            self._known.pop(key, None)
            self._added_seen.pop(key, None)
            self._candidates.pop(key, None)
        for key, (path, identity) in snapshot.items():
            known = self._known.get(key)
            if known is None or not known[1].same_file(identity):
                self._discover_added(path, identity)
                recovered += 1
                continue
            self._known[key] = (path, identity)
        return recovered

    def _discover_added(self, path: Path, identity: FileIdentity) -> None:
        key = _path_key(path)
        if self._is_suppressed(key):
            self._known[key] = (path, identity)
            self._added_seen[key] = identity
            self._candidates.pop(key, None)
            return
        seen = self._added_seen.get(key)
        if seen is not None and seen.same_file(identity):
            return
        self._added_seen[key] = identity
        self._known[key] = (path, identity)
        self._candidates[key] = _Candidate(
            path=path,
            last_identity=identity,
            next_check_at=time.monotonic() + self._stable_check_interval_seconds,
        )

    def _is_suppressed(self, key: str) -> bool:
        expires_at = self._suppressed_until.get(key)
        if expires_at is None:
            return False
        if expires_at > time.monotonic():
            return True
        self._suppressed_until.pop(key, None)
        return False

    async def _check_candidates(self) -> None:
        now = time.monotonic()
        for key, candidate in tuple(self._candidates.items()):
            if self._is_suppressed(key):
                self._candidates.pop(key, None)
                continue
            if candidate.next_check_at > now:
                continue
            try:
                identity = await asyncio.to_thread(_file_identity, candidate.path)
            except FileNotFoundError:
                self._candidates.pop(key, None)
                self._known.pop(key, None)
                self._added_seen.pop(key, None)
                continue
            except OSError:
                candidate.next_check_at = now + self._stable_check_interval_seconds
                continue
            if candidate.last_identity.same_content_state(identity):
                candidate.stable_checks += 1
            else:
                candidate.stable_checks = 0
            candidate.last_identity = identity
            self._known[key] = (candidate.path, identity)
            candidate.next_check_at = now + self._stable_check_interval_seconds
            if candidate.stable_checks < self._required_stable_checks:
                continue
            self._file_sequence += 1
            event_id = f"{self.generation[:12]}-{self._file_sequence}"
            try:
                accepted = await self._submit_file(candidate.path, event_id)
            except Exception as exc:  # noqa: BLE001
                self._log(
                    f"目录监听文件提交失败：文件={candidate.path}，事件={event_id}，错误={exc}",
                    "ERROR",
                )
                accepted = False
            if accepted:
                self._candidates.pop(key, None)

    async def _health_loop(self) -> None:
        while not self._failed:
            await asyncio.sleep(self._health_check_interval_seconds)
            errors: list[str] = []
            for _ in range(2):
                try:
                    if await self._run_health_probe():
                        errors.clear()
                        break
                    errors.append("未收到探测文件新增事件")
                except OSError as exc:
                    errors.append(str(exc))
                await asyncio.sleep(1.0)
            if errors:
                self._schedule_failure(
                    "原生目录监听健康检查失败。",
                    errors[-1],
                )
                return

    async def _run_health_probe(self) -> bool:
        probe_path = self.root / f"{_PROBE_PREFIX}{uuid4().hex}.probe"
        probe_event = asyncio.Event()
        self._health_probe_key = _path_key(probe_path)
        self._health_probe_event = probe_event
        try:
            await asyncio.to_thread(_create_probe_file, probe_path)
            await asyncio.wait_for(
                probe_event.wait(),
                timeout=self._health_probe_timeout_seconds,
            )
            return True
        except TimeoutError:
            return False
        finally:
            with contextlib.suppress(OSError):
                await asyncio.to_thread(probe_path.unlink, True)
            self._health_probe_key = None
            self._health_probe_event = None

    def _schedule_failure(self, message: str, detail: str) -> None:
        if self._failed or self._stopping:
            return
        self._failed = True
        self._watch_stop.set()
        self._failure_task = asyncio.create_task(
            self._deliver_failure(message, detail),
            name="musicpilot-directory-monitor-failure",
        )

    async def _deliver_failure(self, message: str, detail: str) -> None:
        self._log(f"{message} 目录={self.root}，原因={detail}", "ERROR")
        try:
            await self._on_failed(message, detail)
        except Exception:  # noqa: BLE001
            logger.exception("Directory monitor failure callback failed")


def _coalesce_change(current: Change, incoming: Change) -> Change:
    if incoming == Change.deleted:
        return Change.deleted
    if incoming == Change.added:
        return Change.added
    if current == Change.added:
        return Change.added
    return incoming


def _scan_audio_files(
    root: Path,
    boundary: Path | None = None,
) -> DirectorySnapshot:
    boundary = (boundary or root).expanduser().resolve(strict=False)
    directory = _path_within_root(root, boundary)
    if directory is None or not directory.exists():
        raise FileNotFoundError(root)
    if not directory.is_dir():
        raise NotADirectoryError(root)
    result: DirectorySnapshot = {}
    for path in directory.rglob("*"):
        if path.suffix.casefold() not in AUDIO_EXTENSIONS or not path.is_file():
            continue
        normalized = _path_within_root(path, boundary)
        if normalized is None:
            continue
        try:
            identity = _file_identity(normalized)
        except OSError:
            continue
        result[_path_key(normalized)] = (normalized, identity)
    return result


def _create_probe_file(path: Path) -> None:
    with path.open("xb"):
        pass


def _probe_directory_path(root: Path) -> Path:
    directory = root.expanduser().resolve(strict=False)
    if not directory.exists():
        raise DirectoryMonitorProbeError(
            f"源目录不存在：{directory}",
            polling_available=False,
        )
    if not directory.is_dir():
        raise DirectoryMonitorProbeError(
            f"源路径不是目录：{directory}",
            polling_available=False,
        )
    return directory


def _filesystem_type_for_path(path: Path) -> str | None:
    try:
        mountinfo = _MOUNTINFO_PATH.read_text(encoding="utf-8", errors="surrogateescape")
    except OSError:
        return None
    return _filesystem_type_from_mountinfo(path, mountinfo)


def _filesystem_type_from_mountinfo(path: Path, mountinfo: str) -> str | None:
    target = path.expanduser().resolve(strict=False)
    best_depth = -1
    filesystem_type: str | None = None
    for line in mountinfo.splitlines():
        mount_fields, separator, filesystem_fields = line.partition(" - ")
        if not separator:
            continue
        mount_parts = mount_fields.split()
        filesystem_parts = filesystem_fields.split()
        if len(mount_parts) < 5 or not filesystem_parts:
            continue
        mount_point = Path(_decode_mountinfo_path(mount_parts[4]))
        try:
            target.relative_to(mount_point)
        except ValueError:
            continue
        depth = len(mount_point.parts)
        if depth >= best_depth:
            best_depth = depth
            filesystem_type = filesystem_parts[0].casefold()
    return filesystem_type


def _decode_mountinfo_path(value: str) -> str:
    return _MOUNTINFO_ESCAPE_PATTERN.sub(
        lambda match: chr(int(match.group(1), 8)),
        value,
    )


def _file_identity(path: Path) -> FileIdentity:
    stat = path.stat()
    return FileIdentity(
        size=stat.st_size,
        modified_ns=stat.st_mtime_ns,
        device=stat.st_dev,
        inode=stat.st_ino,
        created_ns=stat.st_ctime_ns,
    )


def _path_within_root(path: Path, root: Path) -> Path | None:
    normalized = path.expanduser().resolve(strict=False)
    boundary = root.expanduser().resolve(strict=False)
    try:
        normalized.relative_to(boundary)
    except ValueError:
        return None
    return normalized


def _path_key(path: Path) -> str:
    value = path.as_posix()
    return value.casefold() if os.name == "nt" else value
