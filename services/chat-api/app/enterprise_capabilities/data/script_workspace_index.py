"""Index persisted object-storage files for the authenticated script caller."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.core.config import get_settings
from app.enterprise_capabilities.artifacts.references import user_local_storage_root


def index_user_storage_files(user_id: str, *, max_entries: int = 200) -> list[dict[str, Any]]:
    """List files under the caller's storage prefix (cross-session, same user only)."""
    user_root = user_local_storage_root(user_id)
    if not user_root:
        return []
    root_path = Path(user_root)
    if not root_path.exists():
        return []
    settings = get_settings()
    storage_root = Path(str(settings.LOCAL_STORAGE_PATH or "storage")).expanduser().resolve()
    entries: list[dict[str, Any]] = []
    for path in root_path.rglob("*"):
        if not path.is_file():
            continue
        if path.name.endswith(".meta"):
            continue
        try:
            object_path = path.resolve().relative_to(storage_root).as_posix()
        except ValueError:
            continue
        stat = path.stat()
        entries.append(
            {
                "object_path": object_path,
                "filename": path.name,
                "size_bytes": int(stat.st_size),
                "modified_at": datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat(),
            }
        )
    entries.sort(key=lambda item: str(item.get("modified_at") or ""), reverse=True)
    limit = max(1, min(int(max_entries or 200), 500))
    return entries[:limit]


__all__ = ["index_user_storage_files"]
