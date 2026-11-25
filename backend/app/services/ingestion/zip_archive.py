"""Safe ZIP extraction for uploaded source snapshots (Phase 4A).

Uploaded archives are untrusted. Extraction:
- validates the archive is a real ZIP (magic + central directory),
- normalizes and validates every entry path (no absolutes, no `..`),
- rejects symlink/hardlink entries and encrypted entries,
- rejects duplicate normalized entry names,
- enforces file-count, per-file size, total uncompressed size, and a
  compression-ratio limit (zip-bomb protection),
- writes entries inside the destination directory only,
- skips documented exclusions (`.git`, `__pycache__`, virtualenvs, ...).

The analyzed content is never imported, executed, or installed.
"""

import io
import logging
import os
import stat
import zipfile

from app.services.ingestion.archive import (
    ExtractionResult,
    UnsafeArchiveError,
    is_excluded,
    validate_entry_name,
)

logger = logging.getLogger("flowlens.ingestion.zip")

ZIP_MAGIC = b"PK\x03\x04"

# Compression-ratio checks only apply above this size: tiny, highly repetitive
# source files legitimately compress far beyond the ratio (they are already
# bounded by the per-file and total size limits).
MIN_RATIO_CHECK_BYTES = 1_048_576


def looks_like_zip(archive_bytes: bytes) -> bool:
    return archive_bytes[:4] == ZIP_MAGIC


def _is_symlink(info: zipfile.ZipInfo) -> bool:
    # Unix mode is stored in the high 16 bits of external_attr.
    mode = info.external_attr >> 16
    return stat.S_ISLNK(mode)


def _is_encrypted(info: zipfile.ZipInfo) -> bool:
    return bool(info.flag_bits & 0x1)


def extract_zip(
    archive_bytes: bytes,
    dest_dir,
    *,
    max_file_count: int,
    max_total_bytes: int,
    max_file_bytes: int,
    max_compression_ratio: int = 200,
) -> ExtractionResult:
    """Extract a ZIP archive into `dest_dir` after validating every entry."""
    if not looks_like_zip(archive_bytes):
        raise UnsafeArchiveError("upload is not a ZIP archive")
    dest_root = os.path.realpath(dest_dir)
    result = ExtractionResult()
    seen: set[str] = set()
    total_bytes = 0
    file_count = 0
    try:
        archive = zipfile.ZipFile(io.BytesIO(archive_bytes))
    except (zipfile.BadZipFile, OSError, EOFError) as exc:
        raise UnsafeArchiveError("upload is not a readable ZIP archive") from exc
    with archive:
        for info in archive.infolist():
            if info.is_dir():
                # Directory entries are validated so traversal is rejected
                # early; their files create the parents on demand.
                validate_entry_name(info.filename.rstrip("/") or ".")
                continue
            if _is_encrypted(info):
                raise UnsafeArchiveError("encrypted ZIP entries are not supported")
            if _is_symlink(info):
                # Never materialize links; report and skip.
                result.skipped_paths.append(info.filename)
                continue
            normalized = validate_entry_name(info.filename)
            if normalized is None:
                result.skipped_paths.append(info.filename)
                continue
            if normalized in seen:
                raise UnsafeArchiveError(f"duplicate archive entry: {normalized!r}")
            seen.add(normalized)
            if is_excluded(normalized):
                # Exclusions are reported so callers can surface ignored files.
                result.skipped_paths.append(info.filename)
                continue
            if info.file_size > max_file_bytes:
                raise UnsafeArchiveError("archive entry exceeds the per-file size limit")
            if (
                info.file_size > MIN_RATIO_CHECK_BYTES
                and info.compress_size > 0
                and info.file_size / info.compress_size > max_compression_ratio
            ):
                raise UnsafeArchiveError("archive entry exceeds the compression-ratio limit")
            file_count += 1
            if file_count > max_file_count:
                raise UnsafeArchiveError("archive exceeds the file-count limit")
            target_path = os.path.realpath(os.path.join(dest_root, normalized))
            if target_path != dest_root and not target_path.startswith(dest_root + os.sep):
                raise UnsafeArchiveError("archive entry escapes the snapshot directory")
            os.makedirs(os.path.dirname(target_path), exist_ok=True)
            try:
                with archive.open(info) as source, open(target_path, "wb") as out:
                    written = 0
                    while True:
                        chunk = source.read(64 * 1024)
                        if not chunk:
                            break
                        total_bytes += len(chunk)
                        written += len(chunk)
                        if total_bytes > max_total_bytes:
                            raise UnsafeArchiveError(
                                "archive exceeds the uncompressed size limit"
                            )
                        if written > max_file_bytes:
                            raise UnsafeArchiveError(
                                "archive entry exceeds the per-file size limit"
                            )
                        out.write(chunk)
            except (zipfile.BadZipFile, OSError, RuntimeError) as exc:
                # RuntimeError covers CRC/decryption failures from zipfile.
                raise UnsafeArchiveError("archive entry could not be extracted") from exc
            if written != info.file_size:
                raise UnsafeArchiveError("archive entry size mismatch")
            result.stored_paths.append(normalized)
    result.total_bytes = total_bytes
    return result
