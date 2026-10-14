"""Tests for shared HTTP/MCP governance preview rules."""

from app.dsh_runtime.profile.tool_governance import (
    http_connection_governance,
    mcp_discovered_tool_governance,
    preview_mcp_governance,
)


def test_mcp_read_only_skips_approval_by_default() -> None:
    gov = mcp_discovered_tool_governance(
        config={},
        annotations={"readOnlyHint": True},
    )
    assert gov["risk_level"] == "read"
    assert gov["approval_required"] is False


def test_mcp_destructive_requires_approval_by_default() -> None:
    gov = mcp_discovered_tool_governance(
        config={},
        annotations={"destructiveHint": True},
    )
    assert gov["risk_level"] == "dangerous"
    assert gov["approval_required"] is True


def test_mcp_config_can_force_approval_on_read_only() -> None:
    gov = mcp_discovered_tool_governance(
        config={"approvalRequired": True},
        annotations={"readOnlyHint": True},
    )
    assert gov["approval_required"] is True


def test_preview_mcp_governance_lists_named_tools_only() -> None:
    items = preview_mcp_governance(
        config={},
        discovered_tools=[
            {"name": "search", "annotations": {"readOnlyHint": True}},
            {"name": "", "annotations": {}},
            "invalid",
        ],
    )
    assert len(items) == 1
    assert items[0]["name"] == "search"
    assert items[0]["approval_required"] is False


def test_http_get_defaults_to_read_without_approval() -> None:
    gov = http_connection_governance({"method": "GET"})
    assert gov["risk_level"] == "read"
    assert gov["approval_required"] is False


def test_http_post_defaults_to_write_with_approval() -> None:
    gov = http_connection_governance({"method": "POST"})
    assert gov["risk_level"] == "write"
    assert gov["approval_required"] is True
