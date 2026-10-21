"""Persist locally answered Code questions in the bound conversation."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field

from app.api.endpoints.auth import _resolve_session_user
from app.core.db import get_db
from app.core.tenant import resolve_main_id
from app.dsh_runtime.bindings import KernelBindingRepository
from app.dsh_runtime.conversation.question_answers import record_question_answer

router = APIRouter(prefix="/desktop/dsh/sessions", tags=["desktop-question-answers"])


class QuestionAnswerReceipt(BaseModel):
    device_id: str = Field(min_length=1)
    message_id: str = Field(min_length=1, max_length=256)
    question_id: str = Field(min_length=1, max_length=256)
    questions: list[dict[str, Any]] = Field(min_length=1, max_length=20)
    answers: list[dict[str, Any]] = Field(min_length=1, max_length=20)


@router.post("/{kernel_session_id}/question-answers")
async def record_desktop_question_answer(
    kernel_session_id: str, payload: QuestionAnswerReceipt,
    authorization: str | None = Header(default=None),
) -> dict[str, bool]:
    resolved = await _resolve_session_user(authorization)
    tenant_id = resolve_main_id(resolved["main_id"])
    user_id = str(resolved["user"]["_id"])
    db = get_db()
    binding = await KernelBindingRepository(db).by_kernel_session(
        kernel_session_id, tenant_id=tenant_id, user_id=user_id,
    )
    if (not binding or not binding.get("current")
            or binding.get("execution_location") != "desktop"
            or binding.get("device_id") != payload.device_id):
        raise HTTPException(status_code=404, detail="code_session_not_found")
    active = binding.get("active_turn") or {}
    message_id = str(active.get("message_id") or "")
    if message_id != payload.message_id:
        raise HTTPException(status_code=409, detail="question_turn_changed")
    if len(payload.questions) != len(payload.answers):
        raise HTTPException(status_code=400, detail="question_answer_count_mismatch")
    await record_question_answer(
        db, tenant_id=tenant_id, user_id=user_id, message_id=message_id,
        question_id=payload.question_id, questions=payload.questions, answers=payload.answers,
    )
    return {"recorded": True}
