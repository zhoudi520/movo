"""Admin API for Jira MCP gateway settings."""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from app.api.deps import get_current_admin_user
from app.services.jira_mcp_gateway import (
    ENDPOINT_PRESETS,
    load_settings_doc,
    save_settings,
    serialize_public,
    test_jira_credentials,
)

router = APIRouter()


class JiraMcpGatewayPayload(BaseModel):
    """Request body for saving Jira MCP gateway settings."""

    enabled: bool = True
    jiraBaseUrl: str = Field(default="", max_length=500)
    personalAccessToken: str = Field(default="", max_length=4000)
    gatewayKey: str = Field(default="", max_length=512)
    mcpToolEndpointPreset: str = Field(default="docker_internal", max_length=64)


class JiraMcpGatewayTestJiraPayload(BaseModel):
    """Optional overrides for Jira connectivity test."""

    jiraBaseUrl: str = Field(default="", max_length=500)
    personalAccessToken: str = Field(default="", max_length=4000)


class JiraMcpGatewayTestMcpPayload(BaseModel):
    """Optional overrides for MCP gateway connectivity test."""

    gatewayKey: str = Field(default="", max_length=512)
    mainId: str = Field(default="", max_length=128)


def _main_id(current_user: dict[str, Any]) -> str:
    return str(current_user.get("main_id") or "default")


@router.get("")
async def get_jira_mcp_gateway_settings(current_user: dict[str, Any] = Depends(get_current_admin_user)) -> dict[str, Any]:
    """Return current tenant Jira MCP gateway settings."""
    doc = await load_settings_doc(_main_id(current_user))
    payload = serialize_public(doc)
    payload["endpointPresets"] = ENDPOINT_PRESETS
    return payload


@router.put("")
async def save_jira_mcp_gateway_settings(
    payload: JiraMcpGatewayPayload,
    current_user: dict[str, Any] = Depends(get_current_admin_user),
) -> dict[str, Any]:
    """Save tenant Jira MCP gateway settings and sync linked MCP tool."""
    try:
        saved = await save_settings(
            main_id=_main_id(current_user),
            jira_base_url=payload.jiraBaseUrl,
            personal_access_token=payload.personalAccessToken,
            gateway_key=payload.gatewayKey,
            preset=payload.mcpToolEndpointPreset,
            enabled=payload.enabled,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    saved["endpointPresets"] = ENDPOINT_PRESETS
    return saved


@router.post("/test-jira")
async def test_jira_mcp_gateway_jira(
    payload: JiraMcpGatewayTestJiraPayload,
    current_user: dict[str, Any] = Depends(get_current_admin_user),
) -> dict[str, Any]:
    """Validate Jira REST credentials."""
    main_id = _main_id(current_user)
    doc = await load_settings_doc(main_id) or {}
    jira_url = payload.jiraBaseUrl.strip() or str(doc.get("jira_base_url") or "")
    token = payload.personalAccessToken.strip()
    if not token and doc:
        from app.services.jira_mcp_gateway import _decrypt_field

        token = _decrypt_field(doc, "personal_access_token_encrypted")
    try:
        return test_jira_credentials(jira_base_url=jira_url, personal_access_token=token)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.post("/test-mcp")
async def test_jira_mcp_gateway_mcp(
    payload: JiraMcpGatewayTestMcpPayload,
    current_user: dict[str, Any] = Depends(get_current_admin_user),
) -> dict[str, Any]:
    """Run MCP initialize against the shared gateway URL."""
    main_id = _main_id(current_user)
    doc = await load_settings_doc(main_id) or {}
    from app.services.jira_mcp_gateway import _decrypt_field, _endpoint_for_preset

    gateway_key = payload.gatewayKey.strip() or _decrypt_field(doc, "gateway_key_encrypted")
    if not gateway_key:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="请先保存或填写网关密钥")
    endpoint = _endpoint_for_preset(str(doc.get("mcp_tool_endpoint_preset") or "docker_internal"))
    body = json.dumps(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2025-06-18",
                "capabilities": {},
                "clientInfo": {"name": "movo-admin-test", "version": "1.0"},
            },
        }
    ).encode("utf-8")
    request = urllib.request.Request(
        endpoint,
        data=body,
        headers={
            "Authorization": f"Bearer {gateway_key}",
            "Accept": "application/json, text/event-stream",
            "Content-Type": "application/json",
            "MCP-Protocol-Version": "2025-06-18",
            "X-MOVO-Main-ID": payload.mainId.strip() or main_id,
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            text = response.read(4000).decode("utf-8", errors="replace")
            return {"success": True, "status": response.status, "bodyPreview": text[:800]}
    except urllib.error.HTTPError as exc:
        detail = exc.read(2000).decode("utf-8", errors="replace")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"MCP 网关返回 HTTP {exc.code}: {detail[:300]}",
        ) from exc
