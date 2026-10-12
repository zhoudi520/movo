"""Launch MOVO backend services (chat-api, admin-api, document-parser) for local development."""

from __future__ import annotations

import argparse
import importlib.util
import logging
import os
import signal
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

logger = logging.getLogger(__name__)

SERVICES_DIR = Path(__file__).resolve().parent
REPO_ROOT = SERVICES_DIR.parent
CHAT_API_DIR = SERVICES_DIR / "chat-api"
ADMIN_API_DIR = SERVICES_DIR / "admin-api"
DOCUMENT_PARSER_DIR = SERVICES_DIR / "document-parser"

DEFAULT_CHAT_PORT = 8000
DEFAULT_ADMIN_PORT = 8100
DEFAULT_DOC_PORT = 8200
DEFAULT_REDIS_URL = "redis://127.0.0.1:6379/0"
DEFAULT_MONGODB_URI = "mongodb://127.0.0.1:27017"
DEFAULT_MONGODB_DB = "gragentic"
DEFAULT_WEAVIATE_ENDPOINT = "http://127.0.0.1:8080"

_processes: list[subprocess.Popen[bytes]] = []
_shutting_down = False


def _port_is_busy(host: str, port: int) -> bool:
    """Return True if something is already listening on host:port."""
    import socket

    probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        probe.bind((host, port))
        return False
    except OSError:
        return True
    finally:
        probe.close()


def _windows_listener_pids(port: int) -> set[int]:
    """Collect candidate PIDs listening on a TCP port (netstat + PowerShell)."""
    pids: set[int] = set()
    needle = f":{port}"
    try:
        result = subprocess.run(
            ["netstat", "-ano"],
            capture_output=True,
            text=True,
            check=False,
        )
        for line in result.stdout.splitlines():
            if "LISTENING" not in line or needle not in line:
                continue
            parts = line.split()
            if parts and parts[-1].isdigit():
                pids.add(int(parts[-1]))
    except OSError:
        pass
    ps_cmd = (
        f"Get-NetTCPConnection -LocalPort {port} -State Listen -ErrorAction SilentlyContinue | "
        "Select-Object -ExpandProperty OwningProcess"
    )
    try:
        ps = subprocess.run(
            ["powershell", "-NoProfile", "-Command", ps_cmd],
            capture_output=True,
            text=True,
            check=False,
        )
        for token in ps.stdout.split():
            if token.isdigit():
                pids.add(int(token))
    except OSError:
        pass
    ps_uvicorn = (
        "Get-CimInstance Win32_Process -Filter \"Name='python.exe'\" | "
        f"Where-Object {{ $_.CommandLine -match 'uvicorn' -and $_.CommandLine -match '--port' "
        f"-and $_.CommandLine -match '{port}' }} | "
        "Select-Object -ExpandProperty ProcessId"
    )
    try:
        ps2 = subprocess.run(
            ["powershell", "-NoProfile", "-Command", ps_uvicorn],
            capture_output=True,
            text=True,
            check=False,
        )
        for token in ps2.stdout.split():
            if token.isdigit():
                pids.add(int(token))
    except OSError:
        pass
    pids.discard(os.getpid())
    return pids


def _taskkill_tree(pid: int) -> bool:
    """Terminate a Windows process tree; return True if taskkill reported success."""
    completed = subprocess.run(
        ["taskkill", "/PID", str(pid), "/F", "/T"],
        capture_output=True,
        text=True,
        check=False,
    )
    return completed.returncode == 0


def _chat_api_ready_on_port(host: str, port: int, *, timeout: float = 2.5) -> bool | None:
    """
    Probe MOVO chat-api readiness on a port.

    Returns True when ``/ready`` is HTTP 200, False when MOVO responds but not ready,
    and None when nothing MOVO-like is listening.
    """
    url = f"http://{host}:{port}/ready"
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:
            return response.status == 200
    except urllib.error.HTTPError as exc:
        if exc.code == 503:
            return False
        return None
    except (urllib.error.URLError, TimeoutError, OSError):
        return None


def resolve_chat_listen_port(
    preferred: int,
    *,
    host: str = "127.0.0.1",
    auto_fallback: bool,
) -> int | None:
    """
    Pick a TCP port for chat-api when the preferred port is still occupied.

    On Windows, stale uvicorn reload workers often leave ``8000`` busy but ``/ready`` fails;
    when ``auto_fallback`` is enabled, scan upward for a free port.

    Returns ``None`` when an already-ready chat-api is listening on ``preferred`` and a new
    process should not be started.
    """
    if preferred <= 0:
        raise ValueError(f"Invalid chat port: {preferred}")
    if not _port_is_busy(host, preferred):
        return preferred

    readiness = _chat_api_ready_on_port(host, preferred)
    if readiness is True:
        logger.info(
            f"chat-api is already ready on http://{host}:{preferred}; skipping a new chat-api process."
        )
        return None

    if readiness is False:
        logger.warning(
            f"http://{host}:{preferred} is occupied by a stale or degraded chat-api "
            f"(DSH /ready fails). "
        )
    else:
        logger.warning(f"Port {preferred} is in use by another process.")

    if not auto_fallback:
        raise RuntimeError(
            f"Port {preferred} is busy. Free it, pass --chat-port, set BACKEND_PORT, "
            f"or on Windows omit --fail-if-port-busy to auto-pick the next free port."
        )

    for candidate in range(preferred + 1, preferred + 32):
        if _port_is_busy(host, candidate):
            continue
        logger.warning(
            f"Using chat-api port {candidate} instead of {preferred}. "
            f"Set BACKEND_PORT={candidate} and point user-web at "
            f"http://127.0.0.1:{candidate} (VITE_LEGACY_API_TARGET / VITE_AIGC_API_TARGET). "
            f"If Docker DSH calls this host, set MOVO_HOST_BACKEND_PORT={candidate} and "
            f"recreate dsh-runtime-host."
        )
        return candidate
    raise RuntimeError(f"No free port found near {preferred} for chat-api.")


def release_port(port: int) -> None:
    """
    Free a TCP port before starting uvicorn.

    Windows ``--reload`` often leaves multiple LISTENING PIDs; requests then hit
    stale workers without the current DSH token.
    """
    if port <= 0:
        return
    released: set[int] = set()
    if sys.platform == "win32":
        for _ in range(3):
            for pid in _windows_listener_pids(port):
                if pid in released:
                    continue
                released.add(pid)
                _taskkill_tree(pid)
            if not _port_is_busy("127.0.0.1", port):
                break
            time.sleep(0.4)
        if _port_is_busy("127.0.0.1", port):
            logger.warning(
                f"Port {port} is still in use after release (pids attempted={sorted(released)}). "
                f"Close other uvicorn/PyCharm runs, or start with --chat-port / BACKEND_PORT."
            )
        elif released:
            logger.info(f"Released port {port} (pids={sorted(released)})")
        return
    try:
        result = subprocess.run(
            ["lsof", "-ti", f"tcp:{port}"],
            capture_output=True,
            text=True,
            check=False,
        )
        for token in result.stdout.split():
            if token.isdigit():
                pid = int(token)
                if pid not in released and pid != os.getpid():
                    released.add(pid)
                    subprocess.run(["kill", str(pid)], check=False)
    except OSError:
        pass
    if released:
        logger.info(f"Released port {port} (pids={sorted(released)})")


def fetch_runtime_secrets_from_docker(
    auth_module: object,
    *,
    repo_root: Path,
    volume_prefix: str,
) -> dict[str, str]:
    """
    Read ``runtime.env`` from the Compose deployment-secrets volume via Docker.

    Persists a copy under ``.movo-dev/runtime.env`` when fetch succeeds.
    """
    volume_name = f"{volume_prefix}_deployment-secrets"
    try:
        completed = subprocess.run(
            [
                "docker",
                "run",
                "--rm",
                "-v",
                f"{volume_name}:/run/askai-secrets:ro",
                "alpine:3.21",
                "cat",
                "/run/askai-secrets/runtime.env",
            ],
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        logger.debug(f"Could not read Docker runtime secrets: {exc}")
        return {}
    if completed.returncode != 0 or not completed.stdout.strip():
        logger.debug(
            f"Docker runtime secrets unavailable (volume={volume_name}, code={completed.returncode})"
        )
        return {}
    runtime_env_file = repo_root / ".movo-dev" / "runtime.env"
    runtime_env_file.parent.mkdir(parents=True, exist_ok=True)
    runtime_env_file.write_text(completed.stdout, encoding="utf-8")
    logger.info(f"Synced Docker runtime secrets to {runtime_env_file}")
    return auth_module.load_runtime_secret_values_from_text(completed.stdout)


def _load_auth_module():
    """Import ``scripts/dev/internal_service_auth.py`` without requiring a package layout."""
    auth_path = REPO_ROOT / "scripts" / "dev" / "internal_service_auth.py"
    spec = importlib.util.spec_from_file_location("movo_internal_service_auth", auth_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load auth helper from {auth_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def resolve_python_executable() -> Path:
    """Prefer the unified services venv, then chat-api venv, then the current interpreter."""
    if os.environ.get("MOVO_PYTHON"):
        return Path(os.environ["MOVO_PYTHON"]).resolve()
    candidates = (
        SERVICES_DIR / ".venv" / "Scripts" / "python.exe",
        SERVICES_DIR / ".venv" / "bin" / "python",
        CHAT_API_DIR / "venv" / "Scripts" / "python.exe",
        CHAT_API_DIR / "venv" / "bin" / "python",
    )
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    return Path(sys.executable).resolve()


def ensure_redis_available(redis_url: str) -> None:
    """Verify Redis responds to PING at the configured URL."""
    try:
        import redis
    except ImportError as exc:
        raise RuntimeError(
            "The redis package is required to verify Redis. "
            "Install backend deps: pip install -r services/requirements.txt"
        ) from exc
    try:
        client = redis.from_url(redis_url, socket_connect_timeout=2)
        if not client.ping():
            raise RuntimeError(f"Redis did not respond at {redis_url}")
    except redis.RedisError as exc:
        raise RuntimeError(
            f"Cannot connect to Redis at {redis_url}: {exc}. "
            "Default Compose does NOT publish Redis to the host. Use the host-deps overlay:\n"
            "  docker compose -f docker-compose.yml -f docker-compose.host-deps.yml "
            "up -d mongo redis weaviate bootstrap\n"
            "Then set ASKAI_REDIS_URL if the host/port differs.\n"
            "If you only need chat-api/admin-api (no document worker), use:\n"
            "  python -m services --only chat-api --skip-redis-check\n"
            "  (add admin-api to --only as needed; document-parser requires Redis.)"
        ) from exc


def _ensure_env_var(env: dict[str, str], key: str, value: str) -> None:
    """Set ``key`` when missing or blank so empty placeholder ``.env`` lines do not win."""
    if not str(env.get(key, "")).strip():
        env[key] = value


def build_base_env(
    shared_auth: dict[str, str],
    *,
    chat_port: int,
    admin_port: int,
    doc_port: int,
    redis_url: str,
    mongodb_uri: str,
    mongodb_db: str,
    weaviate_endpoint: str,
) -> dict[str, str]:
    """Merge process environment with development defaults shared by all backends."""
    env = os.environ.copy()
    env.update(shared_auth)
    _ensure_env_var(env, "PYTHONUTF8", "1")
    _ensure_env_var(env, "PYTHONIOENCODING", "utf-8")
    _ensure_env_var(env, "ASKAI_ADMIN_APP_ENV", "development")
    _ensure_env_var(
        env,
        "ASKAI_ADMIN_DOCUMENT_PROCESSING_BASE_URL",
        f"http://127.0.0.1:{doc_port}",
    )
    _ensure_env_var(
        env,
        "ASKAI_ADMIN_ADMIN_API_PUBLIC_BASE_URL",
        f"http://127.0.0.1:{admin_port}",
    )
    _ensure_env_var(env, "ASKAI_DOC_PROCESSING_REDIS_URL", redis_url)
    _ensure_env_var(env, "MOVO_DOC_PROCESSING_REDIS_URL", redis_url)
    _ensure_env_var(env, "ASKAI_ADMIN_REDIS_URL", redis_url)
    _ensure_env_var(env, "ADMIN_API_BASE_URL", f"http://127.0.0.1:{admin_port}")
    _ensure_env_var(env, "DOCUMENT_PROCESSING_BASE_URL", f"http://127.0.0.1:{doc_port}")
    _ensure_env_var(env, "BACKEND_INTERNAL_BASE_URL", f"http://127.0.0.1:{chat_port}")
    _ensure_env_var(env, "ASKAI_ADMIN_BACKEND_BASE_URL", f"http://127.0.0.1:{chat_port}")

    _ensure_env_var(env, "MONGODB_URI", mongodb_uri)
    _ensure_env_var(env, "MONGODB_DB", mongodb_db)
    _ensure_env_var(env, "ASKAI_ADMIN_MONGODB_URI", mongodb_uri)
    _ensure_env_var(env, "ASKAI_ADMIN_MONGODB_DB", mongodb_db)
    _ensure_env_var(env, "MOVO_DOC_PROCESSING_MONGODB_URI", mongodb_uri)
    _ensure_env_var(env, "MOVO_DOC_PROCESSING_MONGODB_DB", mongodb_db)

    _ensure_env_var(env, "ASKAI_ADMIN_WEAVIATE_ENDPOINT", weaviate_endpoint)
    _ensure_env_var(env, "MOVO_DOC_PROCESSING_WEAVIATE_ENDPOINT", weaviate_endpoint)

    jwt_secret = shared_auth.get("ASKAI_ADMIN_JWT_SECRET", "")
    if jwt_secret:
        _ensure_env_var(env, "END_USER_AUTH_SECRET", jwt_secret)
        _ensure_env_var(env, "JWT_SECRET", jwt_secret)

    _ensure_env_var(env, "DSH_RUNTIME_HOST_URL", "http://127.0.0.1:8101")
    dsh_callback = os.environ.get("MOVO_DSH_CALLBACK_HOST", "").strip()
    if not dsh_callback and sys.platform == "win32":
        dsh_callback = "host.docker.internal"
    if dsh_callback.lower() in {"off", "disabled", "127.0.0.1", "localhost"}:
        dsh_callback = "127.0.0.1"
    elif not dsh_callback:
        dsh_callback = "127.0.0.1"
    dsh_base = f"http://{dsh_callback}:{chat_port}"
    env["DSH_MODEL_GATEWAY_URL"] = f"{dsh_base}/internal/dsh/model/generate"
    env["DSH_TOOL_GATEWAY_URL"] = f"{dsh_base}/internal/dsh/tools"
    if dsh_callback == "host.docker.internal":
        logger.info(
            f"DSH gateway URLs use host.docker.internal:{chat_port} "
            f"(Docker DSH → host chat-api). Set MOVO_DSH_CALLBACK_HOST=127.0.0.1 if DSH runs on the host."
        )
    return env


def _popen_kwargs() -> dict:
    """Platform-specific subprocess options for graceful shutdown."""
    kwargs: dict = {}
    if sys.platform == "win32":
        kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP  # type: ignore[attr-defined]
    return kwargs


def start_uvicorn(
    *,
    name: str,
    service_dir: Path,
    python: Path,
    port: int,
    env: dict[str, str],
    reload: bool,
) -> subprocess.Popen[bytes]:
    """Start a FastAPI service with uvicorn."""
    cmd = [
        str(python),
        "-m",
        "uvicorn",
        "app.main:app",
        "--host",
        "127.0.0.1",
        "--port",
        str(port),
    ]
    if reload:
        cmd.extend(
            [
                "--reload",
                "--reload-dir",
                "app",
                "--reload-exclude",
                "backend.log",
                "--reload-exclude",
                "static/*",
                "--reload-exclude",
                "*.pyc",
                "--reload-exclude",
                "__pycache__/*",
            ]
        )
        if name == "chat-api":
            cmd.extend(
                [
                    "--timeout-graceful-shutdown",
                    os.environ.get("BACKEND_GRACEFUL_SHUTDOWN_SECONDS", "5"),
                ]
            )
    child_env = env.copy()
    child_env["PYTHONPATH"] = str(service_dir.resolve())
    logger.info(f"Starting {name} on http://127.0.0.1:{port} ...")
    process = subprocess.Popen(
        cmd,
        cwd=service_dir,
        env=child_env,
        **_popen_kwargs(),
    )
    return process


def resolve_celery_worker_pool(explicit: str | None = None) -> str | None:
    """
    Return Celery ``--pool`` value for the document worker.

    Celery's default prefork pool uses ``billiard`` and fails on Windows
    (PermissionError on shared semaphores). Use ``solo`` locally on Windows;
    on Linux/macOS omit the flag so Celery keeps its default prefork pool.
    """
    if explicit:
        return explicit
    override = os.environ.get("MOVO_CELERY_WORKER_POOL") or os.environ.get("CELERY_WORKER_POOL")
    if override:
        return override
    if sys.platform == "win32":
        return "solo"
    return None


def start_document_worker(
    *,
    python: Path,
    env: dict[str, str],
    queue: str,
    celery_pool: str | None = None,
) -> subprocess.Popen[bytes]:
    """Start the document-parser Celery worker."""
    pool = resolve_celery_worker_pool(celery_pool)
    cmd = [
        str(python),
        "-m",
        "celery",
        "-A",
        "app.workers.celery_app:celery_app",
        "worker",
        "--loglevel=info",
        f"--queues={queue}",
    ]
    if pool:
        cmd.append(f"--pool={pool}")
    child_env = env.copy()
    child_env["PYTHONPATH"] = str(DOCUMENT_PARSER_DIR.resolve())
    pool_label = pool or "prefork (default)"
    logger.info(f"Starting document-parser Celery worker (queue={queue}, pool={pool_label}) ...")
    return subprocess.Popen(
        cmd,
        cwd=DOCUMENT_PARSER_DIR,
        env=child_env,
        **_popen_kwargs(),
    )


def shutdown_children(_signum: int | None = None, _frame: object | None = None) -> None:
    """Terminate all child processes started by this launcher."""
    global _shutting_down
    if _shutting_down:
        return
    _shutting_down = True
    logger.info("Stopping backend services ...")
    for process in _processes:
        if process.poll() is None:
            process.terminate()
    deadline = time.time() + 10
    for process in _processes:
        if process.poll() is not None:
            continue
        remaining = deadline - time.time()
        if remaining > 0:
            try:
                process.wait(timeout=remaining)
            except subprocess.TimeoutExpired:
                process.kill()
        else:
            process.kill()
    _processes.clear()


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse CLI arguments for the backend launcher."""
    parser = argparse.ArgumentParser(
        description="Start MOVO backend services (chat-api, admin-api, document-parser).",
    )
    parser.add_argument("--chat-port", type=int, default=int(os.environ.get("BACKEND_PORT", DEFAULT_CHAT_PORT)))
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
    parser.add_argument(
        "--python",
        type=Path,
        default=None,
        help="Python executable (default: services/.venv or chat-api/venv)",
    )
    parser.add_argument(
        "--no-reload",
        action="store_true",
        help="Disable uvicorn autoreload (default on Windows)",
    )
    parser.add_argument(
        "--reload",
        action="store_true",
        help="Enable uvicorn autoreload (not recommended on Windows)",
    )
    parser.add_argument(
        "--skip-redis-check",
        action="store_true",
        help="Do not verify Redis before starting workers",
    )
    parser.add_argument(
        "--only",
        choices=("all", "chat-api", "admin-api", "document-parser", "document-worker"),
        default="all",
        help="Start a subset of processes (default: all)",
    )
    parser.add_argument(
        "--celery-pool",
        default=None,
        help="Celery worker pool (default: solo on Windows, prefork elsewhere). "
        "Override with MOVO_CELERY_WORKER_POOL.",
    )
    parser.add_argument(
        "--no-release-ports",
        action="store_true",
        help="Do not kill existing listeners on backend ports before start",
    )
    parser.add_argument(
        "--fail-if-port-busy",
        action="store_true",
        help="Do not auto-pick another chat-api port when the preferred port stays busy (Windows default: auto-pick)",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """
    Start configured backend processes and block until interrupted or a child exits.

    Run from repository root::

        python -m services

    Or with the unified venv::

        services/.venv/Scripts/python -m services
    """
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    args = parse_args(argv)
    python = args.python.resolve() if args.python else resolve_python_executable()
    if args.no_reload and args.reload:
        logger.error("Use only one of --no-reload and --reload")
        return 2
    if args.no_reload:
        reload = False
    elif args.reload:
        reload = True
    elif sys.platform == "win32":
        reload = False
        logger.info("Windows: uvicorn reload is off by default (pass --reload to enable)")
    else:
        reload = True

    auth_module = _load_auth_module()
    try:
        shared_auth = auth_module.prepare_internal_service_auth(REPO_ROOT)
    except RuntimeError as exc:
        logger.error(f"{exc}")
        return 1

    if not args.skip_redis_check and args.only in ("all", "document-parser", "document-worker"):
        try:
            ensure_redis_available(args.redis_url)
        except RuntimeError as exc:
            logger.error(f"{exc}")
            return 1

    if not args.no_release_ports:
        if args.only in ("all", "chat-api"):
            release_port(args.chat_port)
        if args.only in ("all", "admin-api"):
            release_port(args.admin_port)
        if args.only in ("all", "document-parser"):
            release_port(args.doc_port)

    skip_chat_api = False
    if args.only in ("all", "chat-api"):
        auto_fallback = sys.platform == "win32" and not args.fail_if_port_busy
        try:
            resolved = resolve_chat_listen_port(
                args.chat_port,
                auto_fallback=auto_fallback,
            )
        except RuntimeError as exc:
            logger.error(f"{exc}")
            return 1
        if resolved is None:
            skip_chat_api = True
        else:
            args.chat_port = resolved

    base_env = build_base_env(
        shared_auth,
        chat_port=args.chat_port,
        admin_port=args.admin_port,
        doc_port=args.doc_port,
        redis_url=args.redis_url,
        mongodb_uri=args.mongodb_uri,
        mongodb_db=args.mongodb_db,
        weaviate_endpoint=args.weaviate_endpoint,
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

    needs_dsh = args.only in ("all", "chat-api")
    if needs_dsh and not str(base_env.get("DSH_RUNTIME_HOST_TOKEN", "")).strip():
        logger.error(
            "DSH_RUNTIME_HOST_TOKEN is missing. Host chat-api must use the same token as "
            "Docker dsh-runtime-host.\n"
            "  docker compose -f docker-compose.yml -f docker-compose.host-deps.yml "
            "up -d bootstrap dsh-runtime-host\n"
            "  scripts/dev/sync_runtime_secrets.ps1\n"
            "Or restart run_backends.py (it will auto-sync from Docker when possible)."
        )
        return 1

    signal.signal(signal.SIGINT, shutdown_children)
    if hasattr(signal, "SIGTERM"):
        signal.signal(signal.SIGTERM, shutdown_children)

    starters: list[tuple[str, subprocess.Popen[bytes]]] = []
    only = args.only

    if only in ("all", "chat-api") and not skip_chat_api:
        starters.append(
            (
                "chat-api",
                start_uvicorn(
                    name="chat-api",
                    service_dir=CHAT_API_DIR,
                    python=python,
                    port=args.chat_port,
                    env=base_env,
                    reload=reload,
                ),
            )
        )
    if only in ("all", "admin-api"):
        starters.append(
            (
                "admin-api",
                start_uvicorn(
                    name="admin-api",
                    service_dir=ADMIN_API_DIR,
                    python=python,
                    port=args.admin_port,
                    env=base_env,
                    reload=reload,
                ),
            )
        )
    if only in ("all", "document-parser"):
        starters.append(
            (
                "document-parser",
                start_uvicorn(
                    name="document-parser",
                    service_dir=DOCUMENT_PARSER_DIR,
                    python=python,
                    port=args.doc_port,
                    env=base_env,
                    reload=reload,
                ),
            )
        )
    if only in ("all", "document-worker"):
        queue = os.environ.get("ASKAI_DOC_PROCESSING_CELERY_QUEUE", "document_processing")
        starters.append(
            (
                "document-worker",
                start_document_worker(
                    python=python,
                    env=base_env,
                    queue=queue,
                    celery_pool=args.celery_pool,
                ),
            )
        )

    _processes.extend(process for _, process in starters)

    logger.info("")
    logger.info("Backend services are starting:")
    if only in ("all", "chat-api"):
        if skip_chat_api:
            logger.info(f"  chat-api:          (already running) http://127.0.0.1:{args.chat_port}/docs")
        else:
            logger.info(f"  chat-api:          http://127.0.0.1:{args.chat_port}/docs")
    if only in ("all", "admin-api"):
        logger.info(f"  admin-api:         http://127.0.0.1:{args.admin_port}/docs")
        if args.admin_port == DEFAULT_ADMIN_PORT:
            logger.info(
                f"  admin-web (3100):  Vite proxies /admin-api → "
                f"http://127.0.0.1:{DEFAULT_ADMIN_PORT} (set VITE_ADMIN_API_TARGET if you use another port)"
            )
    if only in ("all", "document-parser"):
        logger.info(f"  document-parser:   http://127.0.0.1:{args.doc_port}/docs")
    if only in ("all", "document-worker"):
        logger.info(f"  document-worker:   Celery ({args.redis_url})")
    logger.info(f"  Python:            {python}")
    logger.info("")
    logger.info("Press Ctrl+C to stop.")

    if not starters:
        logger.info("Nothing new to start.")
        return 0

    try:
        while True:
            for name, process in starters:
                code = process.poll()
                if code is not None:
                    logger.error(f"{name} exited with code {code}")
                    shutdown_children()
                    return code if code is not None else 1
            time.sleep(0.5)
    except KeyboardInterrupt:
        shutdown_children()
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
