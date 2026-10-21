from __future__ import annotations

import asyncio

from app.dsh_runtime.conversation.question_answers import record_question_answer


class _Messages:
    def __init__(self):
        self.entries = []

    async def update_one(self, query, update):
        found = not any(row["id"] == query["question_answers.id"]["$ne"] for row in self.entries)
        if found:
            self.entries.append(update["$push"]["question_answers"])
        return type("Result", (), {"matched_count": int(found)})()

    async def find_one(self, _scope, _projection):
        return {"question_answers": self.entries}


def test_record_question_answer_is_idempotent():
    messages = _Messages()
    db = type("DB", (), {"chat_messages": messages})()
    args = dict(tenant_id="tenant", message_id="assistant", user_id="alice",
                question_id="call", questions=[{"id": "q", "question": "Goal?"}],
                answers=[{"id": "q", "selected": ["A"]}])
    first = asyncio.run(record_question_answer(db, **args))
    second = asyncio.run(record_question_answer(db, **args))
    assert first == second
    assert len(messages.entries) == 1
