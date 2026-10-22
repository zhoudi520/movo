from __future__ import annotations

import logging
import time
from typing import Any, Dict

import httpx

from app.core.config import get_settings
from app.utils.oss_uploader import ObjectStorageClient


logger = logging.getLogger(__name__)


class DocumentProcessingParseClient:
    """Small client for the document-processing synchronous parse endpoint."""

    def __init__(self) -> None:
        self._settings = get_settings()

    def _source_from_document(self, document: Dict[str, Any]) -> Dict[str, Any]:
        storage_key = str(document.get("object_path") or document.get("storage_key") or "").strip()
        if not storage_key:
            return {}
        return {
            "storageType": str(document.get("storage_type") or self._settings.STORAGE_BACKEND or "oss").strip() or "oss",
            "storageBucket": str(document.get("storage_bucket") or self._settings.OSS_BUCKET_NAME or "").strip(),
            "storageKey": storage_key,
            "filename": str(document.get("filename") or "document").strip() or "document",
            "mimeType": str(document.get("content_type") or document.get("mime_type") or "").strip(),
        }

    def _source_url_from_document(self, document: Dict[str, Any], source: Dict[str, Any]) -> str:
        storage_type = str(source.get("storageType") or "").strip().lower()
        storage_key = str(source.get("storageKey") or "").strip()
        if storage_type == "local" and storage_key:
            try:
                return str(ObjectStorageClient().internal_url(storage_key) or "").strip()
            except Exception:
                return ""
        return ""

    async def parse_markdown(
        self,
        document: Dict[str, Any],
        *,
        timeout_seconds: float | None = None,
        mineru_config: Dict[str, Any] | None = None,
    ) -> Dict[str, Any]:
        base_url = str(getattr(self._settings, "DOCUMENT_PROCESSING_BASE_URL", "") or "").strip().rstrip("/")
        token = str(getattr(self._settings, "DOCUMENT_PROCESSING_SERVICE_TOKEN", "") or "").strip()
        source = self._source_from_document(document)
        filename = str(document.get("filename") or source.get("filename") or "document").strip()
        if not base_url or not token or not source:
            return {}
        payload = {"source": source}
        source_url = self._source_url_from_document(document, source)
        if source_url:
            payload["sourceUrl"] = source_url
        if mineru_config:
            service_url = str(mineru_config.get("serviceUrl") or "").strip()
            api_key = str(mineru_config.get("apiKey") or "").strip()
            if service_url and api_key:
                payload["mineru"] = {"serviceUrl": service_url, "apiKey": api_key}
                payload["modelVersion"] = str(mineru_config.get("modelVersion") or "vlm").strip() or "vlm"
                payload["language"] = str(mineru_config.get("language") or "ch").strip() or "ch"
        configured_timeout = float(getattr(self._settings, "DOCUMENT_PROCESSING_SYNC_PARSE_TIMEOUT_SECONDS", 180.0) or 180.0)
        timeout = max(float(timeout_seconds or 0.0), configured_timeout)
        sync_backend = "mineru" if payload.get("mineru") else "docling"
        logger.info(
            f"document_processing_parse_markdown_start filename={filename[:120]} "
            f"sync_backend={sync_backend} timeout_s={timeout:.1f} base_url={base_url}"
        )
        started_at = time.monotonic()
        try:
            async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
                resp = await client.post(
                    f"{base_url}/api/documents/parse-markdown",
                    json=payload,
                    headers={
                        "Authorization": f"Bearer {token}",
                        "Accept": "application/json",
                    },
                )
            if resp.status_code >= 400:
                logger.info(
                    f"document_processing_parse_markdown_failed filename={filename[:120]} "
                    f"sync_backend={sync_backend} status={resp.status_code} "
                    f"duration_s={time.monotonic() - started_at:.1f} body={str(resp.text or '')[:300]}"
                )
                return {
                    "ok": False,
                    "error": f"document_processing_http_{resp.status_code}",
                    "parser": "document_processing",
                    "filename": filename,
                    "source_url": f"object://{source.get('storageKey')}",
                }
            data = resp.json() if str(resp.text or "").strip() else {}
        except Exception as exc:
            logger.info(
                f"document_processing_parse_markdown_unavailable filename={filename[:120]} "
                f"sync_backend={sync_backend} duration_s={time.monotonic() - started_at:.1f} "
                f"error={str(exc)[:300]}"
            )
            return {
                "ok": False,
                "error": f"document_processing_unavailable: {exc}",
                "parser": "document_processing",
                "filename": filename,
                "source_url": f"object://{source.get('storageKey')}",
            }

        markdown = str((data or {}).get("markdown") or "").strip()
        resolved_parser = str((data or {}).get("parser") or "document_processing").strip() or "document_processing"
        logger.info(
            f"document_processing_parse_markdown_finished filename={filename[:120]} "
            f"ok={bool(markdown)} parser={resolved_parser} sync_backend={sync_backend} "
            f"duration_s={time.monotonic() - started_at:.1f} markdown_chars={len(markdown)}"
        )
        return {
            "ok": bool(markdown),
            "error": "" if markdown else "document_processing_missing_markdown",
            "markdown": markdown,
            "structured_content": dict((data or {}).get("raw") or {}),
            "parse_quality": {
                "source": "document_processing",
                "markdown_chars": int((data or {}).get("markdownChars") or len(markdown)),
                "raw_chunk_count": len(list((data or {}).get("rawChunks") or [])),
                "rag_chunk_count": len(list((data or {}).get("ragChunks") or [])),
            },
            "raw_chunks": list((data or {}).get("rawChunks") or []),
            "rag_chunks": list((data or {}).get("ragChunks") or []),
            "source_url": f"object://{source.get('storageKey')}",
            "filename": filename,
            "parser": resolved_parser,
            "parse_route": f"document_processing_sync_{sync_backend}",
        }


document_processing_parse_client = DocumentProcessingParseClient()
