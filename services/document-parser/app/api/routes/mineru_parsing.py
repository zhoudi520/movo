from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status

from app.core.config import settings
from app.core.security import verify_service_token
from app.domain.jobs import MineruParseJobRequest, MineruParseJobResponse
from app.repositories.job_repository import create_job, mark_job_failed
from app.tasks.mineru_parsing import mineru_parse_task

router = APIRouter()


@router.post("/jobs/mineru-parse", status_code=status.HTTP_202_ACCEPTED)
async def create_mineru_parse_job(
    payload: MineruParseJobRequest,
    _: None = Depends(verify_service_token),
) -> MineruParseJobResponse:
    """Enqueue a MinerU knowledge document parse job."""
    job_id = f"mineru_{uuid.uuid4().hex}"
    job_payload = payload.model_dump()
    create_job(job_id, "mineru_parse", job_payload)
    try:
        mineru_parse_task.apply_async(
            args=[job_id, job_payload],
            task_id=job_id,
            queue=settings.celery_queue,
        )
    except Exception as exc:
        mark_job_failed(job_id, str(exc))
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="任务队列不可用") from exc
    return MineruParseJobResponse(jobId=job_id, status="queued")
