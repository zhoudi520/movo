"""Model groups share connections while members keep independent identities."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest
from bson import ObjectId
from fastapi import HTTPException

from app.api.routes import model_groups, models


def test_grouped_model_create_stores_no_duplicate_credential(monkeypatch) -> None:
    provider_id = ObjectId()
    group_id = ObjectId()
    model_id = ObjectId()
    group = {
        "_id": group_id, "main_id": "tenant", "provider_id": provider_id,
        "status": "active", "base_url": "https://shared.example/v1",
        "api_key_masked": "sk-****", "api_version": "",
    }
    saved = {}

    async def provider_lookup(_id):
        return {"_id": provider_id, "name": "OpenAI", "provider_type": "openai_compatible", "status": "active"}

    async def create(payload):
        saved.update(payload)
        return model_id

    async def find(_id, _tenant):
        return {"_id": model_id, "provider_id": provider_id, **saved}

    monkeypatch.setattr(models, "find_provider_by_id", provider_lookup)
    monkeypatch.setattr(models, "find_group", lambda _id, _tenant: asyncio.sleep(0, result=group))
    monkeypatch.setattr(models, "create_instance", create)
    monkeypatch.setattr(models, "find_instance_by_id", find)
    monkeypatch.setattr(models, "list_providers", lambda: asyncio.sleep(0, result=[{"_id": provider_id, "name": "OpenAI", "provider_type": "openai_compatible"}]))
    monkeypatch.setattr(models, "get_admin_product_extension", lambda: SimpleNamespace(model_created=[]))

    result = asyncio.run(models.post_model_instance(
        models.ModelInstancePayload(providerId=str(provider_id), groupId=str(group_id),
                                    displayName="Text", modelName="gpt-example", apiKey="unexpected"),
        {"main_id": "tenant"},
    ))

    assert saved["group_id"] == str(group_id)
    assert saved["base_url"] == ""
    assert saved["api_key"] == ""
    assert result["baseUrl"] == group["base_url"]
    assert result["apiKeyMasked"] == group["api_key_masked"]


def test_available_models_skip_disabled_group(monkeypatch) -> None:
    provider_id = ObjectId()
    group_id = ObjectId()
    model_id = ObjectId()
    monkeypatch.setattr(models, "list_providers", lambda: asyncio.sleep(0, result=[{"_id": provider_id}]))
    monkeypatch.setattr(models, "list_instances", lambda _tenant: asyncio.sleep(0, result=[{
        "_id": model_id, "provider_id": provider_id, "group_id": str(group_id),
        "status": "active", "capabilities": ["chat"], "model_name": "gpt-example",
    }]))
    monkeypatch.setattr(models, "list_groups", lambda _tenant: asyncio.sleep(0, result=[{
        "_id": group_id, "status": "disabled",
    }]))

    result = asyncio.run(models.get_available_chat_models(current_user={"main_id": "tenant"}))
    assert result == []


def test_azure_group_requires_api_version(monkeypatch) -> None:
    monkeypatch.setattr(model_groups, "find_provider_by_id", lambda _id: asyncio.sleep(0, result={
        "status": "active", "provider_type": "azure_openai",
    }))
    payload = model_groups.ModelGroupPayload(name="Azure", providerId=str(ObjectId()),
                                            baseUrl="https://example.azure.com", apiKey="secret")
    with pytest.raises(HTTPException) as exc:
        asyncio.run(model_groups.post_group(payload, {"main_id": "tenant"}))
    assert exc.value.status_code == 400
    assert exc.value.detail == "model_group_api_version_required"
