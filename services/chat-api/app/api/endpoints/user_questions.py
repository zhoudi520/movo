"""Authenticated bridge for DSH's native human-question tool."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field

from app.services.end_user_session import resolve_session_user
from app.core.db import get_db
from app.core.tenant import resolve_main_id
from app.dsh_runtime.application import dsh_runtime_application
from app.dsh_runtime.bindings import KernelBindingRepository
from app.dsh_runtime.turn_cancellation import (
    CancelNotAllowedError,
    assert_run_initiator,
    member_conversation,
)
from app.dsh_runtime.conversation.participants_repository import SessionParticipantsRepository
from app.dsh_runtime.errors import DshRuntimeError
from app.dsh_runtime.conversation.question_answers import record_question_answer


router = APIRouter(prefix="/dsh/conversations", tags=["user-questions"])


class QuestionAnswer(BaseModel):
    id: str = Field(min_length=1)
    selected: list[str] = Field(default_factory=list)
    custom: str | None = None


class QuestionReply(BaseModel):
    answers: list[QuestionAnswer] = Field(min_length=1)


async def _owning_binding(conversation_id: str, authorization: str | None) -> dict[str, Any]:
    resolved = await resolve_session_user(authorization)
    tenant_id = resolve_main_id(resolved["main_id"])
    user_id = str(resolved["user"]["_id"])
    db = get_db()
    try:
        conversation = await member_conversation(
            db, SessionParticipantsRepository(db), conversation_id,
            tenant_id=tenant_id, user_id=user_id,
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail="session_not_found") from exc
    except CancelNotAllowedError as exc:
        raise HTTPException(status_code=403, detail="question_owner_required") from exc
    if not conversation.get("active_run"):
        raise HTTPException(status_code=404, detail="question_run_not_found")
    try:
        assert_run_initiator(conversation, conversation_id=conversation_id, user_id=user_id)
    except CancelNotAllowedError as exc:
        raise HTTPException(status_code=403, detail="question_owner_required") from exc
    binding = await KernelBindingRepository(db).current(conversation_id, tenant_id=tenant_id, user_id=user_id)
    if binding is None or binding.get("execution_location") != "server":
        raise HTTPException(status_code=404, detail="question_session_not_found")
    return {
        **binding, "_tenant_id": tenant_id, "_user_id": user_id,
        "_message_id": str(conversation["active_run"].get("message_id") or ""),
    }


def _question_path(binding: dict[str, Any], suffix: str = "") -> str:
    return (
        f"/v1/runtimes/{binding['runtime_id']}/sessions/"
        f"{binding['kernel_session_id']}/questions{suffix}"
    )


@router.get("/{conversation_id}/questions")
async def pending_questions(
    conversation_id: str,
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    binding = await _owning_binding(conversation_id, authorization)
    try:
        return await dsh_runtime_application.require_transport().request("GET", _question_path(binding))
    except DshRuntimeError as exc:
        raise HTTPException(status_code=503, detail="question_runtime_unavailable") from exc


@router.post("/{conversation_id}/questions/{question_id}/answer")
async def answer_question(
    conversation_id: str,
    question_id: str,
    payload: QuestionReply,
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    binding = await _owning_binding(conversation_id, authorization)
    if not question_id or "/" in question_id or len(question_id) > 256:
        raise HTTPException(status_code=400, detail="invalid_question_id")
    transport = dsh_runtime_application.require_transport()
    try:
        pending = await transport.request("GET", _question_path(binding))
        item = next((row for row in pending.get("questions", []) if row.get("id") == question_id), None)
        receipt = await transport.request(
            "POST", _question_path(binding, f"/{question_id}/answer"),
            json=payload.model_dump(exclude_none=True),
        )
    except DshRuntimeError as exc:
        raise HTTPException(status_code=409, detail="question_no_longer_pending") from exc
    if not receipt.get("answered") or not binding["_message_id"]:
        raise HTTPException(status_code=409, detail="question_answer_not_accepted")
    questions = receipt.get("questions") or (item or {}).get("questions")
    if not questions:
        raise HTTPException(status_code=409, detail="question_snapshot_unavailable")
    await record_question_answer(
        get_db(), tenant_id=binding["_tenant_id"], user_id=binding["_user_id"],
        message_id=binding["_message_id"], question_id=question_id,
        questions=questions, answers=receipt.get("answers") or payload.model_dump(exclude_none=True)["answers"],
    )
    return {"answered": True, "questionId": question_id}
