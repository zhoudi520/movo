from __future__ import annotations

import datetime
from typing import Any, Mapping


def snapshot_messages(
    rows: list[dict[str, Any]],
    *,
    authors: Mapping[str, Mapping[str, Any]] | None = None,
    owner_user_id: str = "",
) -> list[dict[str, Any]]:
    """Freeze conversation text without attaching local files or execution controls."""
    author_names = authors or {}
    messages = []
    for row in rows:
        if row.get("message_type") == "context_summary" or row.get("role") not in {"user", "assistant"}:
            continue
        role = str(row.get("role"))
        if role == "assistant":
            for entry in row.get("question_answers") or []:
                answers = {answer.get("id"): answer for answer in entry.get("answers") or []}
                lines = []
                for question in entry.get("questions") or []:
                    answer = answers.get(question.get("id")) or {}
                    values = [*answer.get("selected", []), answer.get("custom")]
                    lines.append(f"{question.get('question', '')}\n{', '.join(str(value) for value in values if value)}")
                if lines:
                    messages.append({
                        "role": "user", "content": "\n\n".join(lines),
                        "created_at": entry.get("created_at") or row.get("created_at"),
                        "author_name": str((author_names.get(str(entry.get("user_id") or owner_user_id)) or {}).get("display_name") or ""),
                    })
        item = {
            "role": str(row.get("role") or ""),
            "content": str(row.get("content") or ""),
            "created_at": row.get("created_at"),
        }
        if role == "user":
            user_id = str(row.get("user_id") or owner_user_id)
            item["author_name"] = str((author_names.get(user_id) or {}).get("display_name") or "")
        messages.append(item)
    return messages


def snapshot_active(doc: dict[str, Any], now: datetime.datetime) -> bool:
    expires = doc.get("expires_at")
    if not isinstance(expires, datetime.datetime) or doc.get("revoked_at") is not None:
        return False
    if expires.tzinfo is None:
        expires = expires.replace(tzinfo=datetime.timezone.utc)
    return expires > now
