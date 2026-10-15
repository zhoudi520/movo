"""Foreground dev entry helpers for individual backend services (PyCharm / IDE)."""

from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path
from typing import Literal

from services.run_backends import (
    ADMIN_API_DIR,
    CHAT_API_DIR,
    DEFAULT_ADMIN_PORT,
    DEFAULT_CHAT_PORT,
    DEFAULT_DOC_PORT,
    DEFAULT_MONGODB_DB,
    DEFAULT_MONGODB_URI,
    DEFAULT_REDIS_URL,
    DEFAULT_WEAVIATE_ENDPOINT,
    DOCUMENT_PARSER_DIR,
    REPO_ROOT,
    build_base_env,
    ensure_redis_available,
    fetch_runtime_secrets_from_docker,
    release_port,
    resolve_chat_listen_port,
    resolve_celery_worker_pool,
    _load_auth_module,
)

logger = logging.getLogger(__name__)

ServiceName = Literal["chat-api", "admin-api", "document-parser", "document-worker"]


def ensure_repo_root_on_path() -> None:
    """Put the repository root on ``sys.path`` so ``services.*`` imports work from service dirs."""
    root = str(REPO_ROOT.resolve())
    if root not in sys.path:
        sys.path.insert(0, root)


def resolve_reload_flag(*, no_reload: bool, reload: bool) -> bool:
    """Resolve uvicorn autoreload (Windows defaults off, same as ``run_backends``)."""
    if no_reload and reload:
        raise ValueError("Use only one of --no-reload and --reload")
    if no_reload:
        return False
    if reload:
        return True
    if sys.platform == "win32":
        logger.info("Windows: uvicorn reload is off by default (pass --reload to enable)")
        return False
    return True


def apply_env_to_process(env: dict[str, str]) -> None:
    """Merge development env into the current process (before importing ``app``)."""
    for key, value in env.items():
        os.environ[key] = value


def prepare_service_env(
    *,
    chat_port: int,
    admin_port: int,
    doc_port: int,
    redis_url: str,
    mongodb_uri: str,
    mongodb_db: str,
    weaviate_endpoint: str,
    require_dsh_token: bool,
) -> dict[str, str]:
    """
    Build mixed-development env (auth, Mongo, Redis, DSH gateways) for one service process.

    Raises ``RuntimeError`` when auth or DSH token preparation fails.
    """
    auth_module = _load_auth_module()
    shared_auth = auth_module.prepare_internal_service_auth(REPO_ROOT)
    base_env = build_base_env(
        shared_auth,
        chat_port=chat_port,
        admin_port=admin_port,
        doc_port=doc_port,
        redis_url=redis_url,
        mongodb_uri=mongodb_uri,
        mongodb_db=mongodb_db,
        weaviate_endpoint=weaviate_endpoint,
    )
    runtime_env_file = REPO_ROOT / ".movo-dev" / "runtime.env"
    runtime_secrets = auth_module.load_runtime_secret_values(runtime_env_file)
    if not runtime_secrets.get("DSH_RUNTIME_HOST_TOKEN"):
        volume_prefix = os.environ.get("MOVO_VOLUME_PREFIX", "movo")
        runtime_secrets.update(
            fetch_runtime_secrets_from_docker(
                auth_module,
                repo_root=REPO_ROOT,
                volume_prefix=volume_prefix,
            )
        )
    for key, value in runtime_secrets.items():
        base_env[key] = value
    if require_dsh_token and not str(base_env.get("DSH_RUNTIME_HOST_TOKEN", "")).strip():
        raise RuntimeError(
            "DSH_RUNTIME_HOST_TOKEN is missing. Run bootstrap + sync_runtime_secrets, "
            "or start Docker dsh-runtime-host so run_backends/dev_launcher can sync runtime.env."
        )
    return base_env


def run_uvicorn_foreground(
    *,
    service_name: ServiceName,
    service_dir: Path,
    port: int,
    reload: bool,
) -> None:
    """
    Run uvicorn in the **current** process so IDE consoles show application logs.

    Sets ``cwd`` and ``PYTHONPATH`` to ``service_dir`` before starting.
    """
    service_dir = service_dir.resolve()
    os.chdir(service_dir)
    os.environ["PYTHONPATH"] = str(service_dir)

    import uvicorn

    kwargs: dict = {
        "app": "app.main:app",
        "host": "127.0.0.1",
        "port": port,
        "reload": reload,
        "log_level": "info",
    }
    if reload:
        kwargs["reload_dirs"] = ["app"]
        kwargs["reload_excludes"] = [
            "backend.log",
            "static/*",
            "*.pyc",
            "__pycache__/*",
        ]
        if service_name == "chat-api":
            kwargs["timeout_graceful_shutdown"] = int(
                os.environ.get("BACKEND_GRACEFUL_SHUTDOWN_SECONDS", "5")
            )
    logger.info(f"Running {service_name} on http://127.0.0.1:{port}/docs (foreground, reload={reload})")
    uvicorn.run(**kwargs)


def run_celery_worker_foreground(
    *,
    service_dir: Path,
    queue: str,
    celery_pool: str | None,
) -> None:
    """Run the document-parser Celery worker in the current process."""
    service_dir = service_dir.resolve()
    os.chdir(service_dir)
    os.environ["PYTHONPATH"] = str(service_dir)
    pool = resolve_celery_worker_pool(celery_pool)
    argv = [
        "celery",
        "-A",
        "app.workers.celery_app:celery_app",
        "worker",
        "--loglevel=info",
        f"--queues={queue}",
    ]
    if pool:
        argv.append(f"--pool={pool}")
    pool_label = pool or "prefork (default)"
    logger.info(f"Running document-worker (queue={queue}, pool={pool_label})")
    sys.argv = argv
    from celery.__main__ import main as celery_main

    celery_main()


def _add_common_dev_args(parser: argparse.ArgumentParser) -> None:
    """Register CLI flags shared by all per-service dev entrypoints."""
    parser.add_argument(
        "--chat-port",
        type=int,
        default=int(os.environ.get("BACKEND_PORT", DEFAULT_CHAT_PORT)),
    )
    parser.add_argument(
        "--admin-port",
        type=int,
        default=int(os.environ.get("ADMIN_API_PORT", DEFAULT_ADMIN_PORT)),
    )
    parser.add_argument(
        "--doc-port",
        type=int,
        default=int(os.environ.get("DOC_PROCESSING_PORT", DEFAULT_DOC_PORT)),
    )
    parser.add_argument(
        "--redis-url",
        default=os.environ.get("ASKAI_REDIS_URL", DEFAULT_REDIS_URL),
    )
    parser.add_argument(
        "--mongodb-uri",
        default=os.environ.get("MONGODB_URI", DEFAULT_MONGODB_URI),
    )
    parser.add_argument(
        "--mongodb-db",
        default=os.environ.get("MONGODB_DB", DEFAULT_MONGODB_DB),
    )
    parser.add_argument(
        "--weaviate-endpoint",
        default=os.environ.get("MOVO_DOC_PROCESSING_WEAVIATE_ENDPOINT", DEFAULT_WEAVIATE_ENDPOINT),
    )
    parser.add_argument("--no-reload", action="store_true")
    parser.add_argument("--reload", action="store_true")
    parser.add_argument(
        "--no-release-port",
        action="store_true",
        help="Do not kill existing listeners on this service's port before start",
    )
    parser.add_argument(
        "--fail-if-port-busy",
        action="store_true",
        help="Do not auto-pick another chat-api port when preferred port stays busy",
    )


def main_chat_api(argv: list[str] | None = None) -> int:
    """Prepare mixed-dev env and run chat-api uvicorn in the foreground."""
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    ensure_repo_root_on_path()
    parser = argparse.ArgumentParser(description="Run chat-api locally (PyCharm-friendly).")
    _add_common_dev_args(parser)
    args = parser.parse_args(argv)
    try:
        reload = resolve_reload_flag(no_reload=args.no_reload, reload=args.reload)
    except ValueError as exc:
        logger.error(f"{exc}")
        return 2

    chat_port = args.chat_port
    if not args.no_release_port:
        release_port(chat_port)
    auto_fallback = sys.platform == "win32" and not args.fail_if_port_busy
    try:
        resolved = resolve_chat_listen_port(chat_port, auto_fallback=auto_fallback)
    except RuntimeError as exc:
        logger.error(f"{exc}")
        return 1
    if resolved is None:
        logger.error(
            f"chat-api is already running on http://127.0.0.1:{chat_port}. "
            f"Stop it or use another --chat-port."
        )
        return 1
    chat_port = resolved

    try:
        env = prepare_service_env(
            chat_port=chat_port,
            admin_port=args.admin_port,
            doc_port=args.doc_port,
            redis_url=args.redis_url,
            mongodb_uri=args.mongodb_uri,
            mongodb_db=args.mongodb_db,
            weaviate_endpoint=args.weaviate_endpoint,
            require_dsh_token=True,
        )
    except RuntimeError as exc:
        logger.error(f"{exc}")
        return 1
    apply_env_to_process(env)
    try:
        run_uvicorn_foreground(
            service_name="chat-api",
            service_dir=CHAT_API_DIR,
            port=chat_port,
            reload=reload,
        )
    except KeyboardInterrupt:
        return 0
    return 0


def main_admin_api(argv: list[str] | None = None) -> int:
    """Prepare mixed-dev env and run admin-api uvicorn in the foreground."""
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    ensure_repo_root_on_path()
    parser = argparse.ArgumentParser(description="Run admin-api locally (PyCharm-friendly).")
    _add_common_dev_args(parser)
    args = parser.parse_args(argv)
    try:
        reload = resolve_reload_flag(no_reload=args.no_reload, reload=args.reload)
    except ValueError as exc:
        logger.error(f"{exc}")
        return 2

    if not args.no_release_port:
        release_port(args.admin_port)

    try:
        env = prepare_service_env(
            chat_port=args.chat_port,
            admin_port=args.admin_port,
            doc_port=args.doc_port,
            redis_url=args.redis_url,
            mongodb_uri=args.mongodb_uri,
            mongodb_db=args.mongodb_db,
            weaviate_endpoint=args.weaviate_endpoint,
            require_dsh_token=False,
        )
    except RuntimeError as exc:
        logger.error(f"{exc}")
        return 1
    apply_env_to_process(env)
    try:
        run_uvicorn_foreground(
            service_name="admin-api",
            service_dir=ADMIN_API_DIR,
            port=args.admin_port,
            reload=reload,
        )
    except KeyboardInterrupt:
        return 0
    return 0


def main_document_parser(argv: list[str] | None = None) -> int:
    """Prepare mixed-dev env and run document-parser API uvicorn in the foreground."""
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    ensure_repo_root_on_path()
    parser = argparse.ArgumentParser(description="Run document-parser API locally (PyCharm-friendly).")
    _add_common_dev_args(parser)
    parser.add_argument(
        "--skip-redis-check",
        action="store_true",
        help="Do not verify Redis before starting (API only; worker still needs Redis)",
    )
    args = parser.parse_args(argv)
    try:
        reload = resolve_reload_flag(no_reload=args.no_reload, reload=args.reload)
    except ValueError as exc:
        logger.error(f"{exc}")
        return 2

    if not args.skip_redis_check:
        try:
            ensure_redis_available(args.redis_url)
        except RuntimeError as exc:
            logger.error(f"{exc}")
            return 1

    if not args.no_release_port:
        release_port(args.doc_port)

    try:
        env = prepare_service_env(
            chat_port=args.chat_port,
            admin_port=args.admin_port,
            doc_port=args.doc_port,
            redis_url=args.redis_url,
            mongodb_uri=args.mongodb_uri,
            mongodb_db=args.mongodb_db,
            weaviate_endpoint=args.weaviate_endpoint,
            require_dsh_token=False,
        )
    except RuntimeError as exc:
        logger.error(f"{exc}")
        return 1
    apply_env_to_process(env)
    try:
        run_uvicorn_foreground(
            service_name="document-parser",
            service_dir=DOCUMENT_PARSER_DIR,
            port=args.doc_port,
            reload=reload,
        )
    except KeyboardInterrupt:
        return 0
    return 0


def main_document_worker(argv: list[str] | None = None) -> int:
    """Prepare mixed-dev env and run the document-parser Celery worker in the foreground."""
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    ensure_repo_root_on_path()
    parser = argparse.ArgumentParser(description="Run document-parser Celery worker (PyCharm-friendly).")
    _add_common_dev_args(parser)
    parser.add_argument(
        "--celery-pool",
        default=None,
        help="Celery pool (default: solo on Windows)",
    )
    parser.add_argument(
        "--queue",
        default=os.environ.get("ASKAI_DOC_PROCESSING_CELERY_QUEUE", "document_processing"),
    )
    args = parser.parse_args(argv)

    try:
        ensure_redis_available(args.redis_url)
    except RuntimeError as exc:
        logger.error(f"{exc}")
        return 1

    try:
        env = prepare_service_env(
            chat_port=args.chat_port,
            admin_port=args.admin_port,
            doc_port=args.doc_port,
            redis_url=args.redis_url,
            mongodb_uri=args.mongodb_uri,
            mongodb_db=args.mongodb_db,
            weaviate_endpoint=args.weaviate_endpoint,
            require_dsh_token=False,
        )
    except RuntimeError as exc:
        logger.error(f"{exc}")
        return 1
    apply_env_to_process(env)
    try:
        run_celery_worker_foreground(
            service_dir=DOCUMENT_PARSER_DIR,
            queue=args.queue,
            celery_pool=args.celery_pool,
        )
    except KeyboardInterrupt:
        return 0
    return 0
