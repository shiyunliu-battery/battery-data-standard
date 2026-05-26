"""Safe archive expansion for batch conversion."""

from __future__ import annotations

import tarfile
import tempfile
import zipfile
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

from .exceptions import FileIOError, UnsupportedFormatError

ARCHIVE_SUFFIXES = (".zip", ".tar", ".tar.gz", ".tgz")
DEFAULT_MAX_ARCHIVE_DEPTH = 2
GIB = 1024 * 1024 * 1024
DEFAULT_MAX_MEMBER_BYTES = 100 * GIB
DEFAULT_MAX_TOTAL_BYTES = 100 * GIB


@dataclass(frozen=True)
class BatchSource:
    path: Path
    relative_path: Path
    archive_path: Path | None = None
    archive_member: str | None = None


@contextmanager
def batch_sources(
    input_path: Path,
    *,
    recursive: bool = False,
    supported_suffixes: set[str],
    max_archive_depth: int = DEFAULT_MAX_ARCHIVE_DEPTH,
    max_member_bytes: int = DEFAULT_MAX_MEMBER_BYTES,
    max_total_bytes: int = DEFAULT_MAX_TOTAL_BYTES,
) -> Iterator[list[BatchSource]]:
    with tempfile.TemporaryDirectory(prefix="bds-archive-") as temp_dir:
        temp_root = Path(temp_dir)
        sources: list[BatchSource] = []
        if input_path.is_file():
            if is_archive_path(input_path):
                sources.extend(
                    _expand_archive_sources(
                        input_path,
                        temp_root / input_path.stem,
                        Path(input_path.stem),
                        supported_suffixes=supported_suffixes,
                        depth=0,
                        max_depth=max_archive_depth,
                        max_member_bytes=max_member_bytes,
                        max_total_bytes=max_total_bytes,
                    )
                )
            elif is_supported_source_path(input_path, supported_suffixes):
                sources.append(BatchSource(input_path, Path(input_path.name)))
            else:
                sources.append(BatchSource(input_path, Path(input_path.name)))
        elif input_path.is_dir():
            pattern = "**/*" if recursive else "*"
            for path in sorted(input_path.glob(pattern)):
                if not path.is_file():
                    continue
                relative = path.relative_to(input_path)
                if is_archive_path(path):
                    sources.extend(
                        _expand_archive_sources(
                            path,
                            temp_root / safe_member_path(relative),
                            relative.with_suffix(""),
                            supported_suffixes=supported_suffixes,
                            depth=0,
                            max_depth=max_archive_depth,
                            max_member_bytes=max_member_bytes,
                            max_total_bytes=max_total_bytes,
                        )
                    )
                elif is_supported_source_path(path, supported_suffixes):
                    sources.append(BatchSource(path, relative))
        else:
            raise FileIOError(f"Input path does not exist: {input_path}")
        yield sources


def is_archive_path(path: Path) -> bool:
    suffixes = "".join(path.suffixes).lower()
    return any(suffixes.endswith(suffix) for suffix in ARCHIVE_SUFFIXES)


def is_supported_source_path(path: Path, supported_suffixes: set[str]) -> bool:
    suffix = path.suffix.lower()
    if suffix in supported_suffixes:
        return True
    return len(suffix) == 4 and suffix[1:].isdigit()


def safe_member_path(path: str | Path) -> Path:
    parts = []
    for part in Path(path).parts:
        if part in {"", ".", ".."}:
            continue
        clean = "".join(ch if ch.isalnum() or ch in "._- " else "_" for ch in part).strip()
        if clean:
            parts.append(clean)
    return Path(*parts) if parts else Path("member")


def _expand_archive_sources(
    archive_path: Path,
    target_root: Path,
    relative_root: Path,
    *,
    supported_suffixes: set[str],
    depth: int,
    max_depth: int,
    max_member_bytes: int,
    max_total_bytes: int,
) -> list[BatchSource]:
    if depth > max_depth:
        raise UnsupportedFormatError(f"Archive nesting exceeds maximum depth {max_depth}: {archive_path}")
    target_root.mkdir(parents=True, exist_ok=True)
    if zipfile.is_zipfile(archive_path):
        members = _extract_zip(archive_path, target_root, max_member_bytes, max_total_bytes)
    elif tarfile.is_tarfile(archive_path):
        members = _extract_tar(archive_path, target_root, max_member_bytes, max_total_bytes)
    else:
        raise UnsupportedFormatError(f"Unsupported archive format: {archive_path}")

    sources: list[BatchSource] = []
    for member_path, member_name in members:
        relative = relative_root / safe_member_path(member_name)
        if is_archive_path(member_path) and depth < max_depth:
            sources.extend(
                _expand_archive_sources(
                    member_path,
                    target_root / safe_member_path(member_name).with_suffix(""),
                    relative.with_suffix(""),
                    supported_suffixes=supported_suffixes,
                    depth=depth + 1,
                    max_depth=max_depth,
                    max_member_bytes=max_member_bytes,
                    max_total_bytes=max_total_bytes,
                )
            )
        elif is_supported_source_path(member_path, supported_suffixes):
            sources.append(
                BatchSource(
                    member_path,
                    relative,
                    archive_path=archive_path,
                    archive_member=member_name,
                )
            )
    return sources


def _extract_zip(
    archive_path: Path,
    target_root: Path,
    max_member_bytes: int,
    max_total_bytes: int,
) -> list[tuple[Path, str]]:
    extracted: list[tuple[Path, str]] = []
    total = 0
    with zipfile.ZipFile(archive_path) as archive:
        for info in archive.infolist():
            if info.is_dir():
                continue
            total += info.file_size
            _check_archive_limits(info.filename, info.file_size, total, max_member_bytes, max_total_bytes)
            target = _safe_target(target_root, info.filename)
            target.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(info) as source, target.open("wb") as handle:
                handle.write(source.read())
            extracted.append((target, info.filename))
    return extracted


def _extract_tar(
    archive_path: Path,
    target_root: Path,
    max_member_bytes: int,
    max_total_bytes: int,
) -> list[tuple[Path, str]]:
    extracted: list[tuple[Path, str]] = []
    total = 0
    with tarfile.open(archive_path) as archive:
        for member in archive.getmembers():
            if not member.isfile():
                continue
            total += member.size
            _check_archive_limits(member.name, member.size, total, max_member_bytes, max_total_bytes)
            source = archive.extractfile(member)
            if source is None:
                continue
            target = _safe_target(target_root, member.name)
            target.parent.mkdir(parents=True, exist_ok=True)
            with source, target.open("wb") as handle:
                handle.write(source.read())
            extracted.append((target, member.name))
    return extracted


def _check_archive_limits(
    member_name: str,
    member_size: int,
    total_size: int,
    max_member_bytes: int,
    max_total_bytes: int,
) -> None:
    if member_size > max_member_bytes:
        raise UnsupportedFormatError(f"Archive member {member_name} exceeds size limit.")
    if total_size > max_total_bytes:
        raise UnsupportedFormatError("Archive extracted size exceeds total limit.")


def _safe_target(target_root: Path, member_name: str) -> Path:
    target = (target_root / safe_member_path(member_name)).resolve()
    root = target_root.resolve()
    if root != target and root not in target.parents:
        raise UnsupportedFormatError(f"Unsafe archive member path: {member_name}")
    return target
