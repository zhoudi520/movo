from __future__ import annotations

import asyncio
import json
import urllib.error
import urllib.request
from decimal import Decimal, InvalidOperation
from typing import Any
from urllib.parse import urlparse

from app.repositories.model_group_repository import find_group
from app.repositories.model_repository import decrypt_secret, find_provider_by_id
from app.services.model_pricing import normalize_pricing
from app.services.model_test_tls import build_model_test_ssl_context

_MODELS_FETCH_TIMEOUT_SECONDS = 8

# 官方默认定价（每 100 万 Token）；仅在命中官方域名/供应商时使用，并可能被 /models 接口覆盖。
_PROVIDER_CATALOG: dict[str, list[dict[str, Any]]] = {
    "deepseek": [
        {
            "patterns": ("deepseek-flash", "deepseek-v4-flash", "deepseek-chat", "deepseek-v4-flash-vision-exp"),
            "pricing": {"currency": "CNY", "inputPerMillion": 1, "outputPerMillion": 2},
        },
        {
            "patterns": ("deepseek-v4-pro", "deepseek-reasoner"),
            "pricing": {"currency": "CNY", "inputPerMillion": 4, "outputPerMillion": 16},
        },
    ],
    # OpenAI Standard 计价（USD / 1M tokens，≤272K 短上下文输入档）
    # 来源：https://developers.openai.com/api/docs/pricing
    "openai": [
        {"patterns": ("gpt-6-astra",), "pricing": {"currency": "USD", "inputPerMillion": 10, "outputPerMillion": 50}},
        {"patterns": ("gpt-6.1-sol",), "pricing": {"currency": "USD", "inputPerMillion": 2, "outputPerMillion": 10}},
        {"patterns": ("gpt-6-luna",), "pricing": {"currency": "USD", "inputPerMillion": 0.1, "outputPerMillion": 0.5}},
        {"patterns": ("gpt-6-sol",), "pricing": {"currency": "USD", "inputPerMillion": 2, "outputPerMillion": 10}},
        {"patterns": ("gpt-5.6-sol",), "pricing": {"currency": "USD", "inputPerMillion": 4, "outputPerMillion": 20}},
        {"patterns": ("gpt-5.6-terra",), "pricing": {"currency": "USD", "inputPerMillion": 2, "outputPerMillion": 12}},
        {"patterns": ("gpt-5.6-luna",), "pricing": {"currency": "USD", "inputPerMillion": 0.2, "outputPerMillion": 1.2}},
        {"patterns": ("gpt-5.5-pro",), "pricing": {"currency": "USD", "inputPerMillion": 30, "outputPerMillion": 180}},
        {"patterns": ("gpt-5.5",), "pricing": {"currency": "USD", "inputPerMillion": 5, "outputPerMillion": 30}},
        {"patterns": ("gpt-5.4-pro",), "pricing": {"currency": "USD", "inputPerMillion": 30, "outputPerMillion": 180}},
        {"patterns": ("gpt-5.4-mini",), "pricing": {"currency": "USD", "inputPerMillion": 0.75, "outputPerMillion": 4.5}},
        {"patterns": ("gpt-5.4-nano",), "pricing": {"currency": "USD", "inputPerMillion": 0.2, "outputPerMillion": 1.25}},
        {"patterns": ("gpt-5.4",), "pricing": {"currency": "USD", "inputPerMillion": 2.5, "outputPerMillion": 15}},
        {"patterns": ("gpt-5.3-codex",), "pricing": {"currency": "USD", "inputPerMillion": 1.75, "outputPerMillion": 14}},
        {"patterns": ("gpt-5.2-pro",), "pricing": {"currency": "USD", "inputPerMillion": 21, "outputPerMillion": 168}},
        {"patterns": ("gpt-5.2",), "pricing": {"currency": "USD", "inputPerMillion": 1.75, "outputPerMillion": 14}},
        {"patterns": ("gpt-5.1",), "pricing": {"currency": "USD", "inputPerMillion": 1.25, "outputPerMillion": 10}},
        {"patterns": ("gpt-5-pro",), "pricing": {"currency": "USD", "inputPerMillion": 15, "outputPerMillion": 120}},
        {"patterns": ("gpt-5-mini",), "pricing": {"currency": "USD", "inputPerMillion": 0.25, "outputPerMillion": 2}},
        {"patterns": ("gpt-5-nano",), "pricing": {"currency": "USD", "inputPerMillion": 0.05, "outputPerMillion": 0.4}},
        {"patterns": ("gpt-5",), "pricing": {"currency": "USD", "inputPerMillion": 1.25, "outputPerMillion": 10}},
        {"patterns": ("gpt-4.1-nano", "gpt-4.1-nano-2025-04-14"), "pricing": {"currency": "USD", "inputPerMillion": 0.1, "outputPerMillion": 0.4}},
        {"patterns": ("gpt-4.1-mini", "gpt-4.1-mini-2025-04-14"), "pricing": {"currency": "USD", "inputPerMillion": 0.4, "outputPerMillion": 1.6}},
        {"patterns": ("gpt-4.1", "gpt-4.1-2025-04-14"), "pricing": {"currency": "USD", "inputPerMillion": 2, "outputPerMillion": 8}},
        {"patterns": ("gpt-4o-mini", "gpt-4o-mini-2024-07-18"), "pricing": {"currency": "USD", "inputPerMillion": 0.15, "outputPerMillion": 0.6}},
        {"patterns": ("gpt-4o-2024-05-13",), "pricing": {"currency": "USD", "inputPerMillion": 5, "outputPerMillion": 15}},
        {"patterns": ("gpt-4o", "chatgpt-4o", "gpt-4o-2024-08-06", "gpt-4o-2024-11-20"), "pricing": {"currency": "USD", "inputPerMillion": 2.5, "outputPerMillion": 10}},
        {"patterns": ("o1-pro",), "pricing": {"currency": "USD", "inputPerMillion": 150, "outputPerMillion": 600}},
        {"patterns": ("o1",), "pricing": {"currency": "USD", "inputPerMillion": 15, "outputPerMillion": 60}},
        {"patterns": ("o3-pro",), "pricing": {"currency": "USD", "inputPerMillion": 20, "outputPerMillion": 80}},
        {"patterns": ("o3-mini",), "pricing": {"currency": "USD", "inputPerMillion": 1.1, "outputPerMillion": 4.4}},
        {"patterns": ("o4-mini", "o4-mini-2025-04-16"), "pricing": {"currency": "USD", "inputPerMillion": 1.1, "outputPerMillion": 4.4}},
        {"patterns": ("o3",), "pricing": {"currency": "USD", "inputPerMillion": 2, "outputPerMillion": 8}},
        {"patterns": ("gpt-4-turbo", "gpt-4-turbo-2024-04-09"), "pricing": {"currency": "USD", "inputPerMillion": 10, "outputPerMillion": 30}},
        {"patterns": ("gpt-4-0613", "gpt-4"), "pricing": {"currency": "USD", "inputPerMillion": 30, "outputPerMillion": 60}},
        {"patterns": ("gpt-3.5-turbo-instruct",), "pricing": {"currency": "USD", "inputPerMillion": 1.5, "outputPerMillion": 2}},
        {"patterns": ("gpt-3.5-turbo-1106",), "pricing": {"currency": "USD", "inputPerMillion": 1, "outputPerMillion": 2}},
        {"patterns": ("gpt-3.5-turbo-0125",), "pricing": {"currency": "USD", "inputPerMillion": 0.5, "outputPerMillion": 1.5}},
        {"patterns": ("gpt-3.5-turbo",), "pricing": {"currency": "USD", "inputPerMillion": 0.5, "outputPerMillion": 1.5}},
        {"patterns": ("text-embedding-3-large",), "pricing": {"currency": "USD", "inputPerMillion": 0.13, "outputPerMillion": 0}},
        {"patterns": ("text-embedding-3-small",), "pricing": {"currency": "USD", "inputPerMillion": 0.02, "outputPerMillion": 0}},
        {"patterns": ("text-embedding-ada-002",), "pricing": {"currency": "USD", "inputPerMillion": 0.1, "outputPerMillion": 0}},
        {"patterns": ("davinci-002",), "pricing": {"currency": "USD", "inputPerMillion": 2, "outputPerMillion": 2}},
        {"patterns": ("babbage-002",), "pricing": {"currency": "USD", "inputPerMillion": 0.4, "outputPerMillion": 0.4}},
    ],
    "qwen": [
        {
            "patterns": ("qwen-max", "qwen3-max"),
            "pricing": {"currency": "CNY", "inputPerMillion": 2.4, "outputPerMillion": 9.6},
        },
        {
            "patterns": ("qwen-plus", "qwen3-plus"),
            "pricing": {"currency": "CNY", "inputPerMillion": 0.8, "outputPerMillion": 2},
        },
        {
            "patterns": ("qwen-turbo", "qwen3-turbo"),
            "pricing": {"currency": "CNY", "inputPerMillion": 0.3, "outputPerMillion": 0.6},
        },
    ],
}

_HOST_PROVIDER_CODES: dict[str, str] = {
    "api.deepseek.com": "deepseek",
    "api.openai.com": "openai",
    "dashscope.aliyuncs.com": "qwen",
}

# 与 OpenAI 官方定价表共用（Azure 部署名通常与 OpenAI 模型 ID 一致或相近）。
_CATALOG_PROVIDER_ALIASES: dict[str, str] = {
    "azure-openai": "openai",
}


def resolve_model_connection(
    instance: dict[str, Any],
    provider: dict[str, Any],
    group: dict[str, Any] | None = None,
) -> tuple[str, str, str]:
    """解析模型连接所需的 Base URL、API Key 与模型 ID。"""
    base_url = str(
        (group or {}).get("base_url")
        or instance.get("base_url")
        or provider.get("default_base_url")
        or ""
    ).strip().rstrip("/")
    model_name = str(instance.get("model_name") or "").strip()
    encrypted = str((group or {}).get("api_key_encrypted") or instance.get("api_key_encrypted") or "")
    api_key = decrypt_secret(encrypted) if encrypted else ""
    return base_url, api_key, model_name


async def resolve_official_model_pricing_for_instance(
    instance: dict[str, Any],
    main_id: str,
) -> dict[str, Any] | None:
    """在测试配置时尝试解析官方/网关公布的模型单价。"""
    try:
        provider = await find_provider_by_id(str(instance.get("provider_id") or ""))
    except Exception:
        return None
    if not provider:
        return None
    group: dict[str, Any] | None = None
    group_id = str(instance.get("group_id") or "")
    if group_id:
        group = await find_group(group_id, main_id)
    return await asyncio.to_thread(resolve_official_model_pricing, instance, provider, group)


def resolve_official_model_pricing(
    instance: dict[str, Any],
    provider: dict[str, Any],
    group: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """从 /models 列表或内置官方价目表解析单价，返回前端可用的 pricing 对象。"""
    base_url, api_key, model_name = resolve_model_connection(instance, provider, group)
    if not model_name:
        return None

    from_api = _fetch_models_endpoint_pricing(base_url, api_key, model_name)
    if from_api is not None and _is_meaningful_pricing(from_api):
        return _as_client_pricing(from_api)

    provider_code = _resolve_provider_code(provider, base_url)
    from_catalog = _lookup_provider_catalog(provider_code, model_name)
    if from_catalog is not None:
        return _as_client_pricing(from_catalog)
    return None


def _as_client_pricing(pricing: dict[str, Any]) -> dict[str, Any] | None:
    """将内部 pricing 规范化为 API 响应结构。"""
    try:
        normalized = normalize_pricing(pricing)
    except ValueError:
        return None
    if normalized is None:
        return None
    return {
        "currency": normalized["currency"],
        "inputPerMillion": float(normalized["inputPerMillion"]),
        "outputPerMillion": float(normalized["outputPerMillion"]),
    }


def _resolve_provider_code(provider: dict[str, Any], base_url: str) -> str:
    """根据供应商配置与 Base URL 推断价目表所属供应商。"""
    code = str(provider.get("code") or "").strip().lower()
    host = (urlparse(base_url).hostname or "").lower()
    if host.endswith(".openai.azure.com") or host == "openai.azure.com":
        return "openai"
    if code and code != "custom-openai-compatible":
        return _CATALOG_PROVIDER_ALIASES.get(code, code)
    return _HOST_PROVIDER_CODES.get(host, code or "custom-openai-compatible")


def _lookup_provider_catalog(provider_code: str, model_name: str) -> dict[str, Any] | None:
    """在内置官方价目表中查找模型单价。"""
    catalog_code = _CATALOG_PROVIDER_ALIASES.get(provider_code, provider_code)
    entries = _PROVIDER_CATALOG.get(catalog_code)
    if not entries:
        return None
    normalized = model_name.strip().lower()
    ranked: list[tuple[int, dict[str, Any]]] = []
    for entry in entries:
        for pattern in entry.get("patterns", ()):
            token = str(pattern).lower()
            if not token:
                continue
            if normalized == token or normalized.startswith(f"{token}-"):
                ranked.append((len(token), entry))
    if not ranked:
        return None
    ranked.sort(key=lambda item: item[0], reverse=True)
    return dict(ranked[0][1]["pricing"])


def _is_meaningful_pricing(pricing: dict[str, Any]) -> bool:
    """忽略网关返回的全零占位单价，以便回退到官方价目表。"""
    try:
        input_rate = Decimal(str(pricing.get("inputPerMillion")))
        output_rate = Decimal(str(pricing.get("outputPerMillion")))
    except (InvalidOperation, TypeError):
        return False
    return input_rate > 0 or output_rate > 0


def _fetch_models_endpoint_pricing(base_url: str, api_key: str, model_name: str) -> dict[str, Any] | None:
    """调用 OpenAI 兼容 GET /models，解析网关返回的单价字段。"""
    if not base_url or not api_key:
        return None
    for url in _models_list_urls(base_url):
        payload = _http_get_json(url, api_key)
        if not isinstance(payload, dict):
            continue
        data = payload.get("data")
        if not isinstance(data, list):
            continue
        for item in data:
            if not isinstance(item, dict):
                continue
            if not _model_entry_matches(item, model_name):
                continue
            parsed = _parse_model_entry_pricing(item)
            if parsed is not None and _is_meaningful_pricing(parsed):
                return parsed
    return None


def _models_list_urls(base_url: str) -> list[str]:
    """生成可能有效的 /models 列表 URL。"""
    trimmed = base_url.rstrip("/")
    if trimmed.endswith("/v1"):
        return [f"{trimmed}/models"]
    return [f"{trimmed}/v1/models", f"{trimmed}/models"]


def _http_get_json(url: str, api_key: str) -> Any:
    """带 Bearer 认证 GET JSON。"""
    request = urllib.request.Request(
        url,
        headers={"Authorization": f"Bearer {api_key}", "Accept": "application/json"},
        method="GET",
    )
    try:
        with urllib.request.urlopen(
            request,
            timeout=_MODELS_FETCH_TIMEOUT_SECONDS,
            context=build_model_test_ssl_context(),
        ) as response:
            return json.loads(response.read().decode("utf-8", errors="replace"))
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, json.JSONDecodeError, ValueError):
        return None


def _model_entry_matches(entry: dict[str, Any], model_name: str) -> bool:
    """判断 models 列表项是否与配置的模型 ID 对应。"""
    candidates = [
        str(entry.get("id") or ""),
        str(entry.get("name") or ""),
        str(entry.get("model") or ""),
    ]
    target = model_name.strip().lower()
    for candidate in candidates:
        normalized = candidate.strip().lower()
        if not normalized:
            continue
        if normalized == target:
            return True
        if normalized.endswith(f"/{target}"):
            return True
    return False


def _parse_model_entry_pricing(entry: dict[str, Any]) -> dict[str, Any] | None:
    """从 models 列表项解析单价（支持 OpenRouter 等常见字段）。"""
    pricing = entry.get("pricing")
    if isinstance(pricing, dict):
        prompt = pricing.get("prompt") if pricing.get("prompt") is not None else pricing.get("input")
        completion = pricing.get("completion") if pricing.get("completion") is not None else pricing.get("output")
        if prompt is not None and completion is not None:
            return _per_token_rates_to_pricing(str(prompt), str(completion), currency="USD")

    for input_key, output_key in (
        ("input_price", "output_price"),
        ("inputPrice", "outputPrice"),
        ("input_token_price", "output_token_price"),
    ):
        if input_key in entry and output_key in entry:
            currency = str(entry.get("currency") or entry.get("price_currency") or "USD").upper()
            if currency not in ("CNY", "USD"):
                currency = "USD"
            return _per_token_rates_to_pricing(str(entry[input_key]), str(entry[output_key]), currency=currency)
    return None


def _per_token_rates_to_pricing(prompt_rate: str, completion_rate: str, *, currency: str) -> dict[str, Any] | None:
    """将「每 Token」单价转换为「每 100 万 Token」单价。"""
    try:
        prompt = Decimal(prompt_rate)
        completion = Decimal(completion_rate)
    except (InvalidOperation, ValueError):
        return None
    if not prompt.is_finite() or not completion.is_finite():
        return None
    million = Decimal(1000000)
    return {
        "currency": currency,
        "inputPerMillion": float((prompt * million).normalize()),
        "outputPerMillion": float((completion * million).normalize()),
    }


__all__ = [
    "resolve_model_connection",
    "resolve_official_model_pricing",
    "resolve_official_model_pricing_for_instance",
]
