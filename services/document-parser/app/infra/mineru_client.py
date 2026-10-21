"""MinerU document parsing client (config supplied per job)."""

from __future__ import annotations

import io
import logging
import re
import time
import zipfile
from pathlib import Path
from urllib.parse import urlparse, urlunparse

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)

MINERU_EXTENSIONS = {
    ".pdf",
    ".doc",
    ".docx",
    ".ppt",
    ".pptx",
    ".xls",
    ".xlsx",
    ".png",
    ".jpg",
    ".jpeg",
    ".webp",
    ".gif",
    ".bmp",
    ".html",
    ".htm",
}


def normalize_api_root(service_url: str) -> str:
    """Normalize MinerU service URL to API v4 root."""
    value = (service_url or "").strip().rstrip("/")
    if not value:
        return ""
    for suffix in ("/extract/task", "/file-urls/batch", "/extract-results/batch"):
        if value.endswith(suffix):
            return value[: -len(suffix)]
    return value


def supports_mineru(path: Path | str) -> bool:
    """Return True when file extension is supported by MinerU."""
    return Path(path).suffix.lower() in MINERU_EXTENSIONS


def _headers(api_key: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json", "Accept": "*/*"}


def _safe_data_id(name: str) -> str:
    stem = Path(name).stem[:120]
    cleaned = re.sub(r"[^A-Za-z0-9_.-]+", "_", stem).strip("._-")
    return (cleaned or "file")[:128]


def _model_version_for(path_or_name: str, default: str) -> str:
    ext = Path(path_or_name).suffix.lower()
    if ext in {".html", ".htm"}:
        return "MinerU-HTML"
    return default or "vlm"


_MD_IMAGE_RE = re.compile(r"(!\[[^\]]*\]\()([^)]+)(\))")
_HTML_IMAGE_RE = re.compile(r'(<img\b[^>]*\bsrc=["\'])([^"\']+)(["\'])', re.IGNORECASE)


def _is_relative_image_ref(src: str) -> bool:
    """Return True when the image src is a relative path inside the MinerU zip."""
    value = (src or "").strip().replace("\\", "/")
    if not value or value.startswith(("http://", "https://", "data:", "/")):
        return False
    name = Path(value).name.lower()
    return name.endswith((".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".jp2"))


def _resolve_zip_member(names: list[str], relative_src: str, md_dir: str) -> str | None:
    """Locate a zip member for a markdown-relative image path."""
    rel = relative_src.strip().replace("\\", "/").lstrip("./")
    candidates = [
        f"{md_dir}/{rel}" if md_dir else rel,
        rel,
        f"images/{Path(rel).name}",
        Path(rel).name,
    ]
    normalized = {n.replace("\\", "/"): n for n in names}
    for cand in candidates:
        key = cand.replace("\\", "/")
        if key in normalized:
            return normalized[key]
        for n_key, n_raw in normalized.items():
            if n_key.endswith("/" + key) or n_key.endswith(key):
                return n_raw
    return None


def _decode_markdown_bytes(content: bytes) -> str:
    """Decode markdown bytes with common encodings."""
    for encoding in ("utf-8", "utf-8-sig", "gbk"):
        try:
            return content.decode(encoding)
        except UnicodeDecodeError:
            continue
    return content.decode("utf-8", errors="ignore")


def _extract_full_md_from_zip(zip_bytes: bytes) -> str:
    """Extract primary markdown from MinerU result zip."""
    markdown, _assets = extract_markdown_and_assets_from_zip(zip_bytes)
    return markdown


def extract_markdown_and_assets_from_zip(zip_bytes: bytes) -> tuple[str, dict[str, bytes]]:
    """
    Extract markdown and embedded image bytes from a MinerU result zip.

    Image refs in markdown are rewritten to ``assets/{name}`` paths relative to parsed.md.

    Returns:
        Tuple of (markdown text, mapping of relative asset path -> file bytes).
    """
    assets: dict[str, bytes] = {}
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        names = zf.namelist()
        candidates = [n for n in names if n.replace("\\", "/").endswith("full.md")]
        if not candidates:
            md_files = [n for n in names if n.replace("\\", "/").lower().endswith(".md")]
            if md_files:
                candidates = sorted(md_files, key=lambda n: (-len(n), n.count("/")))
                logger.info(f"MinerU zip 未含 full.md，回退使用: {candidates[0]}")
            else:
                raise RuntimeError(f"结果压缩包中未找到 markdown，文件列表={names[:20]}")
        candidates.sort(key=lambda n: (n.count("/"), len(n)))
        md_member = candidates[0]
        text = _decode_markdown_bytes(zf.read(md_member))
        md_dir = str(Path(md_member.replace("\\", "/")).parent).replace("\\", "/")
        if md_dir == ".":
            md_dir = ""

        def _replace_src(src: str) -> str:
            raw = src.strip()
            if not _is_relative_image_ref(raw):
                return raw
            member = _resolve_zip_member(names, raw, md_dir)
            if not member:
                logger.warning(f"MinerU zip 中未找到图片: src={raw}")
                return raw
            try:
                content = zf.read(member)
            except Exception as exc:
                logger.warning(f"MinerU zip 读取图片失败: src={raw}, error={exc}")
                return raw
            rel_name = Path(member.replace("\\", "/")).name
            rel_key = f"assets/{rel_name}"
            assets[rel_key] = content
            return rel_key

        text = _MD_IMAGE_RE.sub(lambda m: f"{m.group(1)}{_replace_src(m.group(2))}{m.group(3)}", text)
        text = _HTML_IMAGE_RE.sub(
            lambda m: f"{m.group(1)}{_replace_src(m.group(2))}{m.group(3)}",
            text,
        )
        return text, assets


def _relay_request_url(original: str, relay_base: str) -> tuple[str, dict[str, str]]:
    """
    Swap OSS/CDN URL origin to a relay entry while preserving upstream Host.

    Args:
        original: Full URL from MinerU (OSS/CDN).
        relay_base: Relay gateway base URL.

    Returns:
        Tuple of (request_url, extra_headers).
    """
    raw = str(original or "").strip()
    base = str(relay_base or "").strip().rstrip("/")
    if not raw or not base:
        return raw, {}
    orig = urlparse(raw)
    relay = urlparse(base)
    if not orig.scheme or not orig.netloc or not relay.scheme or not relay.netloc:
        return raw, {}
    req_url = urlunparse((relay.scheme, relay.netloc, orig.path, orig.params, orig.query, orig.fragment))
    upstream_host = (orig.hostname or "").strip()
    headers = {"Host": upstream_host} if upstream_host else {}
    return req_url, headers


def _http_get_with_retries(
    url: str,
    *,
    relay_base: str = "",
    timeout: httpx.Timeout | None = None,
    max_attempts: int | None = None,
) -> bytes:
    """
    Download bytes from URL with retries (handles transient SSL / connection drops).

    Args:
        url: Target URL.
        relay_base: Optional CDN/OSS relay base.
        timeout: httpx timeout; defaults to long read for zip packages.
        max_attempts: Retry count.

    Returns:
        Response body bytes.
    """
    attempts = max(1, int(max_attempts or settings.mineru_zip_download_retries or 4))
    read_timeout = httpx.Timeout(60.0, connect=30.0, read=600.0) if timeout is None else timeout
    last_error: Exception | None = None
    for attempt in range(1, attempts + 1):
        req_url, extra_headers = _relay_request_url(url, relay_base)
        if relay_base and req_url != url:
            logger.info(f"MinerU GET 经中继: attempt={attempt}, url={req_url}")
        try:
            with httpx.Client(timeout=read_timeout, follow_redirects=True) as client:
                response = client.get(req_url, headers=extra_headers or None)
                response.raise_for_status()
                return response.content
        except (httpx.ConnectError, httpx.ReadError, httpx.RemoteProtocolError, httpx.HTTPError) as exc:
            last_error = exc
            logger.warning(f"MinerU 下载失败，准备重试: attempt={attempt}, error={exc}")
            if attempt < attempts:
                time.sleep(min(2**attempt, 20))
    raise RuntimeError(f"下载 MinerU 结果包失败: {last_error}") from last_error


def _http_put_with_retries(
    url: str,
    *,
    content: bytes,
    relay_base: str = "",
    timeout: httpx.Timeout | None = None,
    max_attempts: int | None = None,
) -> None:
    """
    PUT file bytes to presigned URL with optional relay and retries.

    Args:
        url: Presigned upload URL.
        content: File bytes.
        relay_base: Optional OSS upload relay base.
        timeout: httpx timeout.
        max_attempts: Retry count.
    """
    attempts = max(1, int(max_attempts or settings.mineru_zip_download_retries or 4))
    put_timeout = httpx.Timeout(120.0, connect=30.0, read=300.0) if timeout is None else timeout
    last_error: Exception | None = None
    for attempt in range(1, attempts + 1):
        req_url, extra_headers = _relay_request_url(url, relay_base)
        if relay_base and req_url != url:
            logger.info(f"MinerU PUT 经中继: attempt={attempt}, url={req_url}")
        try:
            with httpx.Client(timeout=put_timeout, follow_redirects=True) as client:
                response = client.put(req_url, content=content, headers=extra_headers or None)
                if response.status_code in {200, 201}:
                    return
                raise RuntimeError(f"文件上传失败: HTTP {response.status_code}")
        except (httpx.ConnectError, httpx.ReadError, httpx.RemoteProtocolError, httpx.HTTPError, RuntimeError) as exc:
            last_error = exc
            logger.warning(f"MinerU 上传失败，准备重试: attempt={attempt}, error={exc}")
            if attempt < attempts:
                time.sleep(min(2**attempt, 20))
    raise RuntimeError(f"MinerU 文件上传失败: {last_error}") from last_error


def _poll_batch_until_done(client: httpx.Client, *, root: str, api_key: str, batch_id: str) -> dict:
    """Poll MinerU batch API until the first file reaches done or failed."""
    poll_url = f"{root.rstrip('/')}/extract-results/batch/{batch_id}"
    interval = max(1, int(settings.mineru_poll_interval_sec or 3))
    deadline = time.time() + max(30, int(settings.mineru_poll_timeout_sec or 300))
    last_state = ""
    while time.time() < deadline:
        poll = client.get(poll_url, headers=_headers(api_key))
        poll.raise_for_status()
        poll_body = poll.json()
        if poll_body.get("code") != 0:
            raise RuntimeError(f"查询解析结果失败: {poll_body.get('msg')}")
        results = (poll_body.get("data") or {}).get("extract_result") or []
        if not results:
            time.sleep(interval)
            continue
        item = results[0]
        state = (item.get("state") or "").lower()
        if state != last_state:
            logger.info(f"MinerU 任务状态: batch_id={batch_id}, state={state}")
            last_state = state
        if state == "done":
            return item
        if state == "failed":
            raise RuntimeError(f"MinerU 解析失败: {item.get('err_msg') or 'unknown'}")
        time.sleep(interval)
    raise TimeoutError(f"MinerU 解析超时: batch_id={batch_id}, last_state={last_state}")


def extract_markdown_with_mineru(
    path: Path,
    *,
    service_url: str,
    api_key: str,
    model_version: str = "vlm",
    language: str = "ch",
) -> str:
    """
    Parse a local file with MinerU and return markdown text.

    Args:
        path: Local file path.
        service_url: MinerU API base URL.
        api_key: MinerU API key.
        model_version: MinerU model version.
        language: Document language hint.

    Returns:
        Markdown content string.
    """
    if not service_url or not api_key:
        raise RuntimeError("MinerU serviceUrl/apiKey 未配置")
    if not path.is_file():
        raise FileNotFoundError(f"文件不存在: {path}")
    if not supports_mineru(path):
        raise ValueError(f"MinerU 不支持的文件类型: {path.suffix}")

    root = normalize_api_root(service_url)
    model = _model_version_for(path.name, model_version)
    timeout = httpx.Timeout(120.0, connect=30.0)
    with httpx.Client(timeout=timeout, follow_redirects=True) as client:
        apply_url = f"{root.rstrip('/')}/file-urls/batch"
        payload = {
            "files": [{"name": path.name, "data_id": _safe_data_id(path.name)}],
            "model_version": model,
            "enable_formula": True,
            "enable_table": True,
            "language": language or "ch",
        }
        resp = client.post(apply_url, headers=_headers(api_key), json=payload)
        resp.raise_for_status()
        body = resp.json()
        if body.get("code") != 0:
            raise RuntimeError(f"申请上传链接失败: {body.get('msg')}")
        data = body.get("data") or {}
        batch_id = data.get("batch_id")
        file_urls = data.get("file_urls") or []
        if not batch_id or not file_urls:
            raise RuntimeError("申请上传链接返回异常")
        upload_url = str(file_urls[0])
        oss_relay = str(settings.mineru_oss_upload_relay_url or "").strip()
        file_bytes = path.read_bytes()
        if oss_relay:
            _http_put_with_retries(upload_url, content=file_bytes, relay_base=oss_relay)
        else:
            _http_put_with_retries(upload_url, content=file_bytes)
        item = _poll_batch_until_done(client, root=root, api_key=api_key, batch_id=str(batch_id))
        zip_url = str(item.get("full_zip_url") or "").strip()
        if not zip_url:
            raise RuntimeError("解析完成但缺少 full_zip_url")
        cdn_relay = str(settings.mineru_cdn_download_relay_url or "").strip()
        zip_bytes = _http_get_with_retries(zip_url, relay_base=cdn_relay)
        markdown, _assets = extract_markdown_and_assets_from_zip(zip_bytes)
        return markdown


def extract_markdown_and_assets_with_mineru(
    path: Path,
    *,
    service_url: str,
    api_key: str,
    model_version: str = "vlm",
    language: str = "ch",
) -> tuple[str, dict[str, bytes]]:
    """
    Parse a local file with MinerU and return markdown plus embedded image bytes.

    Returns:
        Tuple of (markdown, assets map keyed by paths like ``assets/foo.png``).
    """
    if not service_url or not api_key:
        raise RuntimeError("MinerU serviceUrl/apiKey 未配置")
    if not path.is_file():
        raise FileNotFoundError(f"文件不存在: {path}")
    if not supports_mineru(path):
        raise ValueError(f"MinerU 不支持的文件类型: {path.suffix}")

    root = normalize_api_root(service_url)
    model = _model_version_for(path.name, model_version)
    timeout = httpx.Timeout(120.0, connect=30.0)
    with httpx.Client(timeout=timeout, follow_redirects=True) as client:
        apply_url = f"{root.rstrip('/')}/file-urls/batch"
        payload = {
            "files": [{"name": path.name, "data_id": _safe_data_id(path.name)}],
            "model_version": model,
            "enable_formula": True,
            "enable_table": True,
            "language": language or "ch",
        }
        resp = client.post(apply_url, headers=_headers(api_key), json=payload)
        resp.raise_for_status()
        body = resp.json()
        if body.get("code") != 0:
            raise RuntimeError(f"申请上传链接失败: {body.get('msg')}")
        data = body.get("data") or {}
        batch_id = data.get("batch_id")
        file_urls = data.get("file_urls") or []
        if not batch_id or not file_urls:
            raise RuntimeError("申请上传链接返回异常")
        upload_url = str(file_urls[0])
        oss_relay = str(settings.mineru_oss_upload_relay_url or "").strip()
        file_bytes = path.read_bytes()
        if oss_relay:
            _http_put_with_retries(upload_url, content=file_bytes, relay_base=oss_relay)
        else:
            _http_put_with_retries(upload_url, content=file_bytes)
        item = _poll_batch_until_done(client, root=root, api_key=api_key, batch_id=str(batch_id))
        zip_url = str(item.get("full_zip_url") or "").strip()
        if not zip_url:
            raise RuntimeError("解析完成但缺少 full_zip_url")
        cdn_relay = str(settings.mineru_cdn_download_relay_url or "").strip()
        zip_bytes = _http_get_with_retries(zip_url, relay_base=cdn_relay)
        return extract_markdown_and_assets_from_zip(zip_bytes)
