from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

FileIdentity = tuple[int, int]


@dataclass(frozen=True, slots=True)
class LibraryStorageUsage:
    source_size_bytes: int
    expansion_size_bytes: int

    @property
    def total_size_bytes(self) -> int:
        return self.source_size_bytes + self.expansion_size_bytes


def calculate_library_storage_usage(
    source_directory: Path,
    mapped_directory: Path | None,
) -> LibraryStorageUsage:
    source_root = _normalized_path(source_directory)
    mapped_root = _normalized_path(mapped_directory) if mapped_directory is not None else None
    _require_directory(source_root, "Source directory")
    if mapped_root is not None:
        _require_directory(mapped_root, "Mapped directory")

    mapped_inside_source = (
        mapped_root
        if mapped_root is not None
        and mapped_root != source_root
        and mapped_root.is_relative_to(source_root)
        else None
    )
    source_size, source_files = _directory_size(
        source_root,
        excluded_directory=mapped_inside_source,
    )
    if mapped_root is None or mapped_root == source_root:
        return LibraryStorageUsage(source_size_bytes=source_size, expansion_size_bytes=0)

    expansion_size, _ = _directory_size(mapped_root, excluded_files=source_files)
    return LibraryStorageUsage(
        source_size_bytes=source_size,
        expansion_size_bytes=expansion_size,
    )


def normalize_storage_path(path: Path | None) -> str:
    if path is None:
        return ""
    return str(_normalized_path(path))


def _directory_size(
    root: Path,
    *,
    excluded_directory: Path | None = None,
    excluded_files: set[FileIdentity] | None = None,
) -> tuple[int, set[FileIdentity]]:
    total = 0
    files: set[FileIdentity] = set()
    stack = [root]
    while stack:
        directory = stack.pop()
        try:
            entries = os.scandir(directory)
        except FileNotFoundError:
            if directory == root:
                raise
            continue
        with entries:
            for entry in entries:
                try:
                    if entry.is_dir(follow_symlinks=False):
                        child = Path(entry.path)
                        if excluded_directory is None or child != excluded_directory:
                            stack.append(child)
                        continue
                    if not entry.is_file(follow_symlinks=False):
                        continue
                    stat = entry.stat(follow_symlinks=False)
                except FileNotFoundError:
                    continue
                identity = (int(stat.st_dev), int(stat.st_ino))
                if identity in files or excluded_files is not None and identity in excluded_files:
                    continue
                files.add(identity)
                total += int(stat.st_size)
    return total, files


def _normalized_path(path: Path) -> Path:
    return Path(os.path.abspath(os.path.expanduser(str(path))))


def _require_directory(path: Path, label: str) -> None:
    if not path.is_dir():
        raise FileNotFoundError(f"{label} does not exist: {path}")
