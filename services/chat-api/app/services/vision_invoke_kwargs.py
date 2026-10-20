from __future__ import annotations

from typing import Any


def _normalized_base_url(configured_model: dict[str, Any] | None, *, fallback_base_url: str) -> str:
    if isinstance(configured_model, dict):
        return str(configured_model.get("base_url") or "").strip().lower()
    return str(fallback_base_url or "").strip().lower()


def supports_dashscope_enable_thinking(
    configured_model: dict[str, Any] | None,
    *,
    fallback_base_url: str = "",
) -> bool:
    """Return whether ``enable_thinking`` is a valid DashScope-only request extension."""
    if isinstance(configured_model, dict):
        provider_type = str(configured_model.get("provider_type") or "").strip().lower()
        if provider_type == "azure_openai":
            return False
    base_url = _normalized_base_url(configured_model, fallback_base_url=fallback_base_url)
    return "dashscope" in base_url or "aliyuncs.com" in base_url


def build_vision_invoke_kwargs(
    *,
    configured_model: dict[str, Any] | None,
    fallback_base_url: str,
    enable_thinking: bool,
    thinking_budget: int,
) -> dict[str, Any]:
    """Build provider-safe kwargs for vision ``ainvoke`` calls."""
    kwargs: dict[str, Any] = {}
    if not enable_thinking:
        return kwargs
    if not supports_dashscope_enable_thinking(configured_model, fallback_base_url=fallback_base_url):
        return kwargs
    kwargs["extra_body"] = {
        "enable_thinking": True,
        "thinking_budget": int(thinking_budget or 81920),
    }
    return kwargs
