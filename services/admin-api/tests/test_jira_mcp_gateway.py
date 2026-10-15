"""Tests for Jira MCP gateway settings and internal runtime config."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.routes import jira_mcp_gateway_internal
from app.services import jira_mcp_gateway as gateway_service


@pytest.fixture
def internal_client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    """Build a minimal app exposing the internal gateway route."""
    monkeypatch.setenv("ADMIN_BACKEND_SERVICE_TOKEN", "test-service-token")
    from app.core.config import settings

    settings.backend_service_token = "test-service-token"
    app = FastAPI()
    app.include_router(jira_mcp_gateway_internal.router, prefix="/api/internal/jira-mcp-gateway")
    return TestClient(app)


def test_internal_runtime_config_requires_service_token(internal_client: TestClient) -> None:
    response = internal_client.get("/api/internal/jira-mcp-gateway/runtime-config")
    assert response.status_code == 401


def test_internal_runtime_config_ok(internal_client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    async def _fake_list() -> dict:
        return {"globalVersion": 3, "tenants": []}

    monkeypatch.setattr(jira_mcp_gateway_internal, "list_runtime_tenant_configs", _fake_list)
    response = internal_client.get(
        "/api/internal/jira-mcp-gateway/runtime-config",
        headers={"X-MOVO-Service-Token": "test-service-token"},
    )
    assert response.status_code == 200
    assert response.json() == {"globalVersion": 3, "tenants": []}


def test_save_settings_increments_config_version(monkeypatch: pytest.MonkeyPatch) -> None:
    store: dict = {}

    class FakeCollection:
        async def find_one(self, query: dict) -> dict | None:
            main_id = query.get("main_id")
            if main_id is None:
                return None
            doc = store.get(main_id)
            if doc is None:
                return None
            return dict(doc)

        async def update_one(self, query: dict, update: dict, upsert: bool = False) -> None:
            main_id = query.get("main_id")
            if main_id is None:
                return
            current = store.get(main_id, {})
            patch = update.get("$set", {})
            current.update(patch)
            store[main_id] = current

        async def insert_one(self, doc: dict) -> None:
            return None

        async def create_index(self, *_args, **_kwargs) -> None:
            return None

    class FakeDb:
        gateway = FakeCollection()
        external_tools = FakeCollection()

        def __getitem__(self, name: str) -> FakeCollection:
            assert name == gateway_service.COLLECTION
            return self.gateway

    monkeypatch.setattr(gateway_service, "get_db", lambda: FakeDb())

    async def _sync(_db: object, **_kwargs: object) -> str:
        return "tool-1"

    monkeypatch.setattr(gateway_service, "_sync_linked_external_tool", _sync)

    import asyncio

    first = asyncio.run(
        gateway_service.save_settings(
            main_id="tenant-a",
            jira_base_url="https://example.atlassian.net",
            personal_access_token="user@example.com:token",
            gateway_key="gateway-key-a",
            preset="docker_internal",
            enabled=True,
        )
    )
    second = asyncio.run(
        gateway_service.save_settings(
            main_id="tenant-a",
            jira_base_url="https://example.atlassian.net",
            personal_access_token="",
            gateway_key="",
            preset="docker_internal",
            enabled=True,
        )
    )
    assert first["configVersion"] == 1
    assert second["configVersion"] == 2
