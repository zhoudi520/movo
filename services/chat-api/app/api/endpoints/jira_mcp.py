"""End-user API for per-user Jira MCP credentials."""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from app.api.principal import ApiPrincipal, require_end_user_principal
from app.services.jira_mcp_user_client import jira_mcp_user_client

router = APIRouter(dependencies=[Depends(require_end_user_principal)])


class ApiResponse(BaseModel):
    code: int = 0
    message: Optional[str] = None
    data: Optional[object] = None


class JiraMcpUserSavePayload(BaseModel):
    jiraBaseUrl: str = Field(min_length=1)
    personalAccessToken: str = Field(default="")
    validateJira: bool = Field(default=True)


@router.get("/jira-mcp/my", response_model=ApiResponse)
async def get_my_jira_mcp(principal: ApiPrincipal = Depends(require_end_user_principal)) -> ApiResponse:
    """Return the current user's Jira MCP binding (masked)."""
    try:
        data = await jira_mcp_user_client.get_credentials(main_id=principal.main_id, user_id=principal.user_id)
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
    return ApiResponse(data=data)


@router.put("/jira-mcp/my", response_model=ApiResponse)
async def save_my_jira_mcp(
    payload: JiraMcpUserSavePayload,
    principal: ApiPrincipal = Depends(require_end_user_principal),
) -> ApiResponse:
    """Save the current user's Jira site URL and API token."""
    try:
        data = await jira_mcp_user_client.save_credentials(
            main_id=principal.main_id,
            user_id=principal.user_id,
            jira_base_url=payload.jiraBaseUrl,
            personal_access_token=payload.personalAccessToken,
            validate_jira=payload.validateJira,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
    return ApiResponse(data=data)


@router.delete("/jira-mcp/my", response_model=ApiResponse)
async def delete_my_jira_mcp(principal: ApiPrincipal = Depends(require_end_user_principal)) -> ApiResponse:
    """Clear the current user's Jira binding (tenant default applies)."""
    try:
        data = await jira_mcp_user_client.delete_credentials(main_id=principal.main_id, user_id=principal.user_id)
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
    return ApiResponse(data=data)
