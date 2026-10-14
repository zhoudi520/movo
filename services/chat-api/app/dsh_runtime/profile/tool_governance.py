"""Shared HTTP/MCP tool risk and approval rules for DSH Tool Profile compilation."""

from __future__ import annotations

from typing import Any, Literal, Mapping, Sequence

RiskLevel = Literal["read", "write", "dangerous"]


def _safe_dict(value: Any) -> dict[str, Any]:
    """Return a shallow dict copy or an empty dict for non-mapping values."""
    return dict(value) if isinstance(value, dict) else {}


def _approval_from_config(config: Mapping[str, Any], *, default: bool) -> bool:
    """Resolve approval_required from connector config with the same defaulting as compile."""
    if "approvalRequired" in config:
        return bool(config.get("approvalRequired"))
    if "approval_required" in config:
        return bool(config.get("approval_required"))
    return default


def http_connection_governance(config: Mapping[str, Any]) -> dict[str, Any]:
    """
    Compute risk and approval flags for one HTTP enterprise tool connection.

    Mirrors ``ToolProfileCompiler._compile_http`` without building a full profile.
    """
    cfg = _safe_dict(config)
    method = str(cfg.get("method") or "GET").upper()
    explicit_risk = str(cfg.get("riskLevel") or cfg.get("risk_level") or "").lower()
    if explicit_risk in {"read", "write", "dangerous"}:
        risk: RiskLevel = explicit_risk  # type: ignore[assignment]
    else:
        risk = "read" if method in {"GET", "HEAD", "OPTIONS"} else "write"
    approval_required = _approval_from_config(cfg, default=(risk != "read"))
    return {
        "risk_level": risk,
        "approval_required": approval_required,
        "http_method": method,
    }


def mcp_discovered_tool_governance(
    *,
    config: Mapping[str, Any],
    annotations: Mapping[str, Any],
) -> dict[str, Any]:
    """
    Compute risk and approval flags for one MCP discovered tool entry.

    Mirrors ``ToolProfileCompiler._compile_mcp`` annotation and config handling.
    """
    cfg = _safe_dict(config)
    ann = _safe_dict(annotations)
    read_only = ann.get("readOnlyHint") is True
    destructive = ann.get("destructiveHint") is True
    if destructive:
        risk: RiskLevel = "dangerous"
    elif read_only:
        risk = "read"
    else:
        risk = "write"
    approval_required = _approval_from_config(cfg, default=(risk != "read"))
    return {
        "risk_level": risk,
        "approval_required": approval_required,
        "read_only_hint": read_only,
        "destructive_hint": destructive,
    }


def preview_mcp_governance(
    *,
    config: Mapping[str, Any],
    discovered_tools: Sequence[Any],
) -> list[dict[str, Any]]:
    """
    Preview governance for each MCP discovered tool row (name + annotations).

    Skips entries without a native tool name, matching compile-time filtering.
    """
    cfg = _safe_dict(config)
    items: list[dict[str, Any]] = []
    for row in discovered_tools:
        if not isinstance(row, dict):
            continue
        name = str(row.get("name") or "").strip()
        if not name:
            continue
        ann = _safe_dict(row.get("annotations"))
        gov = mcp_discovered_tool_governance(config=cfg, annotations=ann)
        items.append({"name": name, **gov})
    return items
