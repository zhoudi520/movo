"""Per-user Jira credentials for the tenant-aware MCP gateway."""

from __future__ import annotations

import datetime
import uuid
from typing import Any

from app.core.db import get_db
from app.repositories.model_repository import decrypt_secret, encrypt_secret, mask_secret
from app.services.jira_mcp_gateway import (
    LINKED_TOOL_NAME,
    _decrypt_field,
    _endpoint_for_preset,
    load_settings_doc,
    test_jira_credentials,
)

USER_COLLECTION = "jira_mcp_user_credentials"

_CONFIG_VERSION_SCALE = 1_000_000


def _now() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc)


def _composite_config_version(tenant_version: int, user_version: int) -> int:
    """Combine tenant and user config versions for gateway subprocess restarts."""
    return int(tenant_version) * _CONFIG_VERSION_SCALE + int(user_version)


async def load_user_doc(main_id: str, user_id: str) -> dict[str, Any] | None:
    """Load raw user Jira credential document."""
    main_id = str(main_id or "default").strip()
    user_id = str(user_id or "").strip()
    if not user_id:
        return None
    return await get_db()[USER_COLLECTION].find_one({"main_id": main_id, "user_id": user_id})


def serialize_user_public(doc: dict[str, Any] | None) -> dict[str, Any]:
    """Serialize user Jira settings without plaintext token (internal summaries)."""
    row = doc or {}
    has_token = bool(str(row.get("personal_access_token_encrypted") or ""))
    return {
        "mainId": str(row.get("main_id") or ""),
        "userId": str(row.get("user_id") or ""),
        "configured": has_token and bool(str(row.get("jira_base_url") or "")),
        "jiraBaseUrl": str(row.get("jira_base_url") or ""),
        "personalAccessTokenMasked": str(row.get("personal_access_token_masked") or ""),
        "configVersion": int(row.get("config_version") or 0),
        "updatedAt": row.get("updated_at").isoformat() if isinstance(row.get("updated_at"), datetime.datetime) else "",
    }


def serialize_user_owner(doc: dict[str, Any] | None) -> dict[str, Any]:
    """Serialize user Jira settings for the credential owner (includes plaintext token)."""
    payload = serialize_user_public(doc)
    if doc:
        payload["personalAccessToken"] = _decrypt_field(doc, "personal_access_token_encrypted")
    else:
        payload["personalAccessToken"] = ""
    return payload


async def save_user_credentials(
    *,
    main_id: str,
    user_id: str,
    jira_base_url: str,
    personal_access_token: str,
    validate_jira: bool = True,
) -> dict[str, Any]:
    """Persist or update a user's Jira site URL and API token."""
    main_id = str(main_id or "default").strip()
    user_id = str(user_id or "").strip()
    if not user_id:
        raise ValueError("user_id 不能为空")

    jira_url = str(jira_base_url or "").strip().rstrip("/")
    if not jira_url:
        raise ValueError("Jira 站点 URL 不能为空")

    token_plain = str(personal_access_token or "").strip()
    existing = await load_user_doc(main_id, user_id)
    existing = existing or {}

    if not token_plain:
        token_encrypted = str(existing.get("personal_access_token_encrypted") or "")
        token_masked = str(existing.get("personal_access_token_masked") or "")
        token_for_test = _decrypt_field(existing, "personal_access_token_encrypted") if token_encrypted else ""
    else:
        token_for_test = token_plain
        token_encrypted = encrypt_secret(token_plain)
        token_masked = mask_secret(token_plain)

    if not token_encrypted:
        raise ValueError("Jira 凭证不能为空")

    if validate_jira:
        test_jira_credentials(jira_base_url=jira_url, personal_access_token=token_for_test)

    now = _now()
    next_version = int(existing.get("config_version") or 0) + 1
    doc_id = str(existing.get("_id") or uuid.uuid4().hex)
    doc = {
        "_id": doc_id,
        "main_id": main_id,
        "user_id": user_id,
        "jira_base_url": jira_url,
        "personal_access_token_encrypted": token_encrypted,
        "personal_access_token_masked": token_masked,
        "config_version": next_version,
        "updated_at": now,
    }
    await get_db()[USER_COLLECTION].update_one(
        {"main_id": main_id, "user_id": user_id},
        {"$set": doc, "$setOnInsert": {"created_at": now}},
        upsert=True,
    )
    return await get_user_jira_workspace(main_id=main_id, user_id=user_id)


async def delete_user_credentials(*, main_id: str, user_id: str) -> dict[str, Any]:
    """Remove a user's Jira binding so tenant default credentials apply."""
    main_id = str(main_id or "default").strip()
    user_id = str(user_id or "").strip()
    if not user_id:
        raise ValueError("user_id 不能为空")
    await get_db()[USER_COLLECTION].delete_one({"main_id": main_id, "user_id": user_id})
    return await get_user_jira_workspace(main_id=main_id, user_id=user_id)


def _serialize_tenant_mcp_tool(tenant_doc: dict[str, Any] | None) -> dict[str, Any]:
    """Expose org gateway MCP endpoint and Bearer token for end-user tool configuration."""
    row = tenant_doc or {}
    enabled = bool(row.get("enabled"))
    preset = str(row.get("mcp_tool_endpoint_preset") or "docker_internal")
    endpoint = _endpoint_for_preset(preset) if enabled else ""
    return {
        "enabled": enabled,
        "toolName": LINKED_TOOL_NAME,
        "endpoint": endpoint,
        "authType": "none",
        "authToken": "",
        "authTokenMasked": "",
        "mcpToolEndpointPreset": preset,
    }


async def get_user_jira_workspace(*, main_id: str, user_id: str) -> dict[str, Any]:
    """Return user Jira binding plus tenant MCP gateway connection hints."""
    doc = await load_user_doc(main_id, user_id)
    tenant_doc = await load_settings_doc(main_id)
    return {
        **serialize_user_owner(doc),
        "mcpTool": _serialize_tenant_mcp_tool(tenant_doc),
    }


async def get_user_credentials_public(*, main_id: str, user_id: str) -> dict[str, Any]:
    """Return user Jira workspace view (credentials + MCP gateway hints)."""
    return await get_user_jira_workspace(main_id=main_id, user_id=user_id)


class JiraMcpConfigError(ValueError):
    """Raised when effective Jira MCP config cannot be resolved."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


async def resolve_effective_jira_config(main_id: str, user_id: str) -> dict[str, Any]:
    """
    Resolve Jira URL and token for a MCP request.

    Uses per-user credentials when present and decryptable; otherwise falls back to
    enabled tenant gateway settings.
    """
    main_id = str(main_id or "default").strip()
    user_id = str(user_id or "").strip()
    tenant_doc = await load_settings_doc(main_id)
    if not tenant_doc or not bool(tenant_doc.get("enabled")):
        raise JiraMcpConfigError("tenant_disabled", "租户 Jira MCP 网关未启用")

    tenant_version = int(tenant_doc.get("config_version") or 0)
    gateway_key = _decrypt_field(tenant_doc, "gateway_key_encrypted")
    if not gateway_key:
        raise JiraMcpConfigError("tenant_misconfigured", "租户网关密钥未配置")

    user_version = 0
    jira_url = ""
    token = ""

    if user_id and user_id != "__default__":
        user_doc = await load_user_doc(main_id, user_id)
        if user_doc:
            user_token = _decrypt_field(user_doc, "personal_access_token_encrypted")
            user_url = str(user_doc.get("jira_base_url") or "").strip().rstrip("/")
            if user_token and user_url:
                jira_url = user_url
                token = user_token
                user_version = int(user_doc.get("config_version") or 0)

    if not token or not jira_url:
        jira_url = str(tenant_doc.get("jira_base_url") or "").strip().rstrip("/")
        token = _decrypt_field(tenant_doc, "personal_access_token_encrypted")
        user_version = 0

    if not jira_url or not token:
        raise JiraMcpConfigError("no_credentials", "无可用 Jira 凭证（用户未绑定且企业默认未配置）")

    source = "user" if user_version > 0 else "tenant_default"
    return {
        "mainId": main_id,
        "userId": user_id or "__default__",
        "jiraBaseUrl": jira_url,
        "personalAccessToken": token,
        "gatewayKey": gateway_key,
        "configVersion": _composite_config_version(tenant_version, user_version),
        "tenantConfigVersion": tenant_version,
        "userConfigVersion": user_version,
        "credentialSource": source,
    }


async def ensure_user_indexes() -> None:
    """Create Mongo indexes for per-user Jira credentials."""
    db = get_db()
    await db[USER_COLLECTION].create_index([("main_id", 1), ("user_id", 1)], unique=True)
