from __future__ import annotations

from urllib.parse import urlsplit, urlunsplit

from fastapi import HTTPException, Request

from app.core.config import get_settings


def portal_link(request: Request, token: str, *, snapshot: bool = False) -> str:
    configured = str(get_settings().USER_PORTAL_BASE_URL or "").strip()
    origin = configured or str(request.headers.get("origin") or "").strip()
    parsed = urlsplit(origin)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise HTTPException(status_code=409, detail={
            "code": "session_share_portal_unconfigured",
            "message": "Configure USER_PORTAL_BASE_URL for desktop sharing",
        })
    key = "session-snapshot" if snapshot else "session-share"
    return urlunsplit((parsed.scheme, parsed.netloc, "/", f"{key}={token}", ""))
