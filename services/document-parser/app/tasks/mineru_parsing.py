from __future__ import annotations

from app.domain.jobs import MineruParseJobRequest
from app.repositories.job_repository import mark_job_failed, mark_job_running
from app.services.mineru_parse_service import post_mineru_failure_callback, run_mineru_parse
from app.workers.celery_app import celery_app


@celery_app.task(name="document.mineru_parse", bind=True, max_retries=2)
def mineru_parse_task(self, job_id: str, payload: dict) -> None:
    """Celery entry for MinerU document parsing."""
    request = MineruParseJobRequest.model_validate(payload)
    try:
        mark_job_running(job_id)
        run_mineru_parse(job_id, request)
    except Exception as exc:
        message = str(exc)
        if self.request.retries < self.max_retries:
            raise self.retry(exc=exc, countdown=15 * (self.request.retries + 1))
        mark_job_failed(job_id, message)
        post_mineru_failure_callback(job_id, request, message)
        raise
