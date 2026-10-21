from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import httpx

from app.enterprise_capabilities.research.progressive import deepseek_provider as module
from app.enterprise_capabilities.research.progressive.provider_router import ProviderRouter
from app.services import search_provider_config


def test_search_uses_deepseek_json_api_and_normalizes_citations() -> None:
    asyncio.run(_verify_search())


async def _verify_search() -> None:
    requests = []

    def respond(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"results": [
            {"title": "Example", "url": "https://example.com/a", "snippet": "Short", "summary": "Long", "rerank_score": 2.4},
            {"title": "No URL", "snippet": "Skip"},
        ]})

    client = httpx.AsyncClient(transport=httpx.MockTransport(respond))
    with patch.object(module.httpx, "AsyncClient", return_value=client):
        rows = await module.DeepSeekProvider(api_key="example-secret").search("MOVO", max_results=3)
    assert len(rows) == 1
    assert rows[0].provider == "deepseek"
    assert rows[0].snippet == "Long"
    assert rows[0].score == 2.4
    assert requests[0].url == module.DEFAULT_ENDPOINT
    assert requests[0].headers["authorization"] == "Bearer example-secret"
    assert json.loads(requests[0].content) == {"query": "MOVO", "count": 3, "need_content": False}


def test_admin_default_uses_only_selected_provider_and_disabling_does_not_use_host_key() -> None:
    asyncio.run(_verify_routing())


def test_single_enabled_provider_is_used_without_explicit_default() -> None:
    asyncio.run(_verify_legacy_single_provider())


async def _verify_legacy_single_provider() -> None:
    class Cursor:
        async def to_list(self, *, length):
            assert length == len(search_provider_config.SUPPORTED_PROVIDERS)
            return [{"provider": "deepseek", "config": {"api_key_encrypted": "cipher", "endpoint": module.DEFAULT_ENDPOINT}}]

    class Collection:
        async def find_one(self, query, *args, **kwargs):
            return None

        def find(self, query):
            assert query["main_id"] == "tenant"
            assert query["enabled"] is True
            return Cursor()

    class Database:
        def __getitem__(self, name):
            assert name == search_provider_config.COLLECTION
            return Collection()

    with patch.object(search_provider_config, "get_db", return_value=Database()), patch.object(
        search_provider_config, "decrypt_secret", return_value="tenant-key"
    ):
        config = await search_provider_config.resolve_default_external_search_provider("tenant")
    assert config is not None
    assert config["provider"] == "deepseek"


def test_multiple_enabled_providers_use_default_then_priority_and_ignore_missing_keys() -> None:
    asyncio.run(_verify_multiple_provider_selection())


async def _verify_multiple_provider_selection() -> None:
    docs = [
        {"provider": "tavily", "enabled": True, "is_default": False, "priority": 10, "config": {"api_key_encrypted": "tavily-key"}},
        {"provider": "deepseek", "enabled": True, "is_default": False, "priority": 5, "config": {"api_key_encrypted": "deepseek-key"}},
        {"provider": "serper", "enabled": True, "is_default": False, "priority": 20, "config": {}},
    ]

    class Cursor:
        async def to_list(self, *, length):
            return [doc for doc in docs if doc["enabled"]]

    class Collection:
        async def find_one(self, query, *args, **kwargs):
            return {"_id": "configured"} if args else None

        def find(self, query):
            return Cursor()

    class Database:
        def __getitem__(self, name):
            return Collection()

    with patch.object(search_provider_config, "get_db", return_value=Database()), patch.object(
        search_provider_config, "decrypt_secret", side_effect=lambda value: value
    ):
        selected = await search_provider_config.resolve_default_external_search_provider("tenant")
        assert selected["provider"] == "deepseek"
        docs[0]["is_default"] = True
        selected = await search_provider_config.resolve_default_external_search_provider("tenant")
        assert selected["provider"] == "tavily"
        docs[0]["enabled"] = docs[1]["enabled"] = False
        assert await search_provider_config.resolve_default_external_search_provider("tenant") is None


async def _verify_routing() -> None:
    configured = {"provider": "deepseek", "api_key": "tenant-key", "endpoint": module.DEFAULT_ENDPOINT}
    settings = SimpleNamespace(TAVILY_API_KEY="host-key", SERPER_API_KEY="", SERPAPI_API_KEY="", SERPAPI_ENABLED=False)
    with (
        patch("app.enterprise_capabilities.research.progressive.provider_router.get_settings", return_value=settings),
        patch("app.enterprise_capabilities.research.progressive.provider_router.get_request_context", return_value={"main_id": "tenant"}),
        patch("app.enterprise_capabilities.research.progressive.provider_router.resolve_default_external_search_provider", new=AsyncMock(return_value=configured)),
        patch("app.enterprise_capabilities.research.progressive.provider_router.has_saved_external_search_config", new=AsyncMock(return_value=True)),
    ):
        providers = await ProviderRouter().available_providers()
    assert [provider.name for provider in providers] == ["deepseek"]

    with (
        patch("app.enterprise_capabilities.research.progressive.provider_router.get_settings", return_value=settings),
        patch("app.enterprise_capabilities.research.progressive.provider_router.get_request_context", return_value={"main_id": "tenant"}),
        patch("app.enterprise_capabilities.research.progressive.provider_router.resolve_default_external_search_provider", new=AsyncMock(return_value=None)),
        patch("app.enterprise_capabilities.research.progressive.provider_router.has_saved_external_search_config", new=AsyncMock(return_value=True)),
    ):
        providers = await ProviderRouter().available_providers()
    assert providers == []
