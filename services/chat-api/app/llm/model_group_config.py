"""Resolve a model instance's optional shared connection."""

from __future__ import annotations

from typing import Any

from bson import ObjectId

from app.core.db import get_db


GROUP_COLLECTION = "admin_model_groups"


async def load_model_group(instance: dict[str, Any]) -> dict[str, Any] | None:
    group_id = str(instance.get("group_id") or "")
    if not group_id:
        return None
    if not ObjectId.is_valid(group_id):
        raise ValueError("model group id is invalid")
    group = await get_db()[GROUP_COLLECTION].find_one({
        "_id": ObjectId(group_id), "main_id": instance.get("main_id"),
    })
    if group is None or str(group.get("provider_id")) != str(instance.get("provider_id")):
        raise ValueError("model group is unavailable")
    return group


async def active_group_ids(main_id: str, group_ids: list[str]) -> set[str]:
    identifiers = [ObjectId(item) for item in group_ids if ObjectId.is_valid(item)]
    if not identifiers:
        return set()
    cursor = get_db()[GROUP_COLLECTION].find({
        "_id": {"$in": identifiers}, "main_id": main_id, "status": "active",
    }, {"_id": 1})
    return {str(item["_id"]) async for item in cursor}
