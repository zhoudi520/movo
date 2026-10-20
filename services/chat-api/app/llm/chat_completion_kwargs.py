from __future__ import annotations

from typing import Any


def prepare_chat_completion_kwargs(kwargs: dict[str, Any]) -> dict[str, Any]:
    """Normalize kwargs for OpenAI ``chat.completions`` requests.

    Reasoning-capable models (for example ``gpt-5.6-luna``) reject function tools on
    ``/v1/chat/completions`` unless ``reasoning_effort`` is explicitly ``none``.
    """
    prepared = dict(kwargs)
    prepared.pop("stream", None)
    if prepared.get("tools"):
        prepared["reasoning_effort"] = "none"
    return prepared
