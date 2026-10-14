from datetime import datetime, timezone

from bson import ObjectId
from bson.errors import InvalidId
from fastapi import APIRouter, Depends, HTTPException, Query, Request

from app.api.deps import get_current_admin_user
from app.api.time_utils import utc_iso
from app.core.db import get_db
from app.core.config import settings
from app.repositories.directory_repository import USER_INVITE_COLLECTION
from app.services.invite_links import request_portal_origin, resolve_portal_base

router = APIRouter()


@router.get("/invites")
async def list_org_invites(
    request: Request,
    page: int = Query(1, ge=1),
    pageSize: int = Query(20, ge=1, le=100),
    departmentId: str | None = None,
    statusFilter: str | None = Query(None, pattern="^(active|expired|revoked|used)$"),
    current_user: dict = Depends(get_current_admin_user),
) -> dict:
    main_id = str(current_user.get("main_id", "default"))
    query = {"main_id": main_id, "purpose": "register", "user_id": None}
    if departmentId:
        query["default_department_id"] = departmentId
    now = datetime.now(timezone.utc)
    if statusFilter == "active":
        query.update({"status": "active", "expires_at": {"$gt": now}})
    elif statusFilter == "expired":
        query["$or"] = [{"status": "expired"}, {"status": "active", "expires_at": {"$lte": now}}]
    elif statusFilter:
        query["status"] = statusFilter
    collection = get_db()[USER_INVITE_COLLECTION]
    total = await collection.count_documents(query)
    cursor = collection.find(query).sort("created_at", -1).skip((page - 1) * pageSize).limit(pageSize)
    portal_base = resolve_portal_base(settings.user_portal_base_url, settings.public_base_url, request_portal_origin(request), str(request.base_url))
    result = []
    async for invite in cursor:
        expires_at = invite.get("expires_at")
        if expires_at and expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        state = "expired" if expires_at and expires_at <= now else invite.get("status", "active")
        result.append({
            "id": str(invite["_id"]),
            "token": invite.get("token", ""),
            "inviteUrl": f"{portal_base}/?invite_code={invite.get('token', '')}&register=1",
            "status": state,
            "createdAt": utc_iso(invite.get("created_at")),
            "expiresAt": utc_iso(invite.get("expires_at")),
            "acceptedCount": invite.get("accepted_count", 1 if invite.get("status") == "used" else 0),
            "defaultDepartmentId": invite.get("default_department_id"),
            "primaryRoleId": invite.get("primary_role_id"),
            "roleIds": invite.get("role_ids") or [],
        })
    return {"items": result, "total": total}


@router.post("/invites/{invite_id}/revoke")
async def revoke_org_invite(invite_id: str, current_user: dict = Depends(get_current_admin_user)) -> dict[str, bool]:
    try:
        oid = ObjectId(invite_id)
    except InvalidId as exc:
        raise HTTPException(status_code=400, detail="邀请ID无效") from exc
    result = await get_db()[USER_INVITE_COLLECTION].update_one(
        {"_id": oid, "main_id": str(current_user.get("main_id", "default")), "purpose": "register", "user_id": None, "status": "active"},
        {"$set": {"status": "revoked", "updated_at": datetime.now(timezone.utc)}},
    )
    if not result.matched_count:
        raise HTTPException(status_code=404, detail="邀请不存在或已失效")
    return {"success": True}
