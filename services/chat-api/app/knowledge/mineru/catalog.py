"""List MinerU-mode knowledge documents for QA selection."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.core.db import get_db


@dataclass
class MineruDocumentInfo:
    """Catalog entry for a MinerU knowledge document."""

    document_id: str
    name: str
    directory_id: str
    content_summary: str
    parsed_markdown_key: str
    readable: bool


async def list_mineru_documents(
    *,
    main_id: str,
    knowledge_base_ids: list[str] | None,
) -> list[MineruDocumentInfo]:
    """
    List mineru documents in scope that are ready for QA.

    Args:
        main_id: Tenant id.
        knowledge_base_ids: Directory ids filter; empty means all directories.

    Returns:
        Document catalog entries.
    """
    query: dict[str, Any] = {
        "main_id": main_id,
        "deleted_at": None,
        "learning_mode": "mineru",
        "$or": [{"scope": "organization"}, {"scope": {"$exists": False}}],
    }
    ids = [str(item).strip() for item in list(knowledge_base_ids or []) if str(item).strip()]
    if ids:
        query["knowledge_base_id"] = {"$in": ids}
    rows = await get_db().knowledge_documents.find(query).sort("updated_at", -1).to_list(length=500)
    items: list[MineruDocumentInfo] = []
    for row in rows:
        summary = str(row.get("content_summary") or "").strip()
        markdown_key = str(row.get("parsed_markdown_key") or "").strip()
        parse_status = str(row.get("parse_status") or "")
        readable = parse_status == "succeeded" and bool(summary) and bool(markdown_key)
        items.append(
            MineruDocumentInfo(
                document_id=str(row.get("_id") or ""),
                name=str(row.get("name") or row.get("original_filename") or ""),
                directory_id=str(row.get("knowledge_base_id") or ""),
                content_summary=summary,
                parsed_markdown_key=markdown_key,
                readable=readable,
            )
        )
    return items
