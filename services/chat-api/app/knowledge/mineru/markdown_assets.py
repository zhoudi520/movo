"""MinerU markdown image URL rewriting and artifact path resolution."""

from __future__ import annotations

import mimetypes
import posixpath
import re
from pathlib import Path
from typing import Any
from urllib.parse import quote

from fastapi import HTTPException, status

from app.core.config import get_settings

_MD_IMAGE_RE = re.compile(r"(!\[[^\]]*\]\()([^)]+)(\))")
_HTML_IMAGE_RE = re.compile(r'(<img\b[^>]*\bsrc=["\'])([^"\']+)(["\'])', re.IGNORECASE)
_RELATIVE_ASSET_RE = re.compile(r"^(?:\./)?assets/[^\"')\s]+", re.IGNORECASE)
_IMAGE_SUFFIXES = (".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".jp2", ".svg")


def _is_relative_image_ref(src: str) -> bool:
    """Return True when src looks like a relative image path inside MinerU markdown."""
    value = str(src or "").strip().replace("\\", "/")
    if not value or value.startswith(("http://", "https://", "data:", "/askai-api/", "/")):
        return False
    return Path(value.split("?", 1)[0]).suffix.lower() in _IMAGE_SUFFIXES


def _artifact_rel_candidates(relative_path: str) -> list[str]:
    """Build candidate artifact-relative paths for a markdown image reference."""
    raw = str(relative_path or "").strip().replace("\\", "/").lstrip("/")
    if not raw or ".." in raw.split("/"):
        return []
    candidates: list[str] = []
    if raw.lower().startswith("assets/"):
        candidates.append(raw)
    if _is_relative_image_ref(raw):
        basename = Path(raw.split("?", 1)[0]).name
        if basename:
            candidates.append(f"assets/{basename}")
    seen: set[str] = set()
    output: list[str] = []
    for item in candidates:
        key = item.lower()
        if key in seen:
            continue
        seen.add(key)
        output.append(item)
    return output


def document_artifact_prefix(doc: dict[str, Any]) -> str:
    """
    Resolve artifact directory prefix for a knowledge document.

    Prefer ``parsed_markdown_key`` parent; fall back to default layout.
    """
    md_key = str(doc.get("parsed_markdown_key") or "").strip().replace("\\", "/")
    if md_key:
        return posixpath.dirname(md_key)
    main_id = str(doc.get("main_id") or "default")
    document_id = str(doc.get("_id") or "")
    return f"knowledge-documents/{main_id}/{document_id}/artifacts"


def resolve_artifact_storage_key(doc: dict[str, Any], relative_path: str) -> str:
    """
    Map a markdown-relative artifact path to an absolute storage key.

    Args:
        doc: Knowledge document record.
        relative_path: Path such as ``assets/chart.png``.

    Returns:
        Storage key under knowledge storage root.

    Raises:
        HTTPException: When the path is invalid or escapes the artifact prefix.
    """
    candidates = _artifact_rel_candidates(relative_path)
    if not candidates:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="invalid artifact path")
    prefix = document_artifact_prefix(doc)
    for raw in candidates:
        storage_key = posixpath.normpath(f"{prefix}/{raw}")
        if not storage_key.startswith(prefix + "/") and storage_key != prefix:
            continue
        return storage_key
    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="invalid artifact path")


def local_artifact_path(doc: dict[str, Any], relative_path: str) -> Path:
    """Resolve a local filesystem path for an artifact (local storage only)."""
    settings = get_settings()
    root = Path(settings.KNOWLEDGE_LOCAL_STORAGE_DIR).expanduser().resolve()
    prefix = document_artifact_prefix(doc)
    last_error: HTTPException | None = None
    for raw in _artifact_rel_candidates(relative_path):
        storage_key = posixpath.normpath(f"{prefix}/{raw}")
        if not storage_key.startswith(prefix + "/") and storage_key != prefix:
            continue
        path = (root / storage_key).resolve()
        if root not in path.parents and path != root:
            last_error = HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="invalid artifact path")
            continue
        if path.is_file():
            return path
        last_error = HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="artifact not found")
    if last_error is not None:
        raise last_error
    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="invalid artifact path")


def artifact_public_url(document_id: str, relative_path: str) -> str:
    """Build browser-facing URL for a knowledge document artifact."""
    rel = str(relative_path or "").strip().replace("\\", "/").lstrip("/")
    encoded = quote(rel, safe="/")
    return f"/askai-api/api/knowledge/sources/documents/{document_id}/artifacts/{encoded}"


def guess_artifact_media_type(relative_path: str) -> str:
    """Guess MIME type for an artifact file."""
    mime, _ = mimetypes.guess_type(relative_path)
    return mime or "application/octet-stream"


def rewrite_mineru_markdown_image_urls(markdown: str, *, document_id: str) -> str:
    """
    Rewrite relative MinerU ``assets/...`` image refs to authenticated API URLs.

    Args:
        markdown: Parsed markdown text.
        document_id: Knowledge document id.

    Returns:
        Markdown with image src/hrefs pointing at the knowledge artifact API.
    """

    def _replace_src(src: str) -> str:
        raw = str(src or "").strip()
        if not raw or raw.startswith(("http://", "https://", "data:", "/askai-api/")):
            return raw
        normalized = raw.replace("\\", "/").lstrip("./")
        if _RELATIVE_ASSET_RE.match(normalized):
            return artifact_public_url(document_id, normalized)
        if _is_relative_image_ref(normalized):
            asset_rel = f"assets/{Path(normalized.split('?', 1)[0]).name}"
            return artifact_public_url(document_id, asset_rel)
        return raw

    text = _MD_IMAGE_RE.sub(lambda m: f"{m.group(1)}{_replace_src(m.group(2))}{m.group(3)}", markdown)
    return _HTML_IMAGE_RE.sub(
        lambda m: f"{m.group(1)}{_replace_src(m.group(2))}{m.group(3)}",
        text,
    )
