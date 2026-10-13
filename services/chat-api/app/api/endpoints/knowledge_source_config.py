from __future__ import annotations

from fastapi import APIRouter, Header

from app.api.endpoints.auth import _resolve_session_user
from app.enterprise_capabilities.knowledge_source.config import get_knowledge_source

router = APIRouter()


@router.get("/knowledge/source/current")
async def current_knowledge_source(authorization: str | None = Header(default=None)) -> dict[str, str]:
    resolved = await _resolve_session_user(authorization)
    main_id = str(resolved.get("main_id") or resolved["user"].get("main_id") or "default")
    source = await get_knowledge_source(main_id)
    return {"mode": str(source.get("mode") or "movo"), "displayName": str(source.get("displayName") or "MOVO 知识库")}
