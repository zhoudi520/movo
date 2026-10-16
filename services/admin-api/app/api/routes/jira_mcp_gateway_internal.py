"""Internal API consumed by the jira-mcp-gateway container and chat-api."""

from __future__ import annotations

import hmac
from typing import Any

from fastapi import APIRouter, Header, HTTPException, Query
from pydantic import BaseModel, Field

from app.core.config import settings
from app.services.jira_mcp_gateway import list_runtime_tenant_configs
from app.services.jira_mcp_user_credentials import (
    JiraMcpConfigError,
    delete_user_credentials,
    get_user_credentials_public,
    resolve_effective_jira_config,
    save_user_credentials,
)

router = APIRouter()


def _require_service(token: str) -> None:
    """Validate service token for internal gateway config reads."""
    expected = str(settings.backend_service_token or "")
    if not token or not expected or not hmac.compare_digest(token, expected):
        raise HTTPException(status_code=401, detail="invalid_service_token")


class UserCredentialsPayload(BaseModel):
    """Body for saving per-user Jira credentials."""

    jiraBaseUrl: str = Field(min_length=1)
    personalAccessToken: str = Field(default="")
    validateJira: bool = Field(default=True)


@router.get("/runtime-config")
async def get_jira_mcp_gateway_runtime_config(
    service_token: str = Header(default="", alias="X-MOVO-Service-Token"),
) -> dict:
    """Return enabled tenant configs for the gateway router."""
    _require_service(service_token)
    return await list_runtime_tenant_configs()


@router.get("/effective-config")
async def get_effective_jira_config(
    main_id: str = Query(..., alias="mainId"),
    user_id: str = Query("", alias="userId"),
    service_token: str = Header(default="", alias="X-MOVO-Service-Token"),
) -> dict[str, Any]:
    """Return merged Jira credentials for one tenant user (gateway hot path)."""
    _require_service(service_token)
    try:
        return await resolve_effective_jira_config(main_id, user_id or "__default__")
    except JiraMcpConfigError as exc:
        raise HTTPException(status_code=503, detail={"code": exc.code, "message": str(exc)}) from exc


@router.get("/user-credentials")
async def read_user_jira_credentials(
    main_id: str = Query(..., alias="mainId"),
    user_id: str = Query(..., alias="userId"),
    service_token: str = Header(default="", alias="X-MOVO-Service-Token"),
) -> dict[str, Any]:
    """Return public view of a user's Jira binding."""
    _require_service(service_token)
    return await get_user_credentials_public(main_id=main_id, user_id=user_id)


@router.put("/user-credentials")
async def write_user_jira_credentials(
    payload: UserCredentialsPayload,
    main_id: str = Query(..., alias="mainId"),
    user_id: str = Query(..., alias="userId"),
    service_token: str = Header(default="", alias="X-MOVO-Service-Token"),
) -> dict[str, Any]:
    """Create or update a user's Jira site URL and API token."""
    _require_service(service_token)
    try:
        return await save_user_credentials(
            main_id=main_id,
            user_id=user_id,
            jira_base_url=payload.jiraBaseUrl,
            personal_access_token=payload.personalAccessToken,
            validate_jira=payload.validateJira,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.delete("/user-credentials")
async def remove_user_jira_credentials(
    main_id: str = Query(..., alias="mainId"),
    user_id: str = Query(..., alias="userId"),
    service_token: str = Header(default="", alias="X-MOVO-Service-Token"),
) -> dict[str, Any]:
    """Remove a user's Jira binding."""
    _require_service(service_token)
    try:
        return await delete_user_credentials(main_id=main_id, user_id=user_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
