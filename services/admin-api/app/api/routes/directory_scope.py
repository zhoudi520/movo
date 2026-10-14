from __future__ import annotations

import re
from typing import Any

from bson import ObjectId
from fastapi import APIRouter, Depends, Query

from app.api.deps import get_current_admin_user
from app.core.db import get_db
from app.repositories.directory_repository import DEPARTMENT_COLLECTION, USER_COLLECTION, USER_ORG_REL_COLLECTION
from app.services.directory_scope import department_user_ids

router = APIRouter()


@router.get("/scope-departments")
async def scope_departments(current_user: dict = Depends(get_current_admin_user)) -> list[dict[str, Any]]:
    main_id = str(current_user.get("main_id") or "default")
    rows = await get_db()[DEPARTMENT_COLLECTION].find(
        {"main_id": main_id}, {"name": 1, "parent_id": 1}
    ).sort("name", 1).to_list(length=50000)
    nodes = {str(row["_id"]): {"id": str(row["_id"]), "name": str(row.get("name") or ""), "children": []} for row in rows}
    roots: list[dict[str, Any]] = []
    for row in rows:
        node = nodes[str(row["_id"])]
        parent = nodes.get(str(row.get("parent_id") or ""))
        (parent["children"] if parent else roots).append(node)
    return roots


@router.get("/scope-users")
async def scope_users(
    current_user: dict = Depends(get_current_admin_user),
    departmentId: str = Query(default=""),
    keyword: str = Query(default="", max_length=100),
    page: int = Query(default=1, ge=1),
    pageSize: int = Query(default=20, ge=1, le=100),
) -> dict[str, Any]:
    main_id = str(current_user.get("main_id") or "default")
    db = get_db()
    query: dict[str, Any] = {"main_id": main_id, "status": {"$ne": "deleted"}}
    if departmentId.strip():
        ids = await department_user_ids(db, main_id, departmentId)
        query["_id"] = {"$in": [ObjectId(item) for item in ids if ObjectId.is_valid(item)]}
    if keyword.strip():
        regex = {"$regex": re.escape(keyword.strip()), "$options": "i"}
        query["$or"] = [{field: regex} for field in ("name", "login_name", "email")]
    total = await db[USER_COLLECTION].count_documents(query)
    rows = await db[USER_COLLECTION].find(
        query, {"name": 1, "login_name": 1, "email": 1}
    ).sort([("name", 1), ("_id", 1)]).skip((page - 1) * pageSize).limit(pageSize).to_list(length=pageSize)
    return {
        "items": [{"id": str(row["_id"]), "name": str(row.get("name") or row.get("login_name") or ""), "loginName": str(row.get("login_name") or ""), "email": str(row.get("email") or "")} for row in rows],
        "total": total,
        "page": page,
        "pageSize": pageSize,
    }
