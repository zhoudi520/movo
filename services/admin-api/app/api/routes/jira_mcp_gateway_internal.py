"""Internal API consumed by the jira-mcp-gateway container."""

from __future__ import annotations

import hmac

from fastapi import APIRouter, Header, HTTPException

from app.core.config import settings
from app.services.jira_mcp_gateway import list_runtime_tenant_configs

router = APIRouter()


def _require_service(token: str) -> None:
    """Validate service token for internal gateway config reads."""
    expected = str(settings.backend_service_token or "")
    if not token or not expected or not hmac.compare_digest(token, expected):
        raise HTTPException(status_code=401, detail="invalid_service_token")


@router.get("/runtime-config")
async def get_jira_mcp_gateway_runtime_config(
    service_token: str = Header(default="", alias="X-MOVO-Service-Token"),
) -> dict:
    """Return enabled tenant configs for the gateway router."""
    _require_service(service_token)
    return await list_runtime_tenant_configs()
