"""Validate the declared tool input field that receives a user's question."""

from __future__ import annotations

import re
from typing import Any

NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,63}$")


def _is_text(type_value: Any) -> bool:
    return isinstance(type_value, str) and type_value.lower() == "string" or (
        isinstance(type_value, list) and any(isinstance(item, str) and item.lower() == "string" for item in type_value)
    )


def mcp_question_fields(tool: dict[str, Any], method_name: str) -> set[str]:
    methods = tool.get("discovered_tools") or []
    method = next((item for item in methods if isinstance(item, dict) and item.get("name") == method_name), None)
    schema = method.get("inputSchema") if method else None
    properties = schema.get("properties") if isinstance(schema, dict) else None
    if not isinstance(properties, dict):
        return set()
    return {
        name for name, definition in properties.items()
        if isinstance(name, str) and isinstance(definition, dict)
        and _is_text(definition.get("type"))
    }


def http_question_fields(tool: dict[str, Any]) -> set[str]:
    nodes = (tool.get("config") or {}).get("inputSchema")
    if not isinstance(nodes, list):
        return set()
    counts: dict[str, int] = {}

    def visit(items: list[Any]) -> None:
        for node in items:
            if not isinstance(node, dict):
                continue
            name = node.get("name")
            if isinstance(name, str) and NAME_RE.fullmatch(name) and _is_text(node.get("type")):
                counts[name] = counts.get(name, 0) + 1
            if isinstance(node.get("children"), list):
                visit(node["children"])

    visit(nodes)
    return {name for name, count in counts.items() if count == 1}
