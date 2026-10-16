"""Tests for Jira MCP gateway settings and internal runtime config."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.routes import jira_mcp_gateway_internal
from app.services import jira_mcp_gateway as gateway_service
from app.services import jira_mcp_user_credentials as user_creds_service
from app.services.jira_mcp_user_credentials import JiraMcpConfigError


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
    assert second["personalAccessToken"] == "user@example.com:token"


def test_serialize_public_includes_plain_jira_token(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        gateway_service,
        "_decrypt_field",
        lambda doc, field: "admin@corp.com:ATATT-plain" if field == "personal_access_token_encrypted" else "",
    )
    payload = gateway_service.serialize_public(
        {
            "main_id": "t1",
            "enabled": True,
            "jira_base_url": "https://j.atlassian.net",
            "personal_access_token_encrypted": "enc",
        }
    )
    assert payload["personalAccessToken"] == "admin@corp.com:ATATT-plain"
    assert "personalAccessTokenMasked" not in payload


def test_resolve_effective_prefers_user(monkeypatch: pytest.MonkeyPatch) -> None:
    tenant_doc = {
        "main_id": "t1",
        "enabled": True,
        "config_version": 2,
        "jira_base_url": "https://org.atlassian.net",
        "personal_access_token_encrypted": "enc-org",
        "gateway_key_encrypted": "enc-gw",
    }
    user_doc = {
        "main_id": "t1",
        "user_id": "u1",
        "config_version": 1,
        "jira_base_url": "https://user.atlassian.net",
        "personal_access_token_encrypted": "enc-user",
    }

    async def _load_tenant(main_id: str) -> dict:
        return tenant_doc if main_id == "t1" else None

    async def _load_user(main_id: str, user_id: str) -> dict | None:
        if main_id == "t1" and user_id == "u1":
            return user_doc
        return None

    def _decrypt(doc: dict, field: str) -> str:
        val = str(doc.get(field) or "")
        if field == "personal_access_token_encrypted":
            if val == "enc-user":
                return "user@x.com:usertok"
            if val == "enc-org":
                return "org@x.com:orgtok"
        if field == "gateway_key_encrypted" and val == "enc-gw":
            return "gw-key"
        return ""

    monkeypatch.setattr(user_creds_service, "load_settings_doc", _load_tenant)
    monkeypatch.setattr(user_creds_service, "load_user_doc", _load_user)
    monkeypatch.setattr(user_creds_service, "_decrypt_field", _decrypt)

    import asyncio

    result = asyncio.run(user_creds_service.resolve_effective_jira_config("t1", "u1"))
    assert result["jiraBaseUrl"] == "https://user.atlassian.net"
    assert result["personalAccessToken"] == "user@x.com:usertok"
    assert result["credentialSource"] == "user"
    assert result["configVersion"] == 2 * 1_000_000 + 1


def test_resolve_effective_falls_back_to_tenant(monkeypatch: pytest.MonkeyPatch) -> None:
    tenant_doc = {
        "main_id": "t1",
        "enabled": True,
        "config_version": 1,
        "jira_base_url": "https://org.atlassian.net",
        "personal_access_token_encrypted": "enc-org",
        "gateway_key_encrypted": "enc-gw",
    }

    async def _load_tenant(main_id: str) -> dict:
        return tenant_doc

    async def _load_user(_main_id: str, _user_id: str) -> None:
        return None

    def _decrypt(doc: dict, field: str) -> str:
        if field == "personal_access_token_encrypted":
            return "org@x.com:orgtok"
        if field == "gateway_key_encrypted":
            return "gw-key"
        return ""

    monkeypatch.setattr(user_creds_service, "load_settings_doc", _load_tenant)
    monkeypatch.setattr(user_creds_service, "load_user_doc", _load_user)
    monkeypatch.setattr(user_creds_service, "_decrypt_field", _decrypt)

    import asyncio

    result = asyncio.run(user_creds_service.resolve_effective_jira_config("t1", "u2"))
    assert result["credentialSource"] == "tenant_default"


def test_resolve_effective_tenant_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _load_tenant(_main_id: str) -> dict:
        return {"enabled": False}

    monkeypatch.setattr(user_creds_service, "load_settings_doc", _load_tenant)

    import asyncio

    with pytest.raises(JiraMcpConfigError) as exc:
        asyncio.run(user_creds_service.resolve_effective_jira_config("t1", "u1"))
    assert exc.value.code == "tenant_disabled"
