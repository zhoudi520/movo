"""Read internal knowledge document artifacts from shared storage."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from app.core.config import get_settings


def read_storage_text(doc: dict[str, Any], storage_key: str) -> str:
    """
    Read UTF-8 text from a knowledge document storage key (local storage).

    Args:
        doc: Knowledge document record.
        storage_key: Object key within knowledge storage.

    Returns:
        File contents as string.
    """
    settings = get_settings()
    root = Path(settings.KNOWLEDGE_LOCAL_STORAGE_DIR).expanduser().resolve()
    normalized = storage_key.strip().lstrip("/").replace("\\", "/")
    path = (root / normalized).resolve()
    if root not in path.parents and path != root:
        raise ValueError("invalid storage key")
    if not path.is_file():
        raise FileNotFoundError(f"artifact not found: {storage_key}")
    return path.read_text(encoding="utf-8", errors="ignore")
