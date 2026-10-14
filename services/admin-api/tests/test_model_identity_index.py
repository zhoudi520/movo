"""The group dimension must be part of the persisted model identity."""

from __future__ import annotations

import asyncio

from app.repositories.model_identity_index import GROUP_INDEX, OLD_INDEX, ensure_model_identity_index


class FakeCollection:
    def __init__(self, *, old_index: bool) -> None:
        self.indexes = {OLD_INDEX: {}} if old_index else {GROUP_INDEX: {}}
        self.calls: list[tuple] = []

    async def update_many(self, selector, update):
        self.calls.append(("backfill", selector, update))

    async def create_index(self, keys, **options):
        self.calls.append(("create", keys, options))
        self.indexes[options["name"]] = {}

    async def index_information(self):
        self.calls.append(("inspect",))
        return self.indexes

    async def drop_index(self, name):
        self.calls.append(("drop", name))
        del self.indexes[name]


def test_migrates_identity_index_without_losing_uniqueness() -> None:
    collection = FakeCollection(old_index=True)
    asyncio.run(ensure_model_identity_index(collection))

    assert [call[0] for call in collection.calls] == ["backfill", "create", "inspect", "drop"]
    assert collection.calls[0][1:] == ({"group_id": None}, {"$set": {"group_id": ""}})
    assert collection.calls[1][1] == [
        ("main_id", 1), ("provider_id", 1), ("group_id", 1), ("model_name", 1), ("display_name", 1)
    ]
    assert collection.calls[1][2] == {"unique": True, "name": GROUP_INDEX}
    assert collection.calls[3] == ("drop", OLD_INDEX)


def test_identity_index_migration_is_repeatable() -> None:
    collection = FakeCollection(old_index=False)
    asyncio.run(ensure_model_identity_index(collection))
    assert not any(call[0] == "drop" for call in collection.calls)
    assert GROUP_INDEX in collection.indexes
