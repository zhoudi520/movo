import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException

from app.api.routes.knowledge_source_settings import KnowledgeSourcePayload, _require_tool


def _payload(argument: str, *, mcp_method: str = "search_documents") -> KnowledgeSourcePayload:
    return KnowledgeSourcePayload(
        mode="external", displayName="Customer knowledge", toolId="tool-1",
        mcpToolName=mcp_method, queryArgument=argument,
        mapping={"answerPath": "response.answer"},
    )


def test_mcp_question_field_must_match_declared_string_input():
    tool = {
        "status": "active", "type": "mcp",
        "config": {"enabledToolNames": ["search_documents"]},
        "discovered_tools": [{
            "name": "search_documents",
            "inputSchema": {"type": "object", "properties": {
                "question": {"type": "string"},
                "context": {"type": "string"},
                "limit": {"type": "integer"},
            }},
        }],
    }
    db = SimpleNamespace(external_tools=SimpleNamespace(find_one=AsyncMock(return_value=tool)))

    with patch("app.api.routes.knowledge_source_settings.get_db", return_value=db):
        asyncio.run(_require_tool(_payload("context"), "org-1"))
        for invalid in ("query", "limit"):
            with pytest.raises(HTTPException) as error:
                asyncio.run(_require_tool(_payload(invalid), "org-1"))
            assert error.value.status_code == 400


def test_http_question_field_must_match_declared_text_input():
    tool = {
        "status": "active", "type": "http",
        "config": {"inputSchema": [
            {"name": "question", "type": "String", "location": "Body"},
            {"name": "prompt", "type": "String", "location": "Query"},
            {"name": "limit", "type": "Number", "location": "Query"},
        ]},
    }
    db = SimpleNamespace(external_tools=SimpleNamespace(find_one=AsyncMock(return_value=tool)))

    with patch("app.api.routes.knowledge_source_settings.get_db", return_value=db):
        asyncio.run(_require_tool(_payload("question", mcp_method=""), "org-1"))
        asyncio.run(_require_tool(_payload("prompt", mcp_method=""), "org-1"))
        with pytest.raises(HTTPException) as error:
            asyncio.run(_require_tool(_payload("limit", mcp_method=""), "org-1"))
        assert error.value.status_code == 400
