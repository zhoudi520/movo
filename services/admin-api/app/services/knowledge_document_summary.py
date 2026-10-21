"""Generate per-document content summaries for MinerU knowledge documents."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from typing import Any

from app.core.config import settings
from app.core.db import get_db
from app.repositories.model_repository import decrypt_secret, find_instance_by_id
from app.services.image_model_configuration import normalize_capabilities
from app.services.knowledge_storage import read_text_artifact
from app.services.model_test_tls import build_model_test_ssl_context

logger = logging.getLogger(__name__)

COLLECTION = "knowledge_documents"
SUMMARY_MAX_CHARS = int(getattr(settings, "knowledge_summary_max_chars", 200) or 200)
SUMMARY_MAX_OUTPUT_TOKENS = 320


class SummaryLlmHttpError(RuntimeError):
    """Chat completion HTTP error with response body."""

    def __init__(self, status_code: int, detail: str) -> None:
        self.status_code = status_code
        self.detail = detail
        super().__init__(f"摘要 LLM 调用失败 HTTP {status_code}: {detail}")


async def _list_chat_targets(main_id: str) -> list[tuple[dict[str, Any], dict[str, Any]]]:
    """
    List chat-capable model instances in fallback order (preferred first, then others).

    Args:
        main_id: Tenant id.

    Returns:
        List of (instance, provider) pairs.
    """
    db = get_db()
    instance_id = (
        str(settings.knowledge_summary_model_instance_id or "").strip()
        or os.getenv("ASKAI_ADMIN_KNOWLEDGE_SUMMARY_MODEL_INSTANCE_ID", "").strip()
    )
    tenants = [main_id]
    if main_id != "default":
        tenants.append("default")
    seen: set[str] = set()
    ordered_instances: list[dict[str, Any]] = []

    def _append(instance: dict[str, Any] | None) -> None:
        if not instance or str(instance.get("status") or "") != "active":
            return
        caps = normalize_capabilities(instance.get("capabilities"))
        if "chat" not in caps and "text" not in caps:
            return
        key = str(instance.get("_id") or "")
        if not key or key in seen:
            return
        seen.add(key)
        ordered_instances.append(instance)

    if instance_id:
        for tenant in tenants:
            _append(await find_instance_by_id(instance_id, tenant))

    for tenant in tenants:
        cursor = db.admin_model_instances.find({"main_id": tenant, "status": "active"}).sort(
            [("priority", 1), ("updated_at", -1)]
        )
        for instance in await cursor.to_list(length=100):
            _append(instance)

    if not ordered_instances:
        raise RuntimeError("未配置可用于摘要的 Chat 模型，请在模型中心启用带 Chat 能力的模型")

    targets: list[tuple[dict[str, Any], dict[str, Any]]] = []
    for instance in ordered_instances:
        provider = await db.admin_model_providers.find_one(
            {"_id": instance.get("provider_id"), "main_id": instance.get("main_id")}
        )
        targets.append((instance, provider or {}))
    return targets


def _instance_label(instance: dict[str, Any], provider: dict[str, Any]) -> str:
    """Build a short label for logs."""
    name = str(instance.get("display_name") or instance.get("model_name") or instance.get("_id") or "")
    vendor = str(provider.get("name") or provider.get("code") or provider.get("provider_type") or "")
    return f"{vendor}/{name}".strip("/")


def _decrypt_instance_api_key(instance: dict[str, Any]) -> str:
    """Decrypt model instance API key."""
    try:
        return decrypt_secret(str(instance.get("api_key_encrypted") or ""))
    except Exception as exc:
        raise RuntimeError("摘要模型 API Key 解密失败，请重新保存模型配置") from exc


def _parse_chat_response(raw: str) -> str:
    """Parse OpenAI-style chat completion JSON response."""
    parsed = json.loads(raw) if raw else {}
    choices = parsed.get("choices") or []
    if not choices:
        raise RuntimeError("摘要 LLM 返回为空")
    message = choices[0].get("message") or {}
    return str(message.get("content") or "").strip()


def _post_chat_request(*, url: str, headers: dict[str, str], payload: dict[str, Any]) -> str:
    """POST chat completion request and return assistant text."""
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(url, data=data, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=120, context=build_model_test_ssl_context()) as response:
            raw = response.read().decode("utf-8")
            return _parse_chat_response(raw)
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:800]
        raise SummaryLlmHttpError(exc.code, detail) from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"摘要 LLM 调用失败: {exc}") from exc


def _should_retry_token_param(detail: str) -> bool:
    """Return True when HTTP 400 is about max_tokens vs max_completion_tokens."""
    lowered = detail.lower()
    mentions_limit = "max_tokens" in lowered or "max_completion_tokens" in lowered
    if not mentions_limit:
        return False
    return (
        "unsupported parameter" in lowered
        or "unsupported_parameter" in lowered
        or "use 'max_completion_tokens'" in lowered
        or "use max_completion_tokens" in lowered
    )


def _post_chat_with_output_limits(*, url: str, headers: dict[str, str], base_payload: dict[str, Any]) -> str:
    """
    POST chat completion, adapting output limit field for different vendors/models.

    Tries max_tokens, then max_completion_tokens, then no explicit output limit.
    """
    limit_variants: list[dict[str, Any]] = [
        {"max_tokens": SUMMARY_MAX_OUTPUT_TOKENS},
        {"max_completion_tokens": SUMMARY_MAX_OUTPUT_TOKENS},
        {},
    ]
    last_error: Exception | None = None
    for limit_fields in limit_variants:
        payload = {**base_payload, **limit_fields}
        try:
            return _post_chat_request(url=url, headers=headers, payload=payload)
        except SummaryLlmHttpError as exc:
            last_error = exc
            if exc.status_code == 400 and _should_retry_token_param(exc.detail):
                continue
            raise RuntimeError(str(exc)) from exc
    if last_error:
        raise RuntimeError(str(last_error)) from last_error
    raise RuntimeError("摘要 LLM 调用失败")


def _chat_complete_sync(
    *,
    instance: dict[str, Any],
    provider: dict[str, Any],
    system: str,
    user: str,
) -> str:
    """
    Call chat completions using the same routing rules as model connectivity tests.

    Args:
        instance: Model instance document.
        provider: Provider document.
        system: System prompt.
        user: User prompt.

    Returns:
        Assistant message text.
    """
    api_key = _decrypt_instance_api_key(instance)
    if not api_key:
        raise RuntimeError("摘要模型 API Key 不能为空")
    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]
    base_payload: dict[str, Any] = {
        "messages": messages,
        "temperature": 0.2,
    }
    provider_type = str(provider.get("provider_type") or "openai_compatible").strip()
    if provider_type == "azure_openai":
        deployment = str(instance.get("model_name") or "").strip()
        endpoint = str(instance.get("base_url") or provider.get("default_base_url") or "").strip().rstrip("/")
        api_version = str(instance.get("api_version") or "").strip() or "2024-10-21"
        if not deployment:
            raise RuntimeError("Azure 摘要模型 Deployment 名称不能为空")
        if not endpoint:
            raise RuntimeError("Azure 摘要模型 Endpoint 不能为空")
        path_deployment = urllib.parse.quote(deployment, safe="")
        query = urllib.parse.urlencode({"api-version": api_version})
        url = f"{endpoint}/openai/deployments/{path_deployment}/chat/completions?{query}"
        headers = {
            "api-key": api_key,
            "Content-Type": "application/json",
        }
        return _post_chat_with_output_limits(url=url, headers=headers, base_payload=base_payload)

    model_name = str(instance.get("model_name") or "").strip()
    base_url = str(instance.get("base_url") or provider.get("default_base_url") or "").strip().rstrip("/")
    if not model_name:
        raise RuntimeError("摘要模型 ID 不能为空")
    if not base_url:
        raise RuntimeError("摘要模型 Base URL 不能为空")
    openai_payload = {**base_payload, "model": model_name}
    url = f"{base_url}/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    return _post_chat_with_output_limits(url=url, headers=headers, base_payload=openai_payload)


def summarize_core_content(
    filename: str,
    text: str,
    *,
    instance: dict[str, Any],
    provider: dict[str, Any],
) -> str:
    """
    Summarize document body into a short Chinese summary.

    Args:
        filename: Original filename for context.
        text: Full markdown or plain text (not truncated).
        instance: Chat model instance document.
        provider: Model provider document.

    Returns:
        Summary text capped at SUMMARY_MAX_CHARS.
    """
    body = (text or "").strip()
    if not body:
        return ""
    system_prompt = (
        "你是文档摘要助手。请用简洁中文概括文档的核心内容。"
        f"摘要不超过 {SUMMARY_MAX_CHARS} 个字，不要标题、列表或前后缀说明，只输出摘要正文。"
    )
    user_prompt = f"文件名：{filename}\n\n文档内容：\n{body}"
    raw = _chat_complete_sync(instance=instance, provider=provider, system=system_prompt, user=user_prompt)
    summary = " ".join(raw.split())
    if len(summary) > SUMMARY_MAX_CHARS:
        summary = summary[:SUMMARY_MAX_CHARS].rstrip()
    return summary


async def generate_and_store_summary(document_id: str, main_id: str) -> str:
    """
    Read parsed markdown and persist content_summary on the document.

    Args:
        document_id: Knowledge document id.
        main_id: Tenant id.

    Returns:
        Generated summary text.

    Raises:
        RuntimeError: When markdown or summary generation fails.
    """
    db = get_db()
    doc = await db[COLLECTION].find_one({"_id": document_id, "main_id": main_id, "deleted_at": None})
    if not doc:
        raise RuntimeError("文档不存在")
    markdown_key = str(doc.get("parsed_markdown_key") or "").strip()
    if not markdown_key:
        raise RuntimeError("解析 Markdown 不存在，无法生成摘要")
    try:
        text = read_text_artifact(doc, markdown_key)
    except Exception as exc:
        raise RuntimeError(f"读取解析 Markdown 失败: {exc}") from exc
    if not str(text or "").strip():
        raise RuntimeError("解析 Markdown 为空，无法生成摘要")
    filename = str(doc.get("original_filename") or doc.get("name") or "document")
    targets = await _list_chat_targets(main_id)
    errors: list[str] = []
    summary = ""
    for instance, provider in targets:
        label = _instance_label(instance, provider)
        try:
            candidate = await asyncio.to_thread(
                summarize_core_content,
                filename,
                text,
                instance=instance,
                provider=provider,
            )
        except Exception as exc:
            message = str(exc) or repr(exc)
            errors.append(f"{label}: {message}")
            logger.warning(f"摘要模型调用失败，尝试下一个: target={label}, error={message}")
            continue
        if candidate:
            summary = candidate
            logger.info(f"摘要生成成功: target={label}")
            break
        errors.append(f"{label}: 文档摘要为空")
    if not summary:
        joined = " | ".join(errors[:5])
        raise RuntimeError(f"所有摘要模型均失败: {joined}")
    await db[COLLECTION].update_one(
        {"_id": document_id, "main_id": main_id},
        {"$set": {"content_summary": summary, "updated_at": datetime.now(timezone.utc)}},
    )
    logger.info(f"文档摘要已写入: document_id={document_id}, chars={len(summary)}")
    return summary


__all__ = ["SUMMARY_MAX_CHARS", "generate_and_store_summary", "summarize_core_content"]
