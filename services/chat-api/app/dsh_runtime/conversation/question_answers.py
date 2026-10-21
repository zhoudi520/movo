"""Durable, turn-scoped answers to DSH human questions."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.dsh_runtime.events.persistence_retry import retry_persistence


async def record_question_answer(
    db: Any, *, tenant_id: str, message_id: str, user_id: str,
    question_id: str, questions: list[dict[str, Any]], answers: list[dict[str, Any]],
) -> dict[str, Any]:
    """Append once to the assistant turn, which already owns execution history.

    Keeping this with the turn lets the UI place the user's reply before that
    turn's final answer without changing the session's immutable message seqs.
    """
    entry = {
        "id": question_id,
        "user_id": user_id,
        "questions": questions,
        "answers": answers,
        "created_at": datetime.now(timezone.utc),
    }
    scope = {"main_id": tenant_id, "message_id": message_id, "role": "assistant"}
    async def persist() -> dict[str, Any]:
        result = await db.chat_messages.update_one(
            {**scope, "question_answers.id": {"$ne": question_id}},
            {"$push": {"question_answers": entry}},
        )
        if not result.matched_count:
            row = await db.chat_messages.find_one(scope, {"question_answers": 1})
            if row is None:
                raise LookupError("assistant_message_not_found")
            for existing in row.get("question_answers") or []:
                if existing.get("id") == question_id:
                    return existing
            raise LookupError("question_answer_not_recorded")
        return entry

    return await retry_persistence(
        persist, stage="question_answer", context={"message_id": message_id},
    )
