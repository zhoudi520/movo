"""Prepare shared development credentials for chat-api, admin-api, and document-parser."""

from __future__ import annotations

import os
import secrets
from pathlib import Path


RUNTIME_SECRET_KEYS = (
    "DSH_RUNTIME_HOST_TOKEN",
    "DSH_MODEL_GATEWAY_SIGNING_SECRET",
    "END_USER_AUTH_SECRET",
    "ADMIN_BACKEND_SERVICE_TOKEN",
    "ASKAI_ADMIN_BACKEND_SERVICE_TOKEN",
    "MOVO_DOC_PROCESSING_SERVICE_TOKEN",
    "ASKAI_ADMIN_DOCUMENT_PROCESSING_SERVICE_TOKEN",
    "ASKAI_ADMIN_JWT_SECRET",
    "MOVO_DOC_PROCESSING_ADMIN_JWT_SECRET",
)


def read_env_value(key: str, env_file: Path) -> str | None:
    """Read a single KEY=value from a dotenv file without executing it."""
    if not env_file.is_file():
        return None
    prefix = f"{key}="
    for raw_line in env_file.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or not line.startswith(prefix):
            continue
        value = line[len(prefix) :].strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        return value.rstrip("\r")
    return None


def load_runtime_secret_values(runtime_env_file: Path) -> dict[str, str]:
    """Load selected keys from a Docker ``runtime.env`` file for host-side services."""
    if not runtime_env_file.is_file():
        return {}
    return load_runtime_secret_values_from_text(runtime_env_file.read_text(encoding="utf-8"))


def load_runtime_secret_values_from_text(runtime_env_text: str) -> dict[str, str]:
    """Parse selected keys from ``runtime.env`` content."""
    values: dict[str, str] = {}
    for key in RUNTIME_SECRET_KEYS:
        prefix = f"{key}="
        for raw_line in runtime_env_text.splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or not line.startswith(prefix):
                continue
            value = line[len(prefix) :].strip().strip('"').strip("'").rstrip("\r")
            if value:
                values[key] = value
            break
    return values


def prepare_internal_service_auth(root_dir: Path | None = None) -> dict[str, str]:
    """
    Build environment variables shared across backend services in source-dev mode.

    Mirrors ``scripts/dev/internal_service_auth.sh`` so Python and Bash launchers
    behave the same.
    """
    root = root_dir.resolve() if root_dir else None
    env: dict[str, str] = {}

    token = (
        os.environ.get("ADMIN_BACKEND_SERVICE_TOKEN")
        or os.environ.get("ASKAI_ADMIN_BACKEND_SERVICE_TOKEN")
        or ""
    )
    if not token:
        token = secrets.token_hex(32)
    env["ADMIN_BACKEND_SERVICE_TOKEN"] = token
    env["ASKAI_ADMIN_BACKEND_SERVICE_TOKEN"] = token

    document_token = (
        os.environ.get("MOVO_DOC_PROCESSING_SERVICE_TOKEN")
        or os.environ.get("ASKAI_ADMIN_DOCUMENT_PROCESSING_SERVICE_TOKEN")
        or os.environ.get("DOCUMENT_PROCESSING_SERVICE_TOKEN")
        or ""
    )
    if not document_token:
        document_token = secrets.token_hex(32)
    env["MOVO_DOC_PROCESSING_SERVICE_TOKEN"] = document_token
    env["ASKAI_ADMIN_DOCUMENT_PROCESSING_SERVICE_TOKEN"] = document_token
    env["DOCUMENT_PROCESSING_SERVICE_TOKEN"] = document_token

    admin_jwt_secret = (
        os.environ.get("ASKAI_ADMIN_JWT_SECRET")
        or os.environ.get("MOVO_DOC_PROCESSING_ADMIN_JWT_SECRET")
        or ""
    )
    if not admin_jwt_secret and root is not None:
        for candidate in (
            root / "services" / "admin-api" / ".env",
            root / "services" / "document-parser" / ".env",
            root / "services" / "chat-api" / ".env",
        ):
            admin_jwt_secret = read_env_value("ASKAI_ADMIN_JWT_SECRET", candidate) or ""
            if not admin_jwt_secret:
                admin_jwt_secret = read_env_value("MOVO_DOC_PROCESSING_ADMIN_JWT_SECRET", candidate) or ""
            if not admin_jwt_secret:
                admin_jwt_secret = read_env_value("JWT_SECRET", candidate) or ""
            if admin_jwt_secret:
                break

    generated_secret_file = root / ".movo-dev" / "admin_jwt_secret" if root else None
    if not admin_jwt_secret and generated_secret_file is not None:
        if generated_secret_file.is_file() and generated_secret_file.stat().st_size > 0:
            admin_jwt_secret = generated_secret_file.read_text(encoding="utf-8").splitlines()[0].strip()
        else:
            admin_jwt_secret = secrets.token_hex(32)
            generated_secret_file.parent.mkdir(parents=True, exist_ok=True)
            try:
                generated_secret_file.parent.chmod(0o700)
            except OSError:
                pass
            generated_secret_file.write_text(f"{admin_jwt_secret}\n", encoding="utf-8")
            try:
                generated_secret_file.chmod(0o600)
            except OSError:
                pass

    if not admin_jwt_secret:
        raise RuntimeError(
            "A stable admin JWT secret is required. Set ASKAI_ADMIN_JWT_SECRET in "
            "services/admin-api/.env or run from the repository root so "
            ".movo-dev/admin_jwt_secret can be created."
        )

    env["ASKAI_ADMIN_JWT_SECRET"] = admin_jwt_secret
    env["MOVO_DOC_PROCESSING_ADMIN_JWT_SECRET"] = admin_jwt_secret
    return env
