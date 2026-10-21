from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from app.enterprise_capabilities.data.script_engine.executor import ScriptPluginExecutor


def _run_plugin(tmp_path: Path, code: str) -> subprocess.CompletedProcess[str]:
    output_dir = tmp_path / "out"
    output_dir.mkdir()
    plugin = tmp_path / "plugin.py"
    plugin.write_text(code, encoding="utf-8")
    runner = tmp_path / "runner.py"
    runner.write_text(ScriptPluginExecutor._runner_source(), encoding="utf-8")
    payload = tmp_path / "payload.json"
    payload.write_text(json.dumps({
        "inputs": {},
        "context": {"work_dir": str(tmp_path), "output_dir": str(output_dir)},
    }), encoding="utf-8")
    return subprocess.run(
        [sys.executable, "-I", str(runner), str(plugin), str(payload)],
        capture_output=True, text=True, timeout=10,
    )


def test_pathlib_imported_inside_plugin_can_read_and_write_work_dir(tmp_path: Path) -> None:
    result = _run_plugin(tmp_path, '''
def run(inputs, context):
    from pathlib import Path
    path = Path(context["output_dir"]) / "result.txt"
    path.write_text("ok")
    return {"data": path.read_text()}
''')
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["data"] == "ok"


def test_io_open_accepts_existing_file_descriptor(tmp_path: Path) -> None:
    result = _run_plugin(tmp_path, '''
def run(inputs, context):
    import io
    import os
    read_fd, write_fd = os.pipe()
    os.write(write_fd, b"ok")
    os.close(write_fd)
    with io.open(read_fd, "rb") as stream:
        return {"data": stream.read().decode()}
''')
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["data"] == "ok"


def test_pathlib_still_cannot_read_outside_work_dir(tmp_path: Path) -> None:
    result = _run_plugin(tmp_path, '''
def run(inputs, context):
    from pathlib import Path
    Path("/etc/passwd").read_text()
    return {}
''')
    assert result.returncode != 0
    assert "script_plugin file access is limited to work_dir" in result.stderr
