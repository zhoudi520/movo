from datetime import datetime, timedelta, timezone

from starlette.requests import Request

from app.services.session_sharing.links import portal_link
from app.services.session_sharing.snapshot import snapshot_active, snapshot_messages


def test_snapshot_freezes_only_conversation_text():
    rows = [
        {"role": "user", "content": "question", "created_at": None},
        {"role": "assistant", "content": "answer", "execution_events": [{"command": "secret"}]},
        {"role": "system", "content": "hidden"},
        {"role": "assistant", "content": "context", "message_type": "context_summary"},
    ]
    assert snapshot_messages(rows, authors={"owner": {"display_name": "Alice"}}, owner_user_id="owner") == [
        {"role": "user", "content": "question", "created_at": None, "author_name": "Alice"},
        {"role": "assistant", "content": "answer", "created_at": None},
    ]


def test_snapshot_preserves_distinct_shared_message_authors():
    rows = [
        {"role": "user", "user_id": "alice", "content": "first"},
        {"role": "assistant", "content": "reply"},
        {"role": "user", "user_id": "bob", "content": "second"},
    ]
    authors = {"alice": {"display_name": "Alice"}, "bob": {"display_name": "Bob"}}
    result = snapshot_messages(rows, authors=authors, owner_user_id="alice")
    assert [message.get("author_name") for message in result] == ["Alice", None, "Bob"]


def test_snapshot_expiry_and_revocation():
    now = datetime.now(timezone.utc)
    assert snapshot_active({"expires_at": now + timedelta(days=1), "revoked_at": None}, now)
    assert not snapshot_active({"expires_at": now - timedelta(seconds=1), "revoked_at": None}, now)
    assert not snapshot_active({"expires_at": now + timedelta(days=1), "revoked_at": now}, now)


def test_portal_link_uses_public_origin(monkeypatch):
    class Settings:
        USER_PORTAL_BASE_URL = "https://movo.example.com/"

    monkeypatch.setattr("app.services.session_sharing.links.get_settings", lambda: Settings())
    request = Request({"type": "http", "headers": [(b"origin", b"http://localhost:3000")]})
    assert portal_link(request, "abc", snapshot=True) == "https://movo.example.com/?session-snapshot=abc"
