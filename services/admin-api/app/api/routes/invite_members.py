from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException, Query

from app.api.deps import get_current_admin_user
from app.api.time_utils import utc_iso
from app.core.db import get_db
from app.repositories.directory_repository import USER_COLLECTION, USER_INVITE_ACCEPTANCE_COLLECTION, USER_INVITE_COLLECTION

router = APIRouter()


@router.get("/invites/{invite_id}/members")
async def list_invite_members(
    invite_id: str,
    page: int = Query(1, ge=1),
    pageSize: int = Query(25, ge=1, le=100),
    current_user: dict = Depends(get_current_admin_user),
) -> dict:
    if not ObjectId.is_valid(invite_id):
        raise HTTPException(status_code=400, detail="邀请ID无效")
    db = get_db()
    main_id = str(current_user.get("main_id", "default"))
    invite = await db[USER_INVITE_COLLECTION].find_one(
        {"_id": ObjectId(invite_id), "main_id": main_id, "purpose": "register", "user_id": None}
    )
    if invite is None:
        raise HTTPException(status_code=404, detail="邀请不存在")

    query = {"main_id": main_id, "invite_id": invite_id}
    collection = db[USER_INVITE_ACCEPTANCE_COLLECTION]
    total = await collection.count_documents(query)
    accepted = await collection.find(query).sort("accepted_at", -1).skip((page - 1) * pageSize).limit(pageSize).to_list(length=pageSize)
    ids = [ObjectId(row["user_id"]) for row in accepted if ObjectId.is_valid(row.get("user_id", ""))]
    users = await db[USER_COLLECTION].find({"main_id": main_id, "_id": {"$in": ids}}).to_list(length=pageSize) if ids else []
    user_map = {str(user["_id"]): user for user in users}
    return {
        "items": [
            {
                "userId": row["user_id"],
                "name": user_map.get(row["user_id"], {}).get("name", ""),
                "loginName": user_map.get(row["user_id"], {}).get("login_name", ""),
                "email": user_map.get(row["user_id"], {}).get("email", ""),
                "status": user_map.get(row["user_id"], {}).get("status", "deleted"),
                "joinedAt": utc_iso(row.get("accepted_at")),
            }
            for row in accepted
        ],
        "total": total,
        "unattributedCount": max(0, int(invite.get("accepted_count") or 0) - total),
    }
