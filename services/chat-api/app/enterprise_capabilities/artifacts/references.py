from __future__ import annotations

from pathlib import Path
from typing import Any

from app.core.config import get_settings

LEGACY_SHARED_STORAGE_OWNERS = frozenset({"document-parser", "runtime-document-parser"})


def safe_owner_prefix(user_id: str) -> str:
    owner = "".join(character if character.isalnum() or character in {"-", "_"} else "_" for character in str(user_id).strip())
    return (owner or "anonymous") + "/"


def require_owned_artifact(artifact: dict[str, Any], *, user_id: str) -> dict[str, Any]:
    value = dict(artifact or {})
    object_path = str(value.get("object_path") or "").strip().lstrip("/")
    if not object_path or ".." in object_path.split("/") or not object_path.startswith(safe_owner_prefix(user_id)):
        raise PermissionError("artifact reference is outside the authenticated user's storage scope")
    value["object_path"] = object_path
    # Bearer URLs are never trusted from model arguments. Storage resolves a
    # fresh URL from the authorized immutable object path when necessary.
    value.pop("url", None)
    value.pop("signed_url", None)
    return value


def require_owned_artifacts(items: list[Any], *, user_id: str) -> list[dict[str, Any]]:
    return [require_owned_artifact(dict(item), user_id=user_id) for item in items if isinstance(item, dict)]


def storage_owner_from_object_path(object_path: str) -> str | None:
    """Return the first path segment when it denotes an end-user storage owner."""
    token = str(object_path or "").strip().lstrip("/").split("/", 1)[0]
    if not token or token in LEGACY_SHARED_STORAGE_OWNERS or ".." in token:
        return None
    return token


def is_legacy_shared_storage_object_path(object_path: str) -> bool:
    """True for historical parser artifacts stored under a shared service prefix."""
    token = str(object_path or "").strip().lstrip("/").split("/", 1)[0]
    return token in LEGACY_SHARED_STORAGE_OWNERS


def user_local_storage_root(user_id: str) -> str:
    """Return the on-disk root directory for a user's local object storage prefix."""
    settings = get_settings()
    if str(settings.STORAGE_BACKEND or "oss").strip().lower() != "local":
        return ""
    storage_root = Path(str(settings.LOCAL_STORAGE_PATH or "storage")).expanduser().resolve()
    owner = safe_owner_prefix(user_id).strip("/")
    if not owner:
        return ""
    candidate = (storage_root / owner).resolve()
    try:
        candidate.relative_to(storage_root)
    except ValueError:
        return ""
    return str(candidate)


def resolve_artifact_user_id(artifact: dict[str, Any], *, fallback: str = "") -> str:
    """Resolve the storage owner for an artifact reference."""
    for key in ("user_id", "userId"):
        value = str(artifact.get(key) or "").strip()
        if value:
            return value
    owner = storage_owner_from_object_path(str(artifact.get("object_path") or ""))
    if owner:
        return owner
    return str(fallback or "").strip()


def object_path_from_local_storage_file(local_path: str) -> str | None:
    """Map an on-disk file under ``LOCAL_STORAGE_PATH`` to its object-path token."""
    token = str(local_path or "").strip()
    if not token:
        return None
    settings = get_settings()
    if str(settings.STORAGE_BACKEND or "oss").strip().lower() != "local":
        return None
    root = Path(str(settings.LOCAL_STORAGE_PATH or "storage")).expanduser().resolve()
    try:
        relative = Path(token).expanduser().resolve().relative_to(root)
    except (ValueError, OSError):
        return None
    parts = [part for part in relative.parts if part not in {".", ""}]
    if not parts or ".." in parts:
        return None
    return "/".join(parts)


def is_allowed_local_storage_path(local_path: str, *, user_id: str) -> bool:
    """Return True when ``local_path`` resolves to the caller's owned storage object."""
    object_path = object_path_from_local_storage_file(local_path)
    if not object_path:
        return False
    try:
        require_owned_artifact({"object_path": object_path}, user_id=user_id)
    except PermissionError:
        return False
    return True


def authorize_nested_artifact_refs(value: Any, *, user_id: str, depth: int = 0) -> Any:
    if depth > 12:
        raise ValueError("artifact input nesting is too deep")
    if isinstance(value, dict):
        current = dict(value)
        if "object_path" in current:
            current = require_owned_artifact(current, user_id=user_id)
        return {key: authorize_nested_artifact_refs(item, user_id=user_id, depth=depth + 1) for key, item in current.items()}
    if isinstance(value, list):
        return [authorize_nested_artifact_refs(item, user_id=user_id, depth=depth + 1) for item in value[:500]]
    return value
