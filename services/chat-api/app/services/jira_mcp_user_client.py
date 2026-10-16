"""Proxy per-user Jira MCP settings to admin-api internal routes."""

from __future__ import annotations

from typing import Any

import httpx

from app.core.config import get_settings


class JiraMcpUserClient:
    """HTTP client for admin-api Jira MCP user credential APIs."""

    def _headers(self) -> dict[str, str]:
        settings = get_settings()
        return {"X-MOVO-Service-Token": str(settings.ADMIN_BACKEND_SERVICE_TOKEN or "")}

    def _base_url(self) -> str:
        settings = get_settings()
        return str(settings.ADMIN_API_BASE_URL or "http://127.0.0.1:8100").rstrip("/")

    async def get_credentials(self, *, main_id: str, user_id: str) -> dict[str, Any]:
        """Fetch public view of the user's Jira binding."""
        url = f"{self._base_url()}/api/internal/jira-mcp-gateway/user-credentials"
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.get(
                url,
                params={"mainId": main_id, "userId": user_id},
                headers=self._headers(),
            )
        if response.status_code >= 400:
            raise RuntimeError(f"jira_mcp_user_get_failed:{response.status_code}:{response.text[:500]}")
        return response.json()

    async def save_credentials(
        self,
        *,
        main_id: str,
        user_id: str,
        jira_base_url: str,
        personal_access_token: str,
        validate_jira: bool = True,
    ) -> dict[str, Any]:
        """Create or update the user's Jira site URL and token."""
        url = f"{self._base_url()}/api/internal/jira-mcp-gateway/user-credentials"
        async with httpx.AsyncClient(timeout=60) as client:
            response = await client.put(
                url,
                params={"mainId": main_id, "userId": user_id},
                json={
                    "jiraBaseUrl": jira_base_url,
                    "personalAccessToken": personal_access_token,
                    "validateJira": validate_jira,
                },
                headers=self._headers(),
            )
        if response.status_code >= 400:
            detail = response.text[:500]
            if response.status_code == 400:
                raise ValueError(detail)
            raise RuntimeError(f"jira_mcp_user_save_failed:{response.status_code}:{detail}")
        return response.json()

    async def delete_credentials(self, *, main_id: str, user_id: str) -> dict[str, Any]:
        """Remove the user's Jira binding."""
        url = f"{self._base_url()}/api/internal/jira-mcp-gateway/user-credentials"
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.delete(
                url,
                params={"mainId": main_id, "userId": user_id},
                headers=self._headers(),
            )
        if response.status_code >= 400:
            raise RuntimeError(f"jira_mcp_user_delete_failed:{response.status_code}:{response.text[:500]}")
        return response.json()


jira_mcp_user_client = JiraMcpUserClient()
