from __future__ import annotations

import asyncio
from bson import ObjectId

from app.api.endpoints import desktop_question_answers as endpoint


def test_desktop_answer_is_bound_to_active_owner_and_device(monkeypatch):
    user_id = str(ObjectId())
    calls = []

    async def identity(_authorization):
        return {"main_id": "tenant", "user": {"_id": ObjectId(user_id)}}

    class Bindings:
        def __init__(self, _db):
            pass

        async def by_kernel_session(self, *_args, **_kwargs):
            return {
                "current": True, "execution_location": "desktop", "device_id": "device",
                "active_turn": {"message_id": "assistant-1", "status": "running"},
            }

    async def recorded(_db, **kwargs):
        calls.append(kwargs)

    monkeypatch.setattr(endpoint, "_resolve_session_user", identity)
    monkeypatch.setattr(endpoint, "get_db", lambda: object())
    monkeypatch.setattr(endpoint, "KernelBindingRepository", Bindings)
    monkeypatch.setattr(endpoint, "record_question_answer", recorded)
    payload = endpoint.QuestionAnswerReceipt(
        device_id="device", message_id="assistant-1", question_id="call-1",
        questions=[{"id": "q", "question": "Hours?"}],
        answers=[{"id": "q", "selected": ["5 hours"]}],
    )
    assert asyncio.run(endpoint.record_desktop_question_answer("kernel", payload, "Bearer token")) == {"recorded": True}
    assert calls[0]["message_id"] == "assistant-1"
    assert calls[0]["user_id"] == user_id
