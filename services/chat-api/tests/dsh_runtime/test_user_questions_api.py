from __future__ import annotations

import asyncio
from bson import ObjectId
from fastapi import HTTPException
import pytest

from app.api.endpoints import user_questions as endpoint


class _Transport:
    def __init__(self) -> None:
        self.calls = []

    async def request(self, method, path, *, json=None):
        self.calls.append((method, path, json))
        return {"questions": [{"id": "call", "questions": [{"id": "q", "question": "Which?"}]}]} if method == "GET" else {"answered": True}


def test_question_bridge_uses_current_binding_and_structured_answers(monkeypatch):
    user_id = str(ObjectId())
    conversation_id = str(ObjectId())
    transport = _Transport()

    async def identity(_authorization):
        return {"main_id": "tenant", "user": {"_id": ObjectId(user_id)}}

    async def conversation(_db, _participants, _conversation_id, **_kwargs):
        return {"active_run": {"initiator_user_id": user_id, "message_id": "assistant-turn"}}

    class Bindings:
        def __init__(self, _db):
            pass

        async def current(self, *_args, **_kwargs):
            return {"execution_location": "server", "runtime_id": "runtime", "kernel_session_id": "kernel"}

    monkeypatch.setattr(endpoint, "resolve_session_user", identity)
    monkeypatch.setattr(endpoint, "member_conversation", conversation)
    monkeypatch.setattr(endpoint, "get_db", lambda: object())
    monkeypatch.setattr(endpoint, "SessionParticipantsRepository", lambda _db: object())
    monkeypatch.setattr(endpoint, "KernelBindingRepository", Bindings)
    monkeypatch.setattr(endpoint.dsh_runtime_application, "require_transport", lambda: transport)
    recorded_calls = []
    async def recorded(*_args, **kwargs):
        recorded_calls.append(kwargs)
        return {}
    monkeypatch.setattr(endpoint, "record_question_answer", recorded)

    assert asyncio.run(endpoint.pending_questions(conversation_id, "Bearer token")) == {"questions": [{"id": "call", "questions": [{"id": "q", "question": "Which?"}]}]}
    reply = endpoint.QuestionReply(answers=[endpoint.QuestionAnswer(id="q", selected=["A"])])
    assert asyncio.run(endpoint.answer_question(conversation_id, "call", reply, "Bearer token")) == {"answered": True, "questionId": "call"}
    assert recorded_calls[0]["questions"] == [{"id": "q", "question": "Which?"}]
    assert recorded_calls[0]["answers"] == [{"id": "q", "selected": ["A"]}]
    assert transport.calls == [
        ("GET", "/v1/runtimes/runtime/sessions/kernel/questions", None),
        ("GET", "/v1/runtimes/runtime/sessions/kernel/questions", None),
        ("POST", "/v1/runtimes/runtime/sessions/kernel/questions/call/answer", {"answers": [{"id": "q", "selected": ["A"]}]}),
    ]


def test_other_shared_member_cannot_answer(monkeypatch):
    async def identity(_authorization):
        return {"main_id": "tenant", "user": {"_id": ObjectId()}}

    async def conversation(_db, _participants, _conversation_id, **_kwargs):
        return {"active_run": {"initiator_user_id": "someone-else"}}

    monkeypatch.setattr(endpoint, "resolve_session_user", identity)
    monkeypatch.setattr(endpoint, "member_conversation", conversation)
    monkeypatch.setattr(endpoint, "get_db", lambda: object())
    monkeypatch.setattr(endpoint, "SessionParticipantsRepository", lambda _db: object())
    with pytest.raises(HTTPException) as error:
        asyncio.run(endpoint.pending_questions(str(ObjectId()), "Bearer token"))
    assert error.value.status_code == 403


def test_completed_run_has_no_answerable_question(monkeypatch):
    async def identity(_authorization):
        return {"main_id": "tenant", "user": {"_id": ObjectId()}}

    async def conversation(_db, _participants, _conversation_id, **_kwargs):
        return {}

    monkeypatch.setattr(endpoint, "resolve_session_user", identity)
    monkeypatch.setattr(endpoint, "member_conversation", conversation)
    monkeypatch.setattr(endpoint, "get_db", lambda: object())
    monkeypatch.setattr(endpoint, "SessionParticipantsRepository", lambda _db: object())
    with pytest.raises(HTTPException) as error:
        asyncio.run(endpoint.pending_questions(str(ObjectId()), "Bearer token"))
    assert error.value.status_code == 404
