from urllib.parse import urlparse


def request_portal_origin(request) -> str | None:
    return request.headers.get("origin") or request.headers.get("referer")


def resolve_portal_base(configured: str, public_base: str, origin: str | None, request_base: str) -> str:
    """Use the local user portal for local admins and the configured portal in deployments."""
    origin_url = urlparse(origin or "")
    origin_host = origin_url.hostname
    configured_url = urlparse(configured.strip())
    if origin_host in {"localhost", "127.0.0.1"}:
        if configured_url.hostname in {"localhost", "127.0.0.1"}:
            return f"{configured_url.scheme}://{configured_url.netloc}"
        return f"{origin_url.scheme}://{origin_host}:3000"
    for candidate in (configured, public_base, origin or "", request_base):
        parsed = urlparse(candidate.strip())
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            continue
        if parsed.hostname in {"localhost", "127.0.0.1"}:
            continue
        return f"{parsed.scheme}://{parsed.netloc}"
    parsed = urlparse(configured or origin or request_base)
    return f"{parsed.scheme}://{parsed.netloc}"
