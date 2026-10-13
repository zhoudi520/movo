import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException

from app.api.routes.tools import delete_tool


def test_delete_rejects_tool_used_by_external_knowledge():
    bindings = SimpleNamespace(find_one=AsyncMock(return_value={"_id": "binding"}))
    tools = SimpleNamespace(delete_one=AsyncMock())
    class FakeDatabase:
        external_tools = tools

        def __getitem__(self, key):
            assert key == "knowledge_retrieval_sources"
            return bindings

    db = FakeDatabase()

    with patch("app.api.routes.tools.get_db", return_value=db):
        with pytest.raises(HTTPException) as error:
            asyncio.run(delete_tool("tool-1", {"main_id": "org-1"}))

    assert error.value.status_code == 409
    tools.delete_one.assert_not_awaited()
    bindings.find_one.assert_awaited_once_with(
        {"main_id": "org-1", "config.mode": "external", "config.toolId": "tool-1"},
        {"_id": 1},
    )
