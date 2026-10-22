"""Effective MinerU / file-parse settings for runtime document parsing."""

from __future__ import annotations

import os
from copy import deepcopy
from datetime import datetime, timezone
from typing import Any

from app.core.config import get_settings
from app.core.db import get_db
from app.llm.configured_models import decrypt_secret

KNOWLEDGE_SETTINGS_COLLECTION = "knowledge_document_settings"


def _env_str(key: str, default: str = "") -> str:
    return (os.getenv(key, "") or default).strip()


def default_file_parse_settings() -> dict[str, Any]:
    """Return default file parse config from environment."""
    settings = get_settings()
    return {
        "provider": "mineru",
        "enabled": True,
        "serviceUrl": (
            str(getattr(settings, "MINERU_SERVICE_URL", "") or "").strip()
            or _env_str("ASKAI_ADMIN_MINERU_SERVICE_URL", _env_str("MINERU_SERVICE_URL", ""))
        ),
        "apiKey": "",
        "modelVersion": (
            str(getattr(settings, "MINERU_MODEL_VERSION", "") or "").strip()
            or _env_str("ASKAI_ADMIN_MINERU_MODEL_VERSION", _env_str("MINERU_MODEL_VERSION", "vlm"))
            or "vlm"
        ),
        "language": (
            str(getattr(settings, "MINERU_LANGUAGE", "") or "").strip()
            or _env_str("ASKAI_ADMIN_MINERU_LANGUAGE", _env_str("MINERU_LANGUAGE", "ch"))
            or "ch"
        ),
        "expiresAt": "",
    }


def _merge_file_parse(defaults: dict[str, Any], overrides: dict[str, Any]) -> dict[str, Any]:
    result = deepcopy(defaults)
    for key, value in overrides.items():
        if value is None:
            continue
        if isinstance(value, str) and not value.strip() and key != "enabled":
            continue
        result[key] = value
    return result


async def get_effective_file_parse_settings(main_id: str, *, include_secrets: bool = False) -> dict[str, Any]:
    """
    Load file parse settings for a tenant, merging DB overrides onto env defaults.

    Args:
        main_id: Tenant id.
        include_secrets: When True, include decrypted apiKey for internal jobs.

    Returns:
        Effective file parse configuration dict.
    """
    doc = await get_db()[KNOWLEDGE_SETTINGS_COLLECTION].find_one({"main_id": main_id, "kind": "knowledge"})
    config = dict((doc or {}).get("config") or {})
    stored = dict(config.get("fileParse") or {})
    merged = _merge_file_parse(default_file_parse_settings(), stored)
    if stored.get("apiKeyEncrypted") and include_secrets:
        try:
            merged["apiKey"] = decrypt_secret(str(stored.get("apiKeyEncrypted") or ""))
        except Exception:
            merged["apiKey"] = ""
    expires_at = str(merged.get("expiresAt") or "").strip()
    if expires_at:
        try:
            expire_dt = datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
            if expire_dt.tzinfo is None:
                expire_dt = expire_dt.replace(tzinfo=timezone.utc)
            if expire_dt < datetime.now(timezone.utc):
                merged["enabled"] = False
        except ValueError:
            pass
    settings = get_settings()
    if include_secrets and not str(merged.get("apiKey") or "").strip():
        merged["apiKey"] = str(getattr(settings, "MINERU_API_KEY", "") or os.getenv("MINERU_API_KEY", "") or "").strip()
    has_url = bool(str(merged.get("serviceUrl") or "").strip())
    has_secret = bool(stored.get("apiKeyEncrypted")) or bool(
        str(getattr(settings, "MINERU_API_KEY", "") or os.getenv("MINERU_API_KEY", "") or "").strip()
    )
    merged["configured"] = bool(merged.get("enabled") and has_url and has_secret)
    return merged


def is_mineru_ready(config: dict[str, Any]) -> bool:
    """Return whether MinerU runtime parsing can run."""
    return bool(config.get("configured"))


def mineru_runtime_payload(config: dict[str, Any]) -> dict[str, str] | None:
    """Build MinerU credentials for document-processing sync parse."""
    if not is_mineru_ready(config):
        return None
    service_url = str(config.get("serviceUrl") or "").strip()
    api_key = str(config.get("apiKey") or "").strip()
    if not service_url or not api_key:
        return None
    return {
        "serviceUrl": service_url,
        "apiKey": api_key,
        "modelVersion": str(config.get("modelVersion") or "vlm").strip() or "vlm",
        "language": str(config.get("language") or "ch").strip() or "ch",
    }


__all__ = [
    "get_effective_file_parse_settings",
    "is_mineru_ready",
    "mineru_runtime_payload",
]
