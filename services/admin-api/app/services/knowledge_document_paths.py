"""Storage key helpers for knowledge documents."""

from __future__ import annotations

from app.core.config import settings


def storage_prefix() -> str:
    """Return normalized knowledge storage prefix."""
    return settings.knowledge_oss_prefix.strip().strip("/") or "knowledge-documents"


def document_artifact_prefix(main_id: str, document_id: str) -> str:
    """Return artifact directory prefix for a document."""
    return f"{storage_prefix()}/{main_id}/{document_id}/artifacts"


def parsed_markdown_key(main_id: str, document_id: str) -> str:
    """Return storage key for internal parsed markdown."""
    return f"{document_artifact_prefix(main_id, document_id)}/parsed.md"
