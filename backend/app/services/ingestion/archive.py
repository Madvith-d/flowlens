"""Safe archive extraction for immutable source snapshots (GitHub tarballs).

All repository content is untrusted. This module never executes repository
code, never imports it, and never resolves symlinks outside the destination
directory. Every entry path is normalized and validated before extraction.

Limits (configurable in settings):
- file count
- total uncompressed size
- per-file size (via the same total-size accounting, enforced per entry)

Skipped entries are reported so callers can surface exclusions.
"""

import hashlib
import io
import logging
import tarfile
from dataclasses import dataclass, field
from pathlib import PurePosixPath

logger = logging.getLogger("flowlens.ingestion")

# Default exclusions applied to every snapshot (documented in docs).
DEFAULT_EXCLUDED_PARTS = {".git", "__pycache__", ".tox", ".mypy_cache", ".pytest_cache", "node_modules", ".venv", "venv"}
MAX_PATH_LENGTH = 400


@dataclass
class ExtractionResult:
    stored_paths: list[str] = field(default_factory=list)
    skipped_paths: list[str] = field(default_factory=list)
    total_bytes: int = 0


class UnsafeArchiveError(ValueError):
    """Raised when an archive contains unsafe or oversized content."""


def archive_content_hash(archive_bytes: bytes) -> str:
    """Stable digest of the raw archive bytes (provenance fingerprint)."""
    return hashlib.sha256(archive_bytes).hexdigest()


def _is_excluded(normalized: str) -> bool:
    parts = PurePosixPath(normalized).parts
    return any(part in DEFAULT_EXCLUDED_PARTS for part in parts)


def _validate_entry_name(name: str) -> str | None:
    """Return a normalized, safe relative path or None when skipped.

    Rejects: absolute paths, `..` traversal, backslashes, NUL bytes,
    over-long names, and device/symlink entries (validated by the caller).
    """
    if not name or len(name) > MAX_PATH_LENGTH:
        return None
    if "\x00" in name:
        raise UnsafeArchiveError("null byte in archive entry name")
    if name.startswith("/") or name.startswith("\\") or (len(name) > 1 and name[1] == ":"):
        raise UnsafeArchiveError(f"absolute path in archive entry")
    if name.strip() == ".":
        return None
    normalized = name.replace("\\", "/")
    parts = [part for part in PurePosixPath(normalized).parts if part not in (".", "")]
    if not parts:
        return None
    if any(part == ".." for part in parts):
        raise UnsafeArchiveError("path traversal in archive entry")
    return "/".join(parts)


def extract_tar_gz(
    archive_bytes: bytes,
    dest_dir,
    *,
    max_file_count: int,
    max_total_bytes: int,
) -> ExtractionResult:
    """Extract a tar.gz archive into `dest_dir` after validating every entry.

    `dest_dir` must already exist and be dedicated to the snapshot. Entries
    are written only after the normalized path is confirmed to stay inside
    the destination directory.
    """
    import os

    dest_root = os.path.realpath(dest_dir)
    result = ExtractionResult()
    total_bytes = 0
    file_count = 0
    try:
        tar = tarfile.open(fileobj=io.BytesIO(archive_bytes), mode="r:gz")
    except (tarfile.TarError, OSError, EOFError) as exc:
        raise UnsafeArchiveError("archive is not a valid tar.gz stream") from exc
    with tar:
        for member in tar:
            normalized = _validate_entry_name(member.name)
            if normalized is None:
                result.skipped_paths.append(member.name)
                continue
            if member.issym() or member.islnk():
                # Never materialize links from untrusted archives.
                result.skipped_paths.append(member.name)
                continue
            target_path = os.path.realpath(os.path.join(dest_root, normalized))
            if target_path != dest_root and not target_path.startswith(dest_root + os.sep):
                raise UnsafeArchiveError("archive entry escapes the snapshot directory")
            if _is_excluded(normalized):
                result.skipped_paths.append(member.name)
                continue
            if member.isdir():
                os.makedirs(target_path, exist_ok=True)
                continue
            if not member.isfile():
                raise UnsafeArchiveError(f"unsupported archive entry type for {member.name!r}")
            file_count += 1
            if file_count > max_file_count:
                raise UnsafeArchiveError("archive exceeds the file-count limit")
            if member.size > max_total_bytes:
                raise UnsafeArchiveError("archive entry exceeds the size limit")
            extract = tar.extractfile(member)
            if extract is None:
                result.skipped_paths.append(member.name)
                continue
            os.makedirs(os.path.dirname(target_path), exist_ok=True)
            written = 0
            with open(target_path, "wb") as out:
                while True:
                    chunk = extract.read(64 * 1024)
                    if not chunk:
                        break
                    written += len(chunk)
                    total_bytes += len(chunk)
                    if total_bytes > max_total_bytes:
                        raise UnsafeArchiveError("archive exceeds the uncompressed size limit")
                    out.write(chunk)
            if written != member.size:
                raise UnsafeArchiveError("archive entry size mismatch")
            result.stored_paths.append(normalized)
    result.total_bytes = total_bytes
    return result
