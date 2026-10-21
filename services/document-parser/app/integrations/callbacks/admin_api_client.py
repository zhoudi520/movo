from __future__ import annotations

import json
import logging
from typing import Any
from urllib.parse import urlparse, urlunparse

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)


def _resolve_callback_url(callback_url: str) -> str:
    """
    Resolve callback URL, optionally rewriting host for in-cluster admin-api.

    When jobs were enqueued with a browser/host URL (127.0.0.1), document-worker
    can still reach admin-api via ``admin_api_callback_base_url``.
    """
    url = str(callback_url or "").strip()
    rewrite = str(settings.admin_api_callback_base_url or "").strip().rstrip("/")
    if not url or not rewrite:
        return url
    parsed = urlparse(url)
    base = urlparse(rewrite)
    if not parsed.path or not base.scheme or not base.netloc:
        return url
    resolved = urlunparse((base.scheme, base.netloc, parsed.path, parsed.params, parsed.query, parsed.fragment))
    if resolved != url:
        logger.info(f"admin 回调 URL 重写: {url} -> {resolved}")
    return resolved


def post_callback(callback_url: str, callback_token: str, payload: dict[str, Any]) -> None:
    """
    POST parse/index/mineru callback payload to admin-api.

    Args:
        callback_url: Target callback URL from job payload.
        callback_token: Bearer token shared with admin-api.
        payload: JSON-serializable callback body.

    Raises:
        RuntimeError: When the callback HTTP request fails.
    """
    url = _resolve_callback_url(callback_url)
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    headers = {
        "Authorization": f"Bearer {callback_token}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    try:
        with httpx.Client(timeout=httpx.Timeout(60.0, connect=15.0)) as client:
            response = client.post(url, content=data, headers=headers)
            response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        body = (exc.response.text or "")[:800]
        status = exc.response.status_code
        logger.error(f"admin 回调 HTTP 失败: url={url}, status={status}, body={body}, payload={payload}")
        raise RuntimeError(f"admin 回调失败 HTTP {status}: {body}") from exc
    except httpx.HTTPError as exc:
        logger.error(f"admin 回调连接失败: url={url}, error={exc}, payload={payload}")
        raise RuntimeError(f"admin 回调连接失败: {exc}") from exc
