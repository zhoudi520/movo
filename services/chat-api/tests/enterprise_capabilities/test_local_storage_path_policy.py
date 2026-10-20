"""Local filesystem access policy for user-owned storage objects."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.enterprise_capabilities.artifacts.references import (
    is_allowed_local_storage_path,
    object_path_from_local_storage_file,
)


@pytest.fixture
def local_storage_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("STORAGE_BACKEND", "local")
    monkeypatch.setenv("LOCAL_STORAGE_PATH", str(tmp_path))
    from app.core.config import get_settings

    get_settings.cache_clear()
    return tmp_path


def test_static_workspace_path_is_not_mapped_to_object_path(local_storage_root: Path) -> None:
    static_file = Path("/app/static/20261019.docx")
    assert object_path_from_local_storage_file(str(static_file)) is None
    assert not is_allowed_local_storage_path(str(static_file), user_id="user-a")


def test_foreign_storage_file_is_denied(local_storage_root: Path) -> None:
    foreign = local_storage_root / "user-b" / "2026" / "secret.docx"
    foreign.parent.mkdir(parents=True, exist_ok=True)
    foreign.write_bytes(b"x")
    assert not is_allowed_local_storage_path(str(foreign.resolve()), user_id="user-a")


def test_owned_storage_file_is_allowed(local_storage_root: Path) -> None:
    owned = local_storage_root / "user-a" / "2026" / "10" / "19" / "20261019.docx"
    owned.parent.mkdir(parents=True, exist_ok=True)
    owned.write_bytes(b"docx")
    assert is_allowed_local_storage_path(str(owned.resolve()), user_id="user-a")
