"""Jira MCP gateway settings, external tool sync, and runtime config for the gateway container."""

from __future__ import annotations

import base64
import datetime
import secrets
import urllib.error
import urllib.request
import uuid
from typing import Any

from app.core.db import get_db
from app.repositories.model_repository import decrypt_secret, encrypt_secret, mask_secret
from app.services.organization_tools import organization_tool_fields, organization_tool_query

COLLECTION = "jira_mcp_gateway_settings"
LINKED_TOOL_NAME = "Jira（内置网关）"

ENDPOINT_PRESETS: dict[str, str] = {
    "docker_internal": "http://jira-mcp-gateway:8766/mcp",
    "host_loopback": "http://127.0.0.1:8766/mcp",
}


def _now() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc)


def _safe_dict(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _endpoint_for_preset(preset: str) -> str:
    key = str(preset or "docker_internal").strip()
    return ENDPOINT_PRESETS.get(key, ENDPOINT_PRESETS["docker_internal"])


async def load_settings_doc(main_id: str) -> dict[str, Any] | None:
    """Load raw gateway settings document for a tenant."""
    return await get_db()[COLLECTION].find_one({"main_id": str(main_id or "default")})


def serialize_public(doc: dict[str, Any] | None) -> dict[str, Any]:
    """Serialize gateway settings for admin UI (Jira token in plaintext for editing)."""
    row = doc or {}
    return {
        "mainId": str(row.get("main_id") or "default"),
        "enabled": bool(row.get("enabled", False)),
        "jiraBaseUrl": str(row.get("jira_base_url") or ""),
        "personalAccessToken": _decrypt_field(row, "personal_access_token_encrypted") if row else "",
        "gatewayKeyMasked": str(row.get("gateway_key_masked") or ""),
        "configVersion": int(row.get("config_version") or 0),
        "mcpToolEndpointPreset": str(row.get("mcp_tool_endpoint_preset") or "docker_internal"),
        "linkedToolId": str(row.get("linked_tool_id") or ""),
        "resolvedMcpEndpoint": _endpoint_for_preset(str(row.get("mcp_tool_endpoint_preset") or "docker_internal")),
        "updatedAt": row.get("updated_at").isoformat() if isinstance(row.get("updated_at"), datetime.datetime) else "",
    }


def _decrypt_field(doc: dict[str, Any], field: str) -> str:
    encrypted = str(doc.get(field) or "")
    if not encrypted:
        return ""
    try:
        return decrypt_secret(encrypted)
    except ValueError:
        return ""


async def save_settings(
    *,
    main_id: str,
    jira_base_url: str,
    personal_access_token: str,
    gateway_key: str,
    preset: str,
    enabled: bool,
) -> dict[str, Any]:
    """Persist tenant gateway settings and sync linked external MCP tool."""
    main_id = str(main_id or "default")
    db = get_db()
    existing = await load_settings_doc(main_id)
    existing = existing or {}
    now = _now()
    next_version = int(existing.get("config_version") or 0) + 1

    jira_url = str(jira_base_url or existing.get("jira_base_url") or "").strip().rstrip("/")
    if not jira_url:
        raise ValueError("Jira 站点 URL 不能为空")

    token_plain = str(personal_access_token or "").strip()
    if token_plain:
        token_encrypted = encrypt_secret(token_plain)
        token_masked = mask_secret(token_plain)
    else:
        token_encrypted = str(existing.get("personal_access_token_encrypted") or "")
        token_masked = str(existing.get("personal_access_token_masked") or "")
    if not token_encrypted:
        raise ValueError("Jira 凭证不能为空")

    gateway_plain = str(gateway_key or "").strip()
    if gateway_plain:
        gateway_encrypted = encrypt_secret(gateway_plain)
        gateway_masked = mask_secret(gateway_plain)
    else:
        gateway_plain = _decrypt_field(existing, "gateway_key_encrypted")
        if not gateway_plain:
            gateway_plain = secrets.token_urlsafe(32)
            gateway_encrypted = encrypt_secret(gateway_plain)
            gateway_masked = mask_secret(gateway_plain)
        else:
            gateway_encrypted = str(existing.get("gateway_key_encrypted") or "")
            gateway_masked = str(existing.get("gateway_key_masked") or "")

    preset_key = str(preset or existing.get("mcp_tool_endpoint_preset") or "docker_internal").strip()
    if preset_key not in ENDPOINT_PRESETS:
        raise ValueError("无效的 MCP endpoint 预设")

    doc_id = str(existing.get("_id") or uuid.uuid4().hex)
    doc = {
        "_id": doc_id,
        "main_id": main_id,
        "enabled": bool(enabled),
        "jira_base_url": jira_url,
        "personal_access_token_encrypted": token_encrypted,
        "personal_access_token_masked": token_masked,
        "gateway_key_encrypted": gateway_encrypted,
        "gateway_key_masked": gateway_masked,
        "config_version": next_version,
        "mcp_tool_endpoint_preset": preset_key,
        "updated_at": now,
    }
    linked_tool_id = str(existing.get("linked_tool_id") or "")
    linked_tool_id = await _sync_linked_external_tool(
        db,
        main_id=main_id,
        linked_tool_id=linked_tool_id,
        endpoint=_endpoint_for_preset(preset_key),
        gateway_key=gateway_plain,
    )
    doc["linked_tool_id"] = linked_tool_id

    await db[COLLECTION].update_one(
        {"main_id": main_id},
        {"$set": doc, "$setOnInsert": {"created_at": now}},
        upsert=True,
    )
    saved = await load_settings_doc(main_id)
    return serialize_public(saved or doc)


async def _sync_linked_external_tool(
    db: Any,
    *,
    main_id: str,
    linked_tool_id: str,
    endpoint: str,
    gateway_key: str,
) -> str:
    """Create or update organization MCP tool pointing at the shared gateway URL."""
    config_patch = {
        "endpoint": endpoint,
        "authType": "none",
        "authToken": "",
        "headers": {},
        "timeoutSeconds": 45,
    }
    now = _now()
    if linked_tool_id:
        existing = await db.external_tools.find_one(organization_tool_query(main_id, _id=linked_tool_id))
        if existing:
            merged_config = _safe_dict(existing.get("config"))
            merged_config.update(config_patch)
            if "enabledToolNames" not in merged_config:
                merged_config["enabledToolNames"] = []
            await db.external_tools.update_one(
                organization_tool_query(main_id, _id=linked_tool_id),
                {"$set": {"config": merged_config, "type": "mcp", "updated_at": now}},
            )
            return linked_tool_id

    by_name = await db.external_tools.find_one(organization_tool_query(main_id, name=LINKED_TOOL_NAME, type="mcp"))
    if by_name:
        tool_id = str(by_name.get("_id") or "")
        merged_config = _safe_dict(by_name.get("config"))
        merged_config.update(config_patch)
        if "enabledToolNames" not in merged_config:
            merged_config["enabledToolNames"] = []
        await db.external_tools.update_one(
            organization_tool_query(main_id, _id=tool_id),
            {"$set": {"config": merged_config, "updated_at": now}},
        )
        return tool_id

    tool_id = uuid.uuid4().hex
    doc = {
        "_id": tool_id,
        "main_id": main_id,
        **organization_tool_fields(),
        "name": LINKED_TOOL_NAME,
        "type": "mcp",
        "description": "通过内置 Jira MCP 网关连接 Atlassian Jira Cloud。",
        "usage_hint": "在 Skill 中选择具体 Jira MCP 子工具后再调用。",
        "tags": ["jira", "mcp", "gateway"],
        "status": "disabled",
        "config": {**config_patch, "enabledToolNames": []},
        "last_test_status": "untested",
        "last_test_at": None,
        "last_test_message": "",
        "discovered_tools": [],
        "created_at": now,
        "updated_at": now,
    }
    await db.external_tools.insert_one(doc)
    return tool_id


async def list_runtime_tenant_configs() -> dict[str, Any]:
    """Build gateway runtime payload for all enabled tenants."""
    db = get_db()
    cursor = db[COLLECTION].find({"enabled": True})
    tenants: list[dict[str, Any]] = []
    global_version = 0
    async for doc in cursor:
        main_id = str(doc.get("main_id") or "")
        if not main_id:
            continue
        token = _decrypt_field(doc, "personal_access_token_encrypted")
        gateway_key = _decrypt_field(doc, "gateway_key_encrypted")
        jira_url = str(doc.get("jira_base_url") or "").strip()
        version = int(doc.get("config_version") or 0)
        if not token or not gateway_key or not jira_url:
            continue
        global_version += version
        tenants.append(
            {
                "mainId": main_id,
                "configVersion": version,
                "jiraBaseUrl": jira_url,
                "personalAccessToken": token,
                "gatewayKey": gateway_key,
            }
        )
    return {"globalVersion": global_version, "tenants": tenants}


def test_jira_credentials(*, jira_base_url: str, personal_access_token: str) -> dict[str, Any]:
    """Call Jira REST /myself to validate credentials."""
    base = str(jira_base_url or "").strip().rstrip("/")
    token = str(personal_access_token or "").strip()
    if not base or not token:
        raise ValueError("Jira URL 与凭证不能为空")
    encoded = base64.b64encode(token.encode("utf-8")).decode("ascii")
    request = urllib.request.Request(
        f"{base}/rest/api/3/myself",
        headers={"Authorization": f"Basic {encoded}", "Accept": "application/json"},
        method="GET",
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            body = response.read(4000).decode("utf-8", errors="replace")
            return {"success": True, "status": response.status, "bodyPreview": body[:500]}
    except urllib.error.HTTPError as exc:
        detail = exc.read(2000).decode("utf-8", errors="replace")
        raise ValueError(f"Jira 返回 HTTP {exc.code}: {detail[:300]}") from exc


async def ensure_indexes() -> None:
    """Create Mongo indexes for gateway settings."""
    db = get_db()
    await db[COLLECTION].create_index([("main_id", 1)], unique=True)
    await db[COLLECTION].create_index([("enabled", 1), ("config_version", -1)])
