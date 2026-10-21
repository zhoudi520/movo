"""Run MinerU parse jobs and callback admin-api."""

from __future__ import annotations

import logging
import tempfile
from pathlib import Path

from app.domain.jobs import MineruParseJobRequest
from app.infra.mineru_client import extract_markdown_and_assets_with_mineru
from app.integrations.callbacks.admin_api_client import post_callback
from app.integrations.storage import get_storage_adapter
from app.repositories.job_repository import mark_job_failed, mark_job_succeeded, update_job_progress

logger = logging.getLogger(__name__)


def _notify_admin_callback(request: MineruParseJobRequest, payload: dict) -> None:
    """Best-effort admin callback; logs and swallows delivery errors."""
    try:
        post_callback(request.callback.url, request.callback.token, payload)
    except Exception as exc:
        logger.error(f"MinerU admin 回调未送达: url={request.callback.url}, error={exc}, payload={payload}")


def run_mineru_parse(job_id: str, request: MineruParseJobRequest) -> None:
    """
    Download source file, parse with MinerU, store markdown artifact, notify admin-api.

    Args:
        job_id: Celery job id.
        request: MinerU parse job payload.
    """
    source_storage = get_storage_adapter(request.source.storageType)
    artifact_storage = get_storage_adapter(request.artifacts.storageType)
    artifact_prefix = request.artifacts.storagePrefix.strip().strip("/")
    markdown_key = f"{artifact_prefix}/parsed.md"
    mineru_cfg = request.mineru
    try:
        with tempfile.TemporaryDirectory(prefix="movo-mineru-") as temp_dir:
            temp_path = Path(temp_dir)
            suffix = Path(request.source.filename or request.source.storageKey).suffix or ".bin"
            source_path = temp_path / f"source{suffix}"
            with source_storage.open_file(request.source.storageKey) as source, source_path.open("wb") as output:
                while True:
                    chunk = source.read(1024 * 1024)
                    if not chunk:
                        break
                    output.write(chunk)
            update_job_progress(job_id, 30)
            markdown, asset_files = extract_markdown_and_assets_with_mineru(
                source_path,
                service_url=str(mineru_cfg.serviceUrl or ""),
                api_key=str(mineru_cfg.apiKey or ""),
                model_version=str(request.modelVersion or "vlm"),
                language=str(request.language or "ch"),
            )
            update_job_progress(job_id, 80)
            from app.services.document_parsing_service import _write_bytes_artifact, _write_text_artifact

            _write_text_artifact(artifact_storage, markdown_key, markdown)
            for rel_path, payload in asset_files.items():
                rel = rel_path.strip().lstrip("/").replace("\\", "/")
                asset_key = f"{artifact_prefix}/{rel}"
                _write_bytes_artifact(artifact_storage, asset_key, payload)
            if asset_files:
                logger.info(f"MinerU 已写入图片 artifact: count={len(asset_files)}, document={request.documentId}")
        _notify_admin_callback(
            request,
            {
                "jobId": job_id,
                "status": "succeeded",
                "markdownKey": markdown_key,
                "error": "",
            },
        )
        mark_job_succeeded(job_id, {"markdownKey": markdown_key})
    except Exception as exc:
        message = str(exc) or repr(exc)
        mark_job_failed(job_id, message)
        _notify_admin_callback(
            request,
            {"jobId": job_id, "status": "failed", "markdownKey": "", "error": message[:2000]},
        )
        raise


def post_mineru_failure_callback(job_id: str, request: MineruParseJobRequest, message: str) -> None:
    """Notify admin-api that MinerU job failed."""
    _notify_admin_callback(
        request,
        {"jobId": job_id, "status": "failed", "markdownKey": "", "error": message[:2000]},
    )
