from __future__ import annotations

import mimetypes
from typing import Any

from fastapi import APIRouter, Header, HTTPException, Query, Request, status
from starlette.responses import FileResponse

from app.api.endpoints.auth import _resolve_session_user
from app.core.db import get_db
from app.knowledge.mineru.markdown_assets import (
    guess_artifact_media_type,
    local_artifact_path,
    rewrite_mineru_markdown_image_urls,
)
from app.knowledge.mineru.storage_text import read_storage_text
from app.services.knowledge_preview_stream import preview_response
from app.services.personal_knowledge.access import PersonalKnowledgeAccessService
from app.product.extensions import get_product_extension

router = APIRouter()

DOCUMENT_COLLECTION = "knowledge_documents"
CHUNK_COLLECTION = "knowledge_document_chunks"
OFFICE_EXTENSIONS = {"doc", "docx", "xls", "xlsx", "ppt", "pptx"}


def _needs_preview_conversion(file_ext: str) -> bool:
    return file_ext.strip().lower() in OFFICE_EXTENSIONS


def _serialize_chunk(chunk: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": str(chunk.get("_id") or ""),
        "documentId": str(chunk.get("document_id") or ""),
        "chunkId": str(chunk.get("chunk_id") or ""),
        "chunkStage": str(chunk.get("chunk_stage") or "rag"),
        "ordinal": int(chunk.get("ordinal") or 0),
        "text": str(chunk.get("text") or ""),
        "contextualText": str(chunk.get("contextual_text") or ""),
        "titlePath": list(chunk.get("title_path") or []),
        "pageNo": chunk.get("page_no"),
        "contentType": str(chunk.get("content_type") or "text"),
        "sourceChunkIds": list(chunk.get("source_chunk_ids") or []),
        "metadata": chunk.get("metadata") or {},
    }


async def _authorization_header(authorization: str | None, access_token: str | None = None) -> str | None:
    """Prefer Authorization header; fall back to ``access_token`` query for img tags."""
    if authorization:
        return authorization
    token = str(access_token or "").strip()
    if not token:
        return None
    return token if token.lower().startswith("bearer ") else f"Bearer {token}"


async def _current_scope(authorization: str | None, access_token: str | None = None) -> tuple[str, str]:
    resolved = await _resolve_session_user(await _authorization_header(authorization, access_token))
    user_id = str(resolved["user"].get("_id") or "")
    main_id = str(resolved.get("main_id") or resolved["user"].get("main_id") or "default")
    return user_id, main_id


async def _find_document_or_404(document_id: str, main_id: str, user_id: str = "") -> dict[str, Any]:
    doc = await get_db()[DOCUMENT_COLLECTION].find_one(
        {"_id": document_id, "main_id": main_id, "deleted_at": None}
    )
    if not doc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="document not found")
    if str(doc.get("scope") or "organization") == "personal":
        resource_id = str(doc.get("resource_id") or "")
        try:
            await PersonalKnowledgeAccessService().require_view(
                main_id=main_id, user_id=user_id, resource_id=resource_id,
            )
        except (LookupError, PermissionError) as exc:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="knowledge_forbidden") from exc
    else:
        access_policy = get_product_extension().knowledge_access_policy
        if access_policy is not None:
            try:
                await access_policy.require_view(
                    main_id=main_id,
                    user_id=user_id,
                    document_id=document_id,
                )
            except PermissionError as exc:
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="knowledge_forbidden") from exc
    return doc


@router.get("/knowledge/sources/documents/{document_id}")
async def get_knowledge_source_document(
    document_id: str,
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    user_id, main_id = await _current_scope(authorization)
    doc = await _find_document_or_404(document_id, main_id, user_id)
    can_download = True
    if str(doc.get("scope") or "organization") != "personal":
        access_policy = get_product_extension().knowledge_access_policy
        check_download = getattr(access_policy, "can_download", None)
        if callable(check_download):
            can_download = bool(await check_download(
                main_id=main_id, user_id=user_id, document_id=document_id,
            ))
    return {
        "id": str(doc.get("_id") or ""),
        "scope": str(doc.get("scope") or "organization"),
        "name": str(doc.get("name") or ""),
        "originalFilename": str(doc.get("original_filename") or ""),
        "fileExt": str(doc.get("file_ext") or ""),
        "mimeType": str(doc.get("mime_type") or ""),
        "previewMimeType": str(doc.get("preview_mime_type") or ""),
        "previewStatus": str(doc.get("preview_status") or ""),
        "chunkCount": int(doc.get("chunk_count") or 0),
        "canDownload": can_download,
        "learningMode": str(doc.get("learning_mode") or "rag"),
    }


def _serialize_mineru_pseudo_chunk(doc: dict[str, Any], chunk_id: str) -> dict[str, Any]:
    """Build a source chunk payload for MinerU pseudo chunk ids (``mineru_*``)."""
    document_id = str(doc.get("_id") or "")
    markdown_key = str(doc.get("parsed_markdown_key") or "").strip()
    if not markdown_key:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="chunk not found")
    try:
        raw_text = read_storage_text(doc, markdown_key)
    except (FileNotFoundError, ValueError) as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="chunk not found") from exc
    text = rewrite_mineru_markdown_image_urls(raw_text, document_id=document_id)
    title = str(doc.get("name") or doc.get("original_filename") or document_id)
    return {
        "id": f"{document_id}:{chunk_id}",
        "documentId": document_id,
        "chunkId": chunk_id,
        "chunkStage": "mineru",
        "ordinal": 0,
        "text": text,
        "contextualText": text,
        "titlePath": [title],
        "pageNo": None,
        "contentType": "markdown",
        "sourceChunkIds": [],
        "metadata": {"learningMode": "mineru", "document_title": title},
    }


@router.get("/knowledge/sources/documents/{document_id}/chunks/{chunk_id}")
async def get_knowledge_source_chunk(
    document_id: str,
    chunk_id: str,
    authorization: str | None = Header(default=None),
    access_token: str | None = Query(default=None),
) -> dict[str, Any]:
    user_id, main_id = await _current_scope(authorization, access_token)
    doc = await _find_document_or_404(document_id, main_id, user_id)
    if str(chunk_id).startswith("mineru"):
        return _serialize_mineru_pseudo_chunk(doc, chunk_id)
    chunk = await get_db()[CHUNK_COLLECTION].find_one(
        {
            "main_id": main_id,
            "document_id": document_id,
            "chunk_id": chunk_id,
            "$or": [{"chunk_stage": "rag"}, {"chunk_stage": {"$exists": False}}],
        }
    )
    if not chunk:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="chunk not found")
    return _serialize_chunk(chunk)


@router.get("/knowledge/sources/documents/{document_id}/artifacts/{artifact_path:path}")
async def get_knowledge_source_artifact(
    document_id: str,
    artifact_path: str,
    authorization: str | None = Header(default=None),
    access_token: str | None = Query(default=None),
):
    """Serve MinerU markdown image artifacts with session auth (header or query token)."""
    user_id, main_id = await _current_scope(authorization, access_token)
    doc = await _find_document_or_404(document_id, main_id, user_id)
    if str(doc.get("learning_mode") or "").lower() != "mineru":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="artifact not found")
    rel = str(artifact_path or "").strip().replace("\\", "/").lstrip("/")
    path = local_artifact_path(doc, rel)
    return FileResponse(path, media_type=guess_artifact_media_type(rel), content_disposition_type="inline")


@router.get("/knowledge/sources/documents/{document_id}/preview")
async def get_knowledge_source_preview(
    document_id: str,
    request: Request,
    authorization: str | None = Header(default=None),
):
    user_id, main_id = await _current_scope(authorization)
    doc = await _find_document_or_404(document_id, main_id, user_id)
    preview_status = str(doc.get("preview_status") or "")
    if _needs_preview_conversion(str(doc.get("file_ext") or "")):
        if preview_status != "succeeded":
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="preview not ready")
        storage_field = "preview_key"
    else:
        storage_field = "preview_key" if str(doc.get("preview_key") or "") else "storage_key"
    storage_key = str(doc.get(storage_field) or "")
    mime = (
        str(doc.get("preview_mime_type") or "")
        if storage_field == "preview_key"
        else str(doc.get("mime_type") or "")
    ) or mimetypes.guess_type(storage_key)[0] or "application/octet-stream"
    return preview_response(
        document=doc,
        storage_field=storage_field,
        media_type=mime,
        range_header=request.headers.get("range", ""),
    )
