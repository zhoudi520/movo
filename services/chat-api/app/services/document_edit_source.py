"""Load a Word artifact as editable Markdown for the chat document editor."""

from __future__ import annotations

import asyncio

from app.enterprise_capabilities.artifacts.references import require_owned_artifact
from app.services.document_parser import DocumentParserService
from app.utils.oss_uploader import AliyunOSSUploader


async def docx_markdown_source(*, object_path: str, user_id: str) -> str:
    owned = require_owned_artifact({"object_path": object_path}, user_id=user_id)
    path = owned["object_path"]
    if not path.lower().endswith(".docx"):
        raise ValueError("Only DOCX documents can be opened as Markdown")
    content = await asyncio.to_thread(AliyunOSSUploader().read_bytes, path)
    parsed = await asyncio.to_thread(
        DocumentParserService._build_docx_parse_from_bytes,
        content,
        filename=path.rsplit("/", 1)[-1],
        upload_images=True,
        user_id=user_id,
    )
    return str(parsed.get("markdown") or "").strip()
