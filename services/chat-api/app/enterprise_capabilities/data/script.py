"""Thin adapter for the existing sandboxed script-plugin implementation."""

from __future__ import annotations

import json
from typing import Any

from app.enterprise_capabilities.artifacts.references import user_local_storage_root
from app.enterprise_capabilities.data.script_workspace_index import index_user_storage_files
from app.enterprise_capabilities.runtime.execution_contracts import CapabilityTask
from app.enterprise_capabilities.data.script_engine.executor import ScriptPluginExecutor
from app.enterprise_capabilities.runtime.execution_contracts import CapabilityInputs

from app.enterprise_capabilities.runtime.contracts import CapabilityExecutionContext
from app.enterprise_capabilities.data.script_contract import compile_script_plugin
from app.enterprise_capabilities.data.script_inputs import governed_script_files
from app.enterprise_capabilities.artifacts.delivery_scope import apply_result_delivery_scope


def _workspace_snapshot(context: CapabilityExecutionContext, files: list[dict[str, Any]]) -> dict[str, Any]:
    """Build the authenticated user's persisted-file index for script inputs."""
    return {
        "user_storage_dir": user_local_storage_root(context.user_id),
        "stored_files": index_user_storage_files(context.user_id),
        "session_files": files,
    }


def _prefer_builtin_workspace_list(code: str) -> bool:
    """Return True when the script only needs the precomputed workspace file index."""
    source = str(code or "").strip()
    if not source:
        return True
    lowered = source.lower()
    if "/app/storage" in lowered or "knowledge-documents" in lowered or "/app/" in lowered:
        return True
    if "stored_files" in lowered and len(source) < 600:
        return True
    if any(token in source for token in ("文件清单", "有哪些文件", "工作空间")) and len(source) < 900:
        return True
    return False


def _builtin_workspace_list_result(
    workspace: dict[str, Any],
    *,
    delivery_scope: Any,
) -> dict[str, Any]:
    """Return a script-shaped success payload without entering the subprocess sandbox."""
    listing = list(workspace.get("stored_files") or [])
    payload = {
        "success": True,
        "plugin_result": {
            "data": {
                "stdout": [json.dumps(listing, ensure_ascii=False, indent=2)],
            },
        },
        "workspace": workspace,
    }
    return apply_result_delivery_scope(payload, delivery_scope)


async def run_script(arguments: dict[str, Any], context: CapabilityExecutionContext) -> dict[str, Any]:
    input_data = dict(arguments.get("data") or {})
    files = governed_script_files(arguments, context)
    workspace = _workspace_snapshot(context, files)
    source_code = str(arguments.get("code") or "")
    if _prefer_builtin_workspace_list(source_code):
        return _builtin_workspace_list_result(workspace, delivery_scope=arguments.get("delivery_scope"))
    reserved = {"user_id", "files", "input_artifacts", "graph_artifacts"}
    if reserved.intersection(input_data):
        raise ValueError("script data uses a reserved MOVO context key")
    node = CapabilityTask(
        node_id=f"dsh-script-{context.action_id}", goal="Run governed data-processing script",
        assigned_agent="agent.analysis", expected_artifacts=["plugin_result", "documents", "images"],
        meta={
            "capability_id": "file.run_script_plugin",
            "semantic_config": {"pluginCode": compile_script_plugin(source_code)},
        },
    )
    inputs = CapabilityInputs(
        messages=[], raw_messages=[], intent=node.goal, language="zh",
        output_spec={
            **input_data,
            "user_id": context.user_id,
            "files": files,
            "input_artifacts": {"data": input_data, "files": files},
            "graph_artifacts": {},
        },
    )
    artifacts: dict[str, Any] = {}
    terminal_status = ""
    terminal_error = ""
    async for event, produced in ScriptPluginExecutor().execute(
        runtime=None, task_id=context.conversation_id, run_id=context.action_id,
        node=node, inputs=inputs, skills={},
    ):
        if isinstance(produced, dict):
            artifacts.update(produced)
        if event.get("type") == "subagent_done" and isinstance(event.get("content"), dict):
            terminal_status = str(event["content"].get("status") or "")
            terminal_error = str(event["content"].get("error") or "")
    if terminal_status != "succeeded":
        detail = f": {terminal_error}" if terminal_error else ""
        raise RuntimeError(f"script plugin failed: {terminal_status or 'unknown'}{detail}")
    scoped = apply_result_delivery_scope(artifacts, arguments.get("delivery_scope"))
    return {"success": True, "workspace": workspace, **scoped}
