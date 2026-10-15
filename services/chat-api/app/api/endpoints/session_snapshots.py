"""Authenticated, tenant-scoped read-only snapshots of desktop Code history."""

from __future__ import annotations

import datetime

from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from app.api.principal import ApiPrincipal, require_end_user_principal
from app.core.db import get_db
from app.core.tenant import add_main_scope
from app.dsh_runtime.bindings.repository import KernelBindingRepository
from app.services.session_identity_projection import resolve_author_projections
from app.services.session_sharing.links import portal_link
from app.services.session_sharing.service import SessionShareError, create_token, hash_token
from app.services.session_sharing.snapshot import snapshot_active, snapshot_messages

router = APIRouter(dependencies=[Depends(require_end_user_principal)])
COLLECTION = "session_history_snapshots"


class SnapshotRequest(BaseModel):
    expires_in_days: int = Field(default=30, ge=1, le=365, alias="expiresInDays")


def _now() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc)


@router.post("/sessions/{session_id}/snapshot-share")
async def create_snapshot_share(
    session_id: str,
    payload: SnapshotRequest,
    request: Request,
    principal: ApiPrincipal = Depends(require_end_user_principal),
) -> dict:
    if not ObjectId.is_valid(session_id):
        raise HTTPException(status_code=404, detail="session_not_found")
    db = get_db()
    session = await db.chat_sessions.find_one(add_main_scope({"_id": ObjectId(session_id), "user_id": principal.user_id}, principal.main_id))
    if session is None:
        raise HTTPException(status_code=404, detail="session_not_found")
    binding = await KernelBindingRepository(db).current(session_id, tenant_id=principal.main_id, user_id=principal.user_id)
    if not binding or str(binding.get("execution_location")) != "desktop" or str(binding.get("preset_id")) != "code":
        raise HTTPException(status_code=409, detail="snapshot_requires_desktop_code")
    token = create_token()
    link = portal_link(request, token, snapshot=True)
    rows = await db.chat_messages.find(add_main_scope({"session_id": ObjectId(session_id)}, principal.main_id), {
        "role": 1, "content": 1, "created_at": 1, "message_type": 1, "user_id": 1,
    }).sort([("seq", 1), ("created_at", 1)]).limit(5001).to_list(length=5001)
    if len(rows) > 5000:
        raise HTTPException(status_code=413, detail="snapshot_too_large")
    owner_user_id = str(session.get("user_id") or "")
    authors = await resolve_author_projections(
        db,
        tenant_id=principal.main_id,
        user_ids=[str(row.get("user_id") or owner_user_id) for row in rows if row.get("role") == "user"],
    )
    messages = snapshot_messages(rows, authors=authors, owner_user_id=owner_user_id)
    if not messages:
        raise HTTPException(status_code=409, detail="snapshot_empty")
    if sum(len(item["content"].encode("utf-8")) for item in messages) > 8_000_000:
        raise HTTPException(status_code=413, detail="snapshot_too_large")
    now = _now()
    result = await db[COLLECTION].insert_one({
        "main_id": principal.main_id,
        "owner_user_id": principal.user_id,
        "session_id": session_id,
        "token_hash": hash_token(token),
        "title": str(session.get("title") or ""),
        "messages": messages,
        "created_at": now,
        "expires_at": now + datetime.timedelta(days=payload.expires_in_days),
        "revoked_at": None,
    })
    return {"code": 0, "data": {"id": str(result.inserted_id), "url": link, "expires_at": (now + datetime.timedelta(days=payload.expires_in_days)).isoformat()}}


@router.get("/session-snapshots/{token}")
async def read_snapshot_share(token: str, principal: ApiPrincipal = Depends(require_end_user_principal)) -> dict:
    try:
        token_hash = hash_token(token)
    except SessionShareError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail()) from exc
    doc = await get_db()[COLLECTION].find_one(add_main_scope({"token_hash": token_hash}, principal.main_id))
    if doc is None:
        raise HTTPException(status_code=404, detail="snapshot_not_found")
    if not snapshot_active(doc, _now()):
        raise HTTPException(status_code=410, detail="snapshot_inactive")
    return {"code": 0, "data": {"title": doc.get("title") or "", "messages": doc.get("messages") or [], "created_at": doc["created_at"], "expires_at": doc["expires_at"]}}


@router.delete("/session-snapshots/{snapshot_id}")
async def revoke_snapshot_share(snapshot_id: str, principal: ApiPrincipal = Depends(require_end_user_principal)) -> dict:
    if not ObjectId.is_valid(snapshot_id):
        raise HTTPException(status_code=404, detail="snapshot_not_found")
    result = await get_db()[COLLECTION].update_one(add_main_scope({"_id": ObjectId(snapshot_id), "owner_user_id": principal.user_id}, principal.main_id), {"$set": {"revoked_at": _now()}})
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="snapshot_not_found")
    return {"code": 0, "data": {"revoked": True}}
