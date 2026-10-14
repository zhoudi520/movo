from __future__ import annotations

from typing import Any

from bson import ObjectId

from app.repositories.directory_repository import DEPARTMENT_COLLECTION, USER_ORG_REL_COLLECTION


async def department_user_ids(db: Any, main_id: str, department_id: str) -> list[str]:
    """Resolve direct and descendant department members within one tenant."""
    department_id = str(department_id or "").strip()
    if not department_id:
        return []
    department_key = ObjectId(department_id) if ObjectId.is_valid(department_id) else department_id
    departments = await db[DEPARTMENT_COLLECTION].find(
        {"main_id": main_id, "$or": [{"_id": department_key}, {"path_ids": department_id}]},
        {"_id": 1},
    ).to_list(length=50000)
    ids = [str(row["_id"]) for row in departments]
    if not ids:
        return []
    result = await db[USER_ORG_REL_COLLECTION].distinct(
        "user_id", {"main_id": main_id, "org_id": {"$in": ids}}
    )
    return [str(value) for value in result if str(value or "").strip()]
