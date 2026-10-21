from __future__ import annotations

import logging
import os
import shutil
from pathlib import Path
from typing import Any, BinaryIO

from fastapi import HTTPException, status

from app.core.config import settings
from app.services.knowledge_document_paths import document_artifact_prefix, storage_prefix

logger = logging.getLogger(__name__)


class StoredFile:
    def __init__(self, *, storage_type: str, storage_key: str, local_path: str = "", bucket: str = "") -> None:
        self.storage_type = storage_type
        self.storage_key = storage_key
        self.local_path = local_path
        self.bucket = bucket


class StorageService:
    storage_type = "local"

    def put_file(self, source: BinaryIO, storage_key: str) -> StoredFile:
        raise NotImplementedError

    def open_file(self, storage_key: str) -> BinaryIO:
        raise NotImplementedError

    def delete_file(self, storage_key: str) -> None:
        raise NotImplementedError

    def exists(self, storage_key: str) -> bool:
        raise NotImplementedError


class LocalStorageAdapter(StorageService):
    storage_type = "local"

    def __init__(self, root_dir: str) -> None:
        self.root_dir = Path(root_dir).expanduser().resolve()
        self.root_dir.mkdir(parents=True, exist_ok=True)

    def _path(self, storage_key: str) -> Path:
        normalized = storage_key.strip().lstrip("/").replace("\\", "/")
        path = (self.root_dir / normalized).resolve()
        if self.root_dir not in path.parents and path != self.root_dir:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="文件路径无效")
        return path

    def put_file(self, source: BinaryIO, storage_key: str) -> StoredFile:
        target = self._path(storage_key)
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("wb") as output:
            while True:
                chunk = source.read(1024 * 1024)
                if not chunk:
                    break
                output.write(chunk)
        return StoredFile(storage_type=self.storage_type, storage_key=storage_key, local_path=str(target))

    def open_file(self, storage_key: str) -> BinaryIO:
        path = self._path(storage_key)
        if not path.exists() or not path.is_file():
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="文件不存在")
        return path.open("rb")

    def delete_file(self, storage_key: str) -> None:
        path = self._path(storage_key)
        if path.exists() and path.is_file():
            path.unlink()

    def exists(self, storage_key: str) -> bool:
        path = self._path(storage_key)
        return path.exists() and path.is_file()

    def delete_prefix(self, prefix: str) -> None:
        """Delete a directory tree under root_dir matching prefix."""
        normalized = prefix.strip().lstrip("/").replace("\\", "/")
        target = (self.root_dir / normalized).resolve()
        if self.root_dir not in target.parents and target != self.root_dir:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="文件路径无效")
        if target.is_dir():
            shutil.rmtree(target, ignore_errors=True)
        elif target.is_file():
            target.unlink(missing_ok=True)


class OSSStorageAdapter(StorageService):
    storage_type = "oss"

    def __init__(self) -> None:
        if not settings.knowledge_oss_endpoint or not settings.knowledge_oss_bucket:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="OSS 存储配置不完整")
        try:
            import oss2  # type: ignore
        except Exception as exc:  # pragma: no cover - optional dependency
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="OSS 依赖未安装，请安装 oss2") from exc
        auth = oss2.Auth(settings.knowledge_oss_access_key_id, settings.knowledge_oss_access_key_secret)
        self.bucket_name = settings.knowledge_oss_bucket
        self.bucket = oss2.Bucket(auth, settings.knowledge_oss_endpoint, self.bucket_name)

    def put_file(self, source: BinaryIO, storage_key: str) -> StoredFile:
        self.bucket.put_object(storage_key, source)
        return StoredFile(
            storage_type=self.storage_type,
            storage_key=storage_key,
            bucket=self.bucket_name,
        )

    def open_file(self, storage_key: str) -> BinaryIO:
        try:
            result = self.bucket.get_object(storage_key)
        except Exception as exc:  # pragma: no cover - network path
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="文件不存在") from exc
        return result

    def delete_file(self, storage_key: str) -> None:
        self.bucket.delete_object(storage_key)

    def exists(self, storage_key: str) -> bool:
        return bool(self.bucket.object_exists(storage_key))

    def delete_prefix(self, prefix: str) -> None:
        """Delete all objects under prefix."""
        import oss2  # type: ignore

        normalized = prefix.strip().lstrip("/").replace("\\", "/")
        if not normalized.endswith("/"):
            normalized = f"{normalized}/"
        try:
            for obj in oss2.ObjectIterator(self.bucket, prefix=normalized):
                self.bucket.delete_object(obj.key)
        except Exception as exc:  # pragma: no cover
            logger.warning(f"OSS delete_prefix failed: prefix={normalized}, error={exc}")


def get_storage_service(storage_type: str | None = None) -> StorageService:
    storage_type = str(storage_type or settings.knowledge_storage_type or "local").strip().lower()
    if storage_type == "oss":
        return OSSStorageAdapter()
    return LocalStorageAdapter(os.path.abspath(settings.knowledge_local_storage_dir))


def delete_document_storage(doc: dict[str, Any]) -> None:
    """
    Remove original file, preview, and artifact tree for a knowledge document.

    Args:
        doc: Mongo knowledge_documents row.
    """
    storage_type = str(doc.get("storage_type") or "local")
    storage = get_storage_service(storage_type)
    keys = [
        str(doc.get("storage_key") or "").strip(),
        str(doc.get("preview_key") or "").strip(),
        str(doc.get("parsed_markdown_key") or "").strip(),
        str(doc.get("parsed_json_key") or "").strip(),
        str(doc.get("raw_chunks_key") or "").strip(),
        str(doc.get("rag_chunks_key") or "").strip(),
        str(doc.get("chunks_key") or "").strip(),
    ]
    seen: set[str] = set()
    for key in keys:
        if not key or key in seen:
            continue
        seen.add(key)
        try:
            storage.delete_file(key)
        except Exception as exc:
            logger.warning(f"delete_document_storage file failed: key={key}, error={exc}")
    main_id = str(doc.get("main_id") or "default")
    document_id = str(doc.get("_id") or "")
    if document_id:
        artifact_prefix = document_artifact_prefix(main_id, document_id)
        try:
            storage.delete_prefix(artifact_prefix)
        except Exception as exc:
            logger.warning(f"delete_document_storage prefix failed: prefix={artifact_prefix}, error={exc}")
        doc_prefix = f"{storage_prefix()}/{main_id}/{document_id}/"
        try:
            storage.delete_prefix(doc_prefix)
        except Exception as exc:
            logger.warning(f"delete_document_storage doc tree failed: prefix={doc_prefix}, error={exc}")


def read_text_artifact(doc: dict[str, Any], storage_key: str) -> str:
    """Read a text artifact from document storage."""
    storage = get_storage_service(str(doc.get("storage_type") or "local"))
    with storage.open_file(storage_key) as fileobj:
        raw = fileobj.read()
    if isinstance(raw, bytes):
        return raw.decode("utf-8", errors="ignore")
    return str(raw)


def write_text_artifact(doc: dict[str, Any], storage_key: str, text: str) -> None:
    """Write a text artifact to document storage."""
    storage = get_storage_service(str(doc.get("storage_type") or "local"))
    from io import BytesIO

    storage.put_file(BytesIO(text.encode("utf-8")), storage_key)
