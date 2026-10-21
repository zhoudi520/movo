from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

from app.dsh_runtime.profile.search_availability import search_available
from app.dsh_runtime.profile.tools import ToolProfileCompiler
from app.enterprise_capabilities.runtime import InternalCapabilityCatalog


class EmptyCatalog:
    async def list_enabled(self, tenant_id: str, user_id: str):
        return []


def test_public_search_tools_follow_runtime_provider_availability() -> None:
    async def compile_tools(available: bool):
        return await ToolProfileCompiler(
            EmptyCatalog(), InternalCapabilityCatalog(),
            search_availability=lambda tenant_id: asyncio.sleep(0, result=available),
        ).compile(tenant_id="tenant-a", user_id="user-a")

    disabled = {tool.name for tool in asyncio.run(compile_tools(False))}
    enabled = {tool.name for tool in asyncio.run(compile_tools(True))}
    assert {"external_search", "progressive_research"}.isdisjoint(disabled)
    assert {"external_search", "progressive_research"} <= enabled
    assert "knowledge_search" in disabled


def test_availability_uses_same_provider_router_and_explicit_tenant() -> None:
    with patch(
        "app.dsh_runtime.profile.search_availability.ProviderRouter.available_providers",
        new=AsyncMock(return_value=[object()]),
    ) as available:
        assert asyncio.run(search_available("tenant-a")) is True
        available.assert_awaited_once_with(main_id="tenant-a")
