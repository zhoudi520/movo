from __future__ import annotations

from typing import Any

from app.core.db import get_db

COLLECTION = "knowledge_retrieval_sources"


async def get_knowledge_source(main_id: str) -> dict[str, Any]:
    doc = await get_db()[COLLECTION].find_one({"main_id": str(main_id)})
    config = (doc or {}).get("config")
    if not isinstance(config, dict) or config.get("mode") != "external":
        return {"mode": "movo", "displayName": "MOVO 知识库"}
    return dict(config)
