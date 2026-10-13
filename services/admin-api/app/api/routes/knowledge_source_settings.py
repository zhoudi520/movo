"""Tenant knowledge retrieval source; separate from MOVO document processing settings."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, model_validator

from app.api.deps import get_current_admin_user
from app.api.tool_limits import enabled_mcp_tool_names
from app.api.knowledge_question_input import http_question_fields, mcp_question_fields
from app.core.db import get_db

router = APIRouter()
COLLECTION = "knowledge_retrieval_sources"
PATH_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*(?:\.(?:[A-Za-z_][A-Za-z0-9_]*|[0-9]+))*$")


class SourceMapping(BaseModel):
    answerPath: str = Field(default="", max_length=256)
    sourcesPath: str = Field(default="", max_length=256)
    titlePath: str = Field(default="", max_length=256)
    documentUrlPath: str = Field(default="", max_length=256)
    snippetPath: str = Field(default="", max_length=256)

    @model_validator(mode="after")
    def validate_paths(self) -> "SourceMapping":
        for name in type(self).model_fields:
            path = getattr(self, name).strip()
            if path and not PATH_RE.fullmatch(path):
                raise ValueError(f"Invalid field path: {name}")
            setattr(self, name, path)
        return self


class KnowledgeSourcePayload(BaseModel):
    mode: Literal["movo", "external"] = "movo"
    displayName: str = Field(default="", max_length=120)
    toolId: str = Field(default="", max_length=256)
    mcpToolName: str = Field(default="", max_length=256)
    queryArgument: str = Field(default="query", max_length=64)
    mapping: SourceMapping = Field(default_factory=SourceMapping)

    @model_validator(mode="after")
    def validate_external(self) -> "KnowledgeSourcePayload":
        if self.mode == "external" and not (self.displayName.strip() and self.toolId.strip() and self.mapping.answerPath):
            raise ValueError("External knowledge requires a name, tool and answer field")
        if self.mode == "external" and not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]{0,63}", self.queryArgument):
            raise ValueError("External knowledge requires a valid question input field")
        self.displayName = self.displayName.strip()
        self.toolId = self.toolId.strip()
        self.mcpToolName = self.mcpToolName.strip()
        return self


async def _require_tool(payload: KnowledgeSourcePayload, main_id: str) -> None:
    if payload.mode != "external":
        return
    tool = await get_db().external_tools.find_one({"_id": payload.toolId, "main_id": main_id, "scope": {"$ne": "user"}})
    if not tool or tool.get("status") != "active":
        raise HTTPException(status_code=400, detail="请先选择本企业已启用的工具")
    if tool.get("type") == "mcp":
        if payload.mcpToolName not in enabled_mcp_tool_names(tool.get("config")):
            raise HTTPException(status_code=400, detail="请选择此 MCP 服务中已启用的检索工具")
        if payload.queryArgument not in mcp_question_fields(tool, payload.mcpToolName):
            raise HTTPException(status_code=400, detail="请选择该 MCP 工具已声明的文本入参作为用户问题传入字段")
    if tool.get("type") == "http":
        if payload.mcpToolName:
            raise HTTPException(status_code=400, detail="HTTP 工具不需要 MCP 工具名称")
        if payload.queryArgument not in http_question_fields(tool):
            raise HTTPException(status_code=400, detail="请先在 HTTP 工具中声明文本入参，并选择用户问题传入字段")


@router.get("/source")
async def get_source_settings(current_user: dict = Depends(get_current_admin_user)) -> dict:
    main_id = str(current_user.get("main_id") or "default")
    doc = await get_db()[COLLECTION].find_one({"main_id": main_id})
    return KnowledgeSourcePayload.model_validate((doc or {}).get("config") or {}).model_dump()


@router.put("/source")
async def save_source_settings(
    payload: KnowledgeSourcePayload,
    current_user: dict = Depends(get_current_admin_user),
) -> dict:
    main_id = str(current_user.get("main_id") or "default")
    await _require_tool(payload, main_id)
    await get_db()[COLLECTION].update_one(
        {"main_id": main_id},
        {"$set": {"config": payload.model_dump(), "updated_at": datetime.now(timezone.utc)},
         "$setOnInsert": {"main_id": main_id}},
        upsert=True,
    )
    return payload.model_dump()
