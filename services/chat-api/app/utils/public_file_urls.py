from urllib.parse import urlsplit, urlunsplit


def public_file_url(base_url: str, path: str) -> str:
    """Join a public origin/base path with a file route without repeating it."""
    base = str(base_url or "").strip().rstrip("/")
    if not base:
        return path
    parts = urlsplit(base)
    base_path = parts.path.rstrip("/")
    if base_path and (path == base_path or path.startswith(base_path + "/")):
        return urlunsplit((parts.scheme, parts.netloc, path, "", ""))
    return f"{base}{path}"


def normalize_legacy_file_urls(markdown: str, base_url: str, path_prefix: str) -> str:
    """Repair file URLs saved before overlapping base paths were handled."""
    base_path = urlsplit(str(base_url or "").strip()).path.rstrip("/")
    if not base_path or not path_prefix.startswith(base_path + "/"):
        return markdown
    return markdown.replace(f"{base_path}{path_prefix}/", f"{path_prefix}/")
