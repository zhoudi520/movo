"""Administration of shared model connections."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from pymongo.errors import DuplicateKeyError

from app.api.deps import get_current_admin_user
from app.product.extensions import get_admin_product_extension
from app.repositories.model_group_repository import (
    INSTANCE_COLLECTION, create_group, delete_empty_group, find_group, list_groups, update_group,
)
from app.repositories.model_repository import find_provider_by_id
from app.core.db import get_db


router = APIRouter()


class ModelGroupPayload(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    providerId: str = Field(min_length=1)
    baseUrl: str = Field(min_length=1, max_length=300)
    apiVersion: str = Field(default="", max_length=40)
    apiKey: str = Field(default="", max_length=600)
    status: str = Field(default="active", pattern=r"^(active|disabled)$")


def _tenant(user: dict[str, Any]) -> str:
    return str(user.get("main_id") or "default")


def _format(doc: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": str(doc["_id"]),
        "name": doc.get("name", ""),
        "providerId": str(doc.get("provider_id") or ""),
        "baseUrl": doc.get("base_url", ""),
        "apiVersion": doc.get("api_version", ""),
        "apiKeyMasked": doc.get("api_key_masked", ""),
        "status": doc.get("status", "active"),
    }


async def _check_provider(provider_id: str) -> dict[str, Any]:
    try:
        provider = await find_provider_by_id(provider_id)
    except Exception as exc:
        raise HTTPException(400, "model_provider_invalid") from exc
    if not provider or provider.get("status") != "active":
        raise HTTPException(400, "model_provider_unavailable")
    return provider


def _check_connection(payload: ModelGroupPayload, provider: dict[str, Any]) -> None:
    if provider.get("provider_type") == "azure_openai" and not payload.apiVersion.strip():
        raise HTTPException(400, "model_group_api_version_required")


@router.get("/groups")
async def get_groups(user: dict = Depends(get_current_admin_user)) -> list[dict[str, Any]]:
    return [_format(doc) for doc in await list_groups(_tenant(user))]


@router.post("/groups", status_code=201)
async def post_group(payload: ModelGroupPayload, user: dict = Depends(get_current_admin_user)) -> dict[str, Any]:
    provider = await _check_provider(payload.providerId)
    _check_connection(payload, provider)
    if not payload.apiKey.strip():
        raise HTTPException(400, "model_group_api_key_required")
    main_id = _tenant(user)
    try:
        group = await create_group(main_id, {
            "name": payload.name.strip(), "provider_id": payload.providerId,
            "base_url": payload.baseUrl.strip(), "api_version": payload.apiVersion.strip(),
            "api_key": payload.apiKey.strip(), "status": payload.status,
        })
    except DuplicateKeyError as exc:
        raise HTTPException(409, "model_group_name_exists") from exc
    try:
        for callback in get_admin_product_extension().model_group_created:
            result = callback(main_id, str(group["_id"]))
            if hasattr(result, "__await__"):
                await result
    except Exception:
        await delete_empty_group(str(group["_id"]), main_id)
        raise
    return _format(group)


@router.put("/groups/{group_id}")
async def put_group(group_id: str, payload: ModelGroupPayload, user: dict = Depends(get_current_admin_user)) -> dict[str, Any]:
    main_id = _tenant(user)
    existing = await find_group(group_id, main_id)
    if not existing:
        raise HTTPException(404, "model_group_not_found")
    provider = await _check_provider(payload.providerId)
    _check_connection(payload, provider)
    if str(existing.get("provider_id")) != payload.providerId:
        member = await get_db()[INSTANCE_COLLECTION].find_one({"main_id": main_id, "group_id": group_id}, {"_id": 1})
        if member:
            raise HTTPException(409, "model_group_provider_in_use")
    try:
        updated = await update_group(group_id, main_id, {
            "name": payload.name.strip(), "provider_id": payload.providerId,
            "base_url": payload.baseUrl.strip(), "api_version": payload.apiVersion.strip(),
            "api_key": payload.apiKey.strip(), "status": payload.status,
        })
    except DuplicateKeyError as exc:
        raise HTTPException(409, "model_group_name_exists") from exc
    return _format(updated)


@router.delete("/groups/{group_id}")
async def remove_group(group_id: str, user: dict = Depends(get_current_admin_user)) -> dict[str, bool]:
    main_id = _tenant(user)
    if not await find_group(group_id, main_id):
        raise HTTPException(404, "model_group_not_found")
    try:
        await delete_empty_group(group_id, main_id)
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc
    for callback in get_admin_product_extension().model_group_deleted:
        result = callback(main_id, group_id)
        if hasattr(result, "__await__"):
            await result
    return {"success": True}
