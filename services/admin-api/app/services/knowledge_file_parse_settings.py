"""Effective MinerU / file-parse settings (env defaults + knowledge settings override)."""

from __future__ import annotations

import os
from copy import deepcopy
from datetime import datetime, timezone
from typing import Any

from app.core.config import settings
from app.core.db import get_db
from app.repositories.model_repository import decrypt_secret, mask_secret

KNOWLEDGE_SETTINGS_COLLECTION = "knowledge_document_settings"


def _env_str(key: str, default: str = "") -> str:
    return (os.getenv(key, "") or getattr(settings, key.lower(), None) or default).strip()


def default_file_parse_settings() -> dict[str, Any]:
    """Return default file parse config from environment."""
    from app.core.config import settings as app_settings

    return {
        "provider": "mineru",
        "enabled": True,
        "serviceUrl": (
            str(app_settings.mineru_service_url or "").strip()
            or _env_str("ASKAI_ADMIN_MINERU_SERVICE_URL", _env_str("MINERU_SERVICE_URL", ""))
        ),
        "apiKey": "",
        "modelVersion": (
            str(app_settings.mineru_model_version or "").strip()
            or _env_str("ASKAI_ADMIN_MINERU_MODEL_VERSION", _env_str("MINERU_MODEL_VERSION", "vlm"))
            or "vlm"
        ),
        "language": (
            str(app_settings.mineru_language or "").strip()
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
    elif stored.get("apiKeyMasked"):
        merged["apiKeyMasked"] = str(stored.get("apiKeyMasked") or "")
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
    if include_secrets and not str(merged.get("apiKey") or "").strip():
        merged["apiKey"] = str(settings.mineru_api_key or os.getenv("MINERU_API_KEY", "") or "").strip()
    has_url = bool(str(merged.get("serviceUrl") or "").strip())
    has_secret = bool(stored.get("apiKeyEncrypted")) or bool(
        str(settings.mineru_api_key or os.getenv("MINERU_API_KEY", "") or "").strip()
    )
    merged["configured"] = bool(merged.get("enabled") and has_url and has_secret)
    return merged


def serialize_file_parse_for_api(stored: dict[str, Any] | None) -> dict[str, Any]:
    """Serialize file parse settings for admin API responses (secrets masked)."""
    merged = _merge_file_parse(default_file_parse_settings(), dict(stored or {}))
    merged["apiKey"] = ""
    if stored and stored.get("apiKeyMasked"):
        merged["apiKeyMasked"] = str(stored.get("apiKeyMasked") or "")
    else:
        merged["apiKeyMasked"] = mask_secret(str(stored.get("apiKeyEncrypted") or "")) if stored else ""
    return merged


def is_mineru_ready(config: dict[str, Any]) -> bool:
    """Return whether MinerU upload/processing can run."""
    return bool(config.get("configured"))


__all__ = [
    "default_file_parse_settings",
    "get_effective_file_parse_settings",
    "is_mineru_ready",
    "serialize_file_parse_for_api",
]
