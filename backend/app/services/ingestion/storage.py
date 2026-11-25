"""Snapshot storage abstraction.

Source files are stored under `storage_root/snapshots/{snapshot_id}/`, outside
any public/static directory, and never executed. Storage paths are internal:
they must not appear in API responses.
"""

import logging
import os
import shutil

from app.core.config import Settings

logger = logging.getLogger("flowlens.storage")


class UnsafeSnapshotPathError(ValueError):
    """Raised when a computed snapshot path would escape the storage root."""


class SnapshotStorage:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._root = os.path.realpath(os.path.join(settings.storage_root, "snapshots"))

    def _snapshot_root(self) -> str:
        return self._root

    def snapshot_dir(self, snapshot_id: str) -> str:
        """Validated per-snapshot directory path (creates the directory)."""
        if not snapshot_id or "/" in snapshot_id or snapshot_id in (".", ".."):
            raise UnsafeSnapshotPathError("invalid snapshot identifier")
        path = os.path.realpath(os.path.join(self._root, snapshot_id))
        if not path.startswith(self._snapshot_root() + os.sep):
            raise UnsafeSnapshotPathError("snapshot path escapes the storage root")
        os.makedirs(path, exist_ok=True)
        return path

    def delete_snapshot(self, snapshot_id: str) -> None:
        """Remove a snapshot's files (best-effort; DB rows govern lifecycle)."""
        try:
            shutil.rmtree(self.snapshot_dir_parent_only(snapshot_id))
        except OSError:  # pragma: no cover - cleanup is best-effort
            logger.warning("snapshot cleanup failed", extra={"context": {}})

    def snapshot_dir_parent_only(self, snapshot_id: str) -> str:
        if not snapshot_id or "/" in snapshot_id or snapshot_id in (".", ".."):
            raise UnsafeSnapshotPathError("invalid snapshot identifier")
        return os.path.join(self._root, snapshot_id)
