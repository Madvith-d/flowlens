"""Unit tests: safe tar.gz extraction (traversal, links, limits, exclusions)."""

import io
import tarfile

import pytest

from app.services.ingestion.archive import (
    UnsafeArchiveError,
    archive_content_hash,
    extract_tar_gz,
)


def build_tar(entries: list[tuple[str, bytes, str]]) -> bytes:
    """Build an in-memory tar.gz with (name, data, kind) entries.

    kind: "file" or "symlink" (link target is packed into the data bytes).
    """
    archive = io.BytesIO()
    with tarfile.open(fileobj=archive, mode="w:gz") as tar:
        for name, data, kind in entries:
            info = tarfile.TarInfo(name=name)
            info.mtime = 1_700_000_000
            if kind == "symlink":
                info.type = tarfile.SYMTYPE
                info.linkname = data.decode()
                info.size = 0
                tar.addfile(info)
            else:
                info.size = len(data)
                tar.addfile(info, io.BytesIO(data))
    return archive.getvalue()


def _extract(tmp_path, entries, **limits):
    archive = build_tar(entries)
    limits.setdefault("max_file_count", 100)
    limits.setdefault("max_total_bytes", 1024 * 1024)
    return extract_tar_gz(archive, tmp_path / "snap", **limits)


def test_valid_archive_extracts_files(tmp_path):
    result = _extract(
        tmp_path,
        [
            ("app/main.py", b"x = 1\n", "file"),
            ("pkg/sub/utils.py", b"def f():\n    pass\n", "file"),
        ],
    )
    assert result.stored_paths == ["app/main.py", "pkg/sub/utils.py"]
    snap = tmp_path / "snap"
    assert (snap / "app" / "main.py").read_text() == "x = 1\n"
    assert (snap / "pkg" / "sub" / "utils.py").is_file()


def test_traversal_entry_rejected(tmp_path):
    with pytest.raises(UnsafeArchiveError, match="traversal"):
        _extract(tmp_path, [("../escape.py", b"boom\n", "file")])


def test_absolute_path_rejected(tmp_path):
    with pytest.raises(UnsafeArchiveError, match="absolute"):
        _extract(tmp_path, [("/etc/passwd", b"boom\n", "file")])


def test_symlinks_are_never_materialized(tmp_path):
    result = _extract(
        tmp_path,
        [
            ("real.py", b"ok\n", "file"),
            ("evil.py", b"../../outside", "symlink"),
        ],
    )
    assert result.stored_paths == ["real.py"]
    assert "evil.py" in result.skipped_paths
    assert not (tmp_path / "snap" / "evil.py").exists()


def test_excluded_directories_skipped(tmp_path):
    result = _extract(
        tmp_path,
        [
            (".git/config", b"skip\n", "file"),
            ("__pycache__/m.pyc", b"skip", "file"),
            ("app/mod.py", b"keep\n", "file"),
        ],
    )
    assert result.stored_paths == ["app/mod.py"]
    assert len(result.skipped_paths) == 2


def test_file_count_limit_enforced(tmp_path):
    with pytest.raises(UnsafeArchiveError, match="file-count"):
        _extract(
            tmp_path,
            [("a.py", b"1", "file"), ("b.py", b"2", "file")],
            max_file_count=1,
        )


def test_total_size_limit_enforced(tmp_path):
    with pytest.raises(UnsafeArchiveError, match="size limit"):
        _extract(
            tmp_path,
            [("big.py", b"a" * 2048, "file")],
            max_total_bytes=1024,
        )


def test_invalid_gzip_rejected(tmp_path):
    with pytest.raises(UnsafeArchiveError, match="tar.gz"):
        extract_tar_gz(
            b"not-a-tarball",
            tmp_path / "snap",
            max_file_count=10,
            max_total_bytes=1024,
        )


def test_content_hash_is_stable_and_content_sensitive():
    body_a = build_tar([("app/main.py", b"x = 1\n", "file")])
    body_b = build_tar([("app/main.py", b"x = 1\n", "file")])
    body_c = build_tar([("app/main.py", b"x = 2\n", "file")])
    hash_a = archive_content_hash(body_a)
    assert hash_a == archive_content_hash(body_b)
    assert hash_a != archive_content_hash(body_c)
    assert len(hash_a) == 64
