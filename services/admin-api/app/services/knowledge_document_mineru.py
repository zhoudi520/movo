"""MinerU upload and parse orchestration for knowledge documents."""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.core.config import settings
from app.core.db import get_db
from app.services.knowledge_document_paths import parsed_markdown_key
from app.services.knowledge_document_summary import generate_and_store_summary
from app.services.knowledge_file_parse_settings import get_effective_file_parse_settings
from app.services.knowledge_storage import read_text_artifact, write_text_artifact

COLLECTION = "knowledge_documents"

PLAIN_SOURCE_EXTENSIONS = {
    "txt",
    "md",
    "markdown",
    "csv",
    "log",
    "json",
    "xml",
    "html",
    "htm",
    "rtf",
}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def is_plain_source_filename(filename: str) -> bool:
    """Return True when the file can be read as plain text without MinerU."""
    ext = Path(filename or "").suffix.lower().lstrip(".")
    return ext in PLAIN_SOURCE_EXTENSIONS


def _request_mineru_parse(doc: dict[str, Any], file_parse: dict[str, Any]) -> str:
    """Enqueue MinerU parse job on document-parser."""
    document_id = str(doc.get("_id") or "")
    base_url = str(settings.document_processing_base_url or "").rstrip("/")
    if not base_url:
        raise RuntimeError("document processing service url is not configured")
    callback_base = str(settings.admin_api_public_base_url or "").rstrip("/")
    from app.services.knowledge_document_paths import document_artifact_prefix

    artifact_prefix = document_artifact_prefix(str(doc.get("main_id") or "default"), document_id)
    payload = {
        "documentId": document_id,
        "mainId": str(doc.get("main_id") or "default"),
        "source": {
            "storageType": str(doc.get("storage_type") or "local"),
            "storageBucket": str(doc.get("storage_bucket") or ""),
            "storageKey": str(doc.get("storage_key") or ""),
            "filename": str(doc.get("original_filename") or doc.get("name") or "document"),
            "mimeType": str(doc.get("mime_type") or ""),
        },
        "artifacts": {
            "storageType": str(doc.get("storage_type") or "local"),
            "storageBucket": str(doc.get("storage_bucket") or ""),
            "storagePrefix": artifact_prefix,
        },
        "callback": {
            "url": f"{callback_base}/api/knowledge/documents/{document_id}/mineru-parse-callback",
            "token": settings.document_processing_callback_token,
        },
        "modelVersion": str(file_parse.get("modelVersion") or "vlm"),
        "language": str(file_parse.get("language") or "ch"),
        "mineru": {
            "serviceUrl": str(file_parse.get("serviceUrl") or ""),
            "apiKey": str(file_parse.get("apiKey") or ""),
        },
    }
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        f"{base_url}/api/jobs/mineru-parse",
        data=data,
        headers={
            "Authorization": f"Bearer {settings.document_processing_service_token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            raw = response.read().decode("utf-8")
            parsed = json.loads(raw) if raw else {}
    except urllib.error.URLError as exc:
        raise RuntimeError(f"document processing service unavailable: {exc}") from exc
    job_id = str(parsed.get("jobId") or "")
    if not job_id:
        raise RuntimeError("document processing service did not return jobId")
    return job_id


async def ingest_plain_text_mineru(doc: dict[str, Any], *, text: str) -> None:
    """
    Store plain text as parsed markdown and generate summary for mineru documents.

    Args:
        doc: Mongo document row (must include _id, main_id, storage fields).
        text: Plain document body.
    """
    main_id = str(doc.get("main_id") or "default")
    document_id = str(doc.get("_id") or "")
    md_key = parsed_markdown_key(main_id, document_id)
    write_text_artifact(doc, md_key, text)
    await get_db()[COLLECTION].update_one(
        {"_id": document_id, "main_id": main_id},
        {
            "$set": {
                "parsed_markdown_key": md_key,
                "parse_status": "running",
                "status": "pending_parse",
                "updated_at": _now(),
            }
        },
    )
    doc["parsed_markdown_key"] = md_key
    try:
        await generate_and_store_summary(document_id, main_id)
    except Exception as exc:
        message = str(exc)[:2000]
        await get_db()[COLLECTION].update_one(
            {"_id": document_id, "main_id": main_id},
            {
                "$set": {
                    "parse_status": "failed",
                    "status": "failed",
                    "parse_error": message,
                    "parse_updated_at": _now(),
                    "updated_at": _now(),
                }
            },
        )
        raise
    await get_db()[COLLECTION].update_one(
        {"_id": document_id, "main_id": main_id},
        {
            "$set": {
                "parse_status": "succeeded",
                "status": "parsed",
                "parse_error": "",
                "parse_updated_at": _now(),
                "updated_at": _now(),
            }
        },
    )


async def read_plain_text_from_storage(doc: dict[str, Any]) -> str:
    """Read plain text from the uploaded storage key with encoding fallbacks."""
    storage_key = str(doc.get("storage_key") or "")
    raw = read_text_artifact(doc, storage_key)
    return raw


async def retry_mineru_learning(doc: dict[str, Any]) -> None:
    """
    Re-run MinerU learning: summary-only when markdown exists, otherwise re-parse.

    Args:
        doc: Knowledge document row.
    """
    main_id = str(doc.get("main_id") or "default")
    document_id = str(doc.get("_id") or "")
    markdown_key = str(doc.get("parsed_markdown_key") or "").strip()
    if markdown_key:
        await get_db()[COLLECTION].update_one(
            {"_id": document_id, "main_id": main_id},
            {
                "$set": {
                    "content_summary": "",
                    "parse_error": "",
                    "parse_status": "running",
                    "status": "pending_parse",
                    "updated_at": _now(),
                }
            },
        )
        await complete_mineru_callback(document_id, main_id, markdown_key=markdown_key)
        return
    await start_mineru_processing(doc)


async def start_mineru_processing(doc: dict[str, Any], *, temp_path: str = "") -> None:
    """
    Start MinerU processing for a document (plain text inline or remote job).

    Args:
        doc: Inserted knowledge document dict.
        temp_path: Optional local temp path for plain text reads.
    """
    main_id = str(doc.get("main_id") or "default")
    document_id = str(doc.get("_id") or "")
    file_parse = await get_effective_file_parse_settings(main_id, include_secrets=True)
    filename = str(doc.get("original_filename") or "")
    if is_plain_source_filename(filename):
        if temp_path:
            text = Path(temp_path).read_text(encoding="utf-8", errors="ignore")
        else:
            text = await read_plain_text_from_storage(doc)
        await ingest_plain_text_mineru(doc, text=text)
        return
    if not file_parse.get("configured"):
        raise RuntimeError("MinerU 未配置，请在知识设置中填写服务 URL 与 API Key")
    job_id = _request_mineru_parse(doc, file_parse)
    await get_db()[COLLECTION].update_one(
        {"_id": document_id, "main_id": main_id},
        {
            "$set": {
                "status": "pending_parse",
                "parse_status": "queued",
                "parse_job_id": job_id,
                "parse_error": "",
                "parse_updated_at": _now(),
                "updated_at": _now(),
            }
        },
    )


async def complete_mineru_callback(document_id: str, main_id: str, *, markdown_key: str) -> None:
    """After MinerU markdown is stored, generate summary and mark document learned."""
    await get_db()[COLLECTION].update_one(
        {"_id": document_id, "main_id": main_id, "deleted_at": None},
        {"$set": {"parsed_markdown_key": markdown_key, "parse_status": "running", "updated_at": _now()}},
    )
    try:
        await generate_and_store_summary(document_id, main_id)
    except Exception as exc:
        message = str(exc)[:2000]
        await get_db()[COLLECTION].update_one(
            {"_id": document_id, "main_id": main_id},
            {
                "$set": {
                    "parse_status": "failed",
                    "status": "failed",
                    "parse_error": message,
                    "parse_updated_at": _now(),
                    "updated_at": _now(),
                }
            },
        )
        raise
    await get_db()[COLLECTION].update_one(
        {"_id": document_id, "main_id": main_id},
        {
            "$set": {
                "parse_status": "succeeded",
                "status": "parsed",
                "parse_error": "",
                "chunk_status": "not_required",
                "index_status": "not_required",
                "parse_updated_at": _now(),
                "updated_at": _now(),
            }
        },
    )
