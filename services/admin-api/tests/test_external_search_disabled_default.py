from __future__ import annotations

import asyncio
from unittest.mock import patch

import pytest
from fastapi import HTTPException

from app.api.routes import external_search


class SearchConfigs:
    def __init__(self) -> None:
        self.doc = {
            "_id": "provider-1", "main_id": "tenant-1", "provider": "tavily",
            "enabled": True, "is_default": True, "config": {"api_key_encrypted": "encrypted", "api_key_masked": "***"},
        }

    async def find_one(self, query):
        if any(self.doc.get(key) != value for key, value in query.items()):
            return None
        return dict(self.doc)

    def find(self, query):
        assert query == {"main_id": "tenant-1"}
        return self

    async def to_list(self, *, length):
        assert length >= 1
        return [dict(self.doc)]

    async def update_one(self, query, update, *, upsert=False):
        # Motor/MongoDB rejects conflicting update paths even for an existing doc.
        assert not (set(update.get("$set", {})) & set(update.get("$setOnInsert", {})))
        self.doc.update(update.get("$set", {}))

    async def update_many(self, query, update):
        self.doc.update(update.get("$set", {}))


class Database:
    def __init__(self) -> None:
        self.external_search_configs = SearchConfigs()

    def __getitem__(self, key):
        assert key == "external_search_configs"
        return self.external_search_configs


def test_disabling_default_stays_disabled_and_cannot_be_set_default_again() -> None:
    asyncio.run(_verify_disabled_default())


def test_first_enabled_provider_becomes_default() -> None:
    asyncio.run(_verify_first_enabled_default())


def test_provider_list_shows_priority_selection_when_no_explicit_default() -> None:
    docs = [
        {"provider": "tavily", "enabled": True, "priority": 10, "config": {"api_key_encrypted": "t"}},
        {"provider": "deepseek", "enabled": True, "priority": 5, "config": {"api_key_encrypted": "d"}},
    ]
    assert external_search._effective_default_provider(docs) == "deepseek"
    docs[0]["is_default"] = True
    assert external_search._effective_default_provider(docs) == "tavily"
    docs[0]["enabled"] = docs[1]["enabled"] = False
    assert external_search._effective_default_provider(docs) == ""


async def _verify_first_enabled_default() -> None:
    db = Database()
    db.external_search_configs.doc.update(provider="deepseek", enabled=True, is_default=False)
    user = {"main_id": "tenant-1", "username": "admin"}
    with patch.object(external_search, "get_db", return_value=db):
        saved = await external_search.save_external_search_provider(
            "deepseek", external_search.SearchProviderPayload(enabled=True), user,
        )
        assert saved["enabled"] is True
        assert saved["isDefault"] is True
        assert db.external_search_configs.doc["is_default"] is True


async def _verify_disabled_default() -> None:
    db = Database()
    user = {"main_id": "tenant-1", "username": "admin"}
    with patch.object(external_search, "get_db", return_value=db):
        saved = await external_search.save_external_search_provider(
            "tavily", external_search.SearchProviderPayload(enabled=False), user,
        )
        assert saved["enabled"] is False
        assert saved["isDefault"] is False
        assert db.external_search_configs.doc["enabled"] is False
        assert db.external_search_configs.doc["is_default"] is False

        # The list endpoint is what the settings page reads again after reload.
        rows = await external_search.list_external_search_providers(user)
        tavily = next(row for row in rows if row["provider"] == "tavily")
        assert tavily["enabled"] is False
        assert tavily["isDefault"] is False

        with pytest.raises(HTTPException) as error:
            await external_search.set_default_external_search_provider("tavily", user)
        assert error.value.status_code == 400
        assert db.external_search_configs.doc["enabled"] is False
