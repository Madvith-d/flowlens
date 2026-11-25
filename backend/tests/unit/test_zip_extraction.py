"""Unit tests: safe ZIP extraction (traversal, links, limits, zip bombs)."""

import io
import zipfile

import pytest

from app.services.ingestion.zip_archive import extract_zip, looks_like_zip

LIMITS = dict(
    max_file_count=20,
    max_total_bytes=1024 * 1024,
    max_file_bytes=256 * 1024,
    max_compression_ratio=200,
)


def build_zip(entries: list[tuple[str, bytes]]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, mode="w", compression=zipfile.ZIP_DEFLATED) as bundle:
        for name, data in entries:
            bundle.writestr(name, data)
    return buffer.getvalue()


def test_valid_zip_extracts_and_skips_exclusions(tmp_path):
    archive = build_zip(
        [
            ("app/main.py", b"x = 1\n"),
            ("pkg/sub/utils.py", b"def f():\n    pass\n"),
            (".git/config", b"skip me\n"),
            ("__pycache__/m.pyc", b"skip"),
            ("README.md", b"# hi\n"),
        ]
    )
    result = extract_zip(archive, tmp_path / "snap", **LIMITS)
    assert result.stored_paths == ["app/main.py", "pkg/sub/utils.py", "README.md"]
    assert sorted(result.skipped_paths) == [".git/config", "__pycache__/m.pyc"]
    snap = tmp_path / "snap"
    assert (snap / "app" / "main.py").read_text() == "x = 1\n"
    assert not (snap / ".git").exists()


def test_traversal_entry_rejected(tmp_path):
    archive = build_zip([("../escape.py", b"boom\n")])
    with pytest.raises(ValueError, match="traversal"):
        extract_zip(archive, tmp_path / "snap", **LIMITS)


def test_absolute_path_rejected(tmp_path):
    archive = build_zip([("/etc/passwd", b"boom\n")])
    with pytest.raises(ValueError, match="absolute"):
        extract_zip(archive, tmp_path / "snap", **LIMITS)


def test_symlink_entries_skipped(tmp_path):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, mode="w") as bundle:
        bundle.writestr("real.py", b"ok\n")
        info = zipfile.ZipInfo("link.py")
        info.external_attr = (0o120777 << 16)  # symlink mode bits
        bundle.writestr(info, "../../outside")
    result = extract_zip(buffer.getvalue(), tmp_path / "snap", **LIMITS)
    assert result.stored_paths == ["real.py"]
    assert "link.py" in result.skipped_paths
    assert not (tmp_path / "snap" / "link.py").exists()


def test_duplicate_entries_rejected(tmp_path):
    archive = build_zip([("app/main.py", b"a = 1\n"), ("./app/main.py", b"a = 2\n")])
    with pytest.raises(ValueError, match="duplicate"):
        extract_zip(archive, tmp_path / "snap", **LIMITS)


def test_file_count_limit(tmp_path):
    archive = build_zip([("a.py", b"1"), ("b.py", b"2"), ("c.py", b"3")])
    with pytest.raises(ValueError, match="file-count"):
        extract_zip(archive, tmp_path / "snap", **{**LIMITS, "max_file_count": 2})


def test_per_file_size_limit(tmp_path):
    archive = build_zip([("big.py", b"a" * 4096)])
    with pytest.raises(ValueError, match="per-file size"):
        extract_zip(archive, tmp_path / "snap", **{**LIMITS, "max_file_bytes": 1024})


def test_total_size_limit(tmp_path):
    archive = build_zip([("one.py", b"a" * 800), ("two.py", b"b" * 800)])
    with pytest.raises(ValueError, match="uncompressed size"):
        extract_zip(archive, tmp_path / "snap", **{**LIMITS, "max_total_bytes": 1000})


def test_zip_bomb_ratio_rejected(tmp_path):
    # 2 MiB of zeros compresses to a few hundred bytes → ratio far above limit.
    archive = build_zip([("bomb.py", b"\0" * (2 * 1024 * 1024))])
    with pytest.raises(ValueError, match="compression-ratio"):
        extract_zip(
            archive,
            tmp_path / "snap",
            **{**LIMITS, "max_total_bytes": 8 * 1024 * 1024, "max_file_bytes": 4 * 1024 * 1024},
        )


def test_non_zip_rejected(tmp_path):
    assert looks_like_zip(b"not-a-zip") is False
    with pytest.raises(ValueError, match="not a ZIP"):
        extract_zip(b"not-a-zip", tmp_path / "snap", **LIMITS)


def test_truncated_zip_rejected(tmp_path):
    archive = build_zip([("app/main.py", b"x = 1\n")])
    with pytest.raises(ValueError, match="not a readable ZIP"):
        extract_zip(archive[:20], tmp_path / "snap", **LIMITS)


def test_no_files_escaped_destination(tmp_path):
    archive = build_zip([("app/deep/nested/mod.py", b"x = 1\n")])
    extract_zip(archive, tmp_path / "snap", **LIMITS)
    outside = list(tmp_path.rglob("mod.py"))
    assert len(outside) == 1
    assert outside[0].is_relative_to(tmp_path / "snap")
