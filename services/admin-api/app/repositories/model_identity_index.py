"""Migrate model identity uniqueness from provider scope to connection group scope."""

from __future__ import annotations

from typing import Any


OLD_INDEX = "model_instance_identity_unique"
GROUP_INDEX = "model_instance_group_identity_unique"


async def ensure_model_identity_index(collection: Any) -> None:
    # Older standalone models did not store group_id. Give them the same
    # identity value as newly created standalone models before indexing.
    await collection.update_many({"group_id": None}, {"$set": {"group_id": ""}})
    await collection.create_index(
        [("main_id", 1), ("provider_id", 1), ("group_id", 1), ("model_name", 1), ("display_name", 1)],
        unique=True,
        name=GROUP_INDEX,
    )
    # Keep the old constraint until the replacement has been created.
    if OLD_INDEX in await collection.index_information():
        await collection.drop_index(OLD_INDEX)
