from __future__ import annotations

from typing import Any


def usage_model_id(configured_id: str, provider_meta: dict[str, Any]) -> str:
    """Keep the configured instance identity; provider metadata names the deployment."""
    return str(configured_id or provider_meta.get("model_id") or "")
