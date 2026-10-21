"""Embed (iframe) login: exchange login_name for an end-user session without a password."""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any

from pymongo.errors import DuplicateKeyError

from app.core.tenant import add_main_scope, resolve_main_id
from app.governance.position_policy import CAPABILITY_KEYS

USER_COLLECTION = "end_users"
SETUP_COLLECTION = "system_bootstrap"
DEPARTMENT_COLLECTION = "org_units"
ORGANIZATION_COLLECTION = "organizations"
USER_ORG_REL_COLLECTION = "end_user_org_relations"
POSITION_ROLE_COLLECTION = "position_roles"
USER_ROLE_COLLECTION = "end_user_position_roles"
FULL_ACCESS_ROLE_KEY = "full_access_admin"
FULL_ACCESS_ROLE_NAME = "全能力管理员"
EMBED_ROLE_ACTOR = "embed-login"

_EMBED_LOGIN_NAME_RE = re.compile(r"^[A-Za-z0-9_.-]{1,64}$")


class EmbedLoginAmbiguousError(Exception):
    """Multiple active users match the same login_name under case-insensitive rules."""


class EmbedLoginIdentityError(ValueError):
    """The embed user id is missing or fails format validation."""


def _now() -> datetime:
    return datetime.utcnow()


def normalize_embed_login_name(login_name_input: str) -> str:
    """Validate and normalize the third-party user id used as end_users.login_name."""

    identity = str(login_name_input or "").strip()
    if not identity or not _EMBED_LOGIN_NAME_RE.fullmatch(identity):
        raise EmbedLoginIdentityError("userID 格式无效，仅支持 1–64 位字母、数字、._-")
    return identity


async def resolve_default_main_id(db: Any) -> str:
    """Return Setup singleton main_id when bootstrap completed, else empty string."""

    state = await db[SETUP_COLLECTION].find_one({"_id": "singleton"}, {"main_id": 1, "completed": 1})
    if not state or not bool(state.get("completed")):
        return ""
    return str(state.get("main_id") or "").strip()


async def resolve_embed_main_id(db: Any, requested_main_id: str | None) -> str:
    """Resolve tenant id from explicit request or Setup default."""

    explicit = str(requested_main_id or "").strip()
    if explicit:
        return resolve_main_id(explicit)
    return resolve_main_id(await resolve_default_main_id(db))


async def _ensure_root_department(db: Any, main_id: str) -> str:
    """Ensure the tenant root department exists and return its id."""

    now = _now()
    await db[DEPARTMENT_COLLECTION].update_one(
        {"main_id": main_id, "code": "root"},
        {
            "$setOnInsert": {
                "main_id": main_id,
                "name": "企业总部",
                "code": "root",
                "parent_id": None,
                "path_ids": [],
                "path_names": [],
                "status": "active",
                "source": "local",
                "source_dept_id": "",
                "created_at": now,
            },
            "$set": {"updated_at": now},
        },
        upsert=True,
    )
    root = await db[DEPARTMENT_COLLECTION].find_one({"main_id": main_id, "code": "root"})
    if not root:
        raise RuntimeError("组织根部门初始化失败")
    return str(root["_id"])


async def _resolve_org_name(db: Any, main_id: str) -> str:
    org = await db[ORGANIZATION_COLLECTION].find_one({"main_id": main_id}, {"org_name": 1})
    org_name = str((org or {}).get("org_name") or "").strip()
    if org_name:
        return org_name
    setup = await db[SETUP_COLLECTION].find_one({"_id": "singleton"}, {"org_name": 1})
    return str((setup or {}).get("org_name") or main_id).strip()


async def _ensure_full_access_role(db: Any, main_id: str) -> dict[str, Any]:
    """Ensure the tenant-wide full-access position role exists and return its document."""

    now = _now()
    role_id = f"system:{main_id}:{FULL_ACCESS_ROLE_KEY}"
    await db[POSITION_ROLE_COLLECTION].update_one(
        {"main_id": main_id, "system_key": FULL_ACCESS_ROLE_KEY},
        {
            "$setOnInsert": {
                "_id": role_id,
                "main_id": main_id,
                "name": FULL_ACCESS_ROLE_NAME,
                "description": "系统保障角色，自动拥有企业全部 Agent 能力、工具与 Skill。",
                "created_at": now,
            },
            "$set": {
                "status": "active",
                "protected": True,
                "capabilities": {key: True for key in CAPABILITY_KEYS},
                "tool_access_mode": "all",
                "tool_ids": [],
                "skill_access_mode": "all",
                "skill_ids": [],
                "updated_at": now,
            },
        },
        upsert=True,
    )
    role = await db[POSITION_ROLE_COLLECTION].find_one({"main_id": main_id, "system_key": FULL_ACCESS_ROLE_KEY})
    if not role:
        raise RuntimeError("全能力管理员岗位角色初始化失败")
    return dict(role)


async def _user_has_position_role(db: Any, main_id: str, user_id: str) -> bool:
    """Return whether the user already has at least one position role assignment."""

    count = await db[USER_ROLE_COLLECTION].count_documents({"main_id": main_id, "user_id": user_id})
    return count > 0


async def ensure_embed_default_position_role(db: Any, main_id: str, user_id: str) -> None:
    """Assign full-access admin as the primary role when embed users have no position role yet."""

    if await _user_has_position_role(db, main_id, user_id):
        return
    role = await _ensure_full_access_role(db, main_id)
    role_id = str(role.get("_id") or "")
    if not role_id:
        raise RuntimeError("全能力管理员岗位角色 ID 无效")
    now = _now()
    await db[USER_ROLE_COLLECTION].update_one(
        {"main_id": main_id, "user_id": user_id, "role_id": role_id},
        {
            "$setOnInsert": {"created_at": now, "created_by": EMBED_ROLE_ACTOR},
            "$set": {"is_primary": True, "updated_at": now, "updated_by": EMBED_ROLE_ACTOR},
        },
        upsert=True,
    )


async def provision_embed_end_user(db: Any, main_id: str, login_name_input: str) -> dict[str, Any]:
    """Create an active end user for embed login without a password.

    The user can only sign in through embed-login while MOVO_EMBED_LOGIN_ENABLED is on.
    Password login remains unavailable until an administrator sets credentials.
    """

    login_name = normalize_embed_login_name(login_name_input)
    existing = await find_embed_user(db, main_id, login_name)
    if existing:
        return existing

    root_id = await _ensure_root_department(db, main_id)
    org_name = await _resolve_org_name(db, main_id)
    now = _now()
    user_doc: dict[str, Any] = {
        "main_id": main_id,
        "name": login_name,
        "mobile": "",
        "email": "",
        "status": "active",
        "source": "embed",
        "source_user_id": "",
        "primary_org_id": root_id,
        "login_name": login_name,
        "org_name": org_name,
        "space_type": "enterprise",
        "created_at": now,
        "updated_at": now,
    }
    try:
        result = await db[USER_COLLECTION].insert_one(user_doc)
    except DuplicateKeyError:
        raced = await find_embed_user(db, main_id, login_name)
        if raced:
            return raced
        raise
    user_id = str(result.inserted_id)
    await db[USER_ORG_REL_COLLECTION].insert_one(
        {
            "main_id": main_id,
            "user_id": user_id,
            "org_id": root_id,
            "is_primary": True,
            "created_at": now,
            "updated_at": now,
        }
    )
    await ensure_embed_default_position_role(db, main_id, user_id)
    user_doc["_id"] = result.inserted_id
    return user_doc


async def find_embed_user(db: Any, main_id: str, login_name_input: str) -> dict[str, Any] | None:
    """Find an active end user by login_name within a tenant (case-insensitive).

    Args:
        db: Mongo database handle.
        main_id: Tenant scope.
        login_name_input: Raw login name from the embed URL or API body.

    Returns:
        The matched user document, or None when no active user exists.

    Raises:
        EmbedLoginAmbiguousError: When more than one distinct login_name matches.
    """

    identity = str(login_name_input or "").strip()
    if not identity:
        return None
    query = add_main_scope(
        {
            "status": "active",
            "login_name": {"$regex": f"^{re.escape(identity)}$", "$options": "i"},
        },
        main_id,
    )
    rows = await db[USER_COLLECTION].find(query).to_list(length=8)
    if not rows:
        return None
    canonical_names = {str(row.get("login_name") or "") for row in rows}
    if len(rows) > 1 and len(canonical_names) > 1:
        raise EmbedLoginAmbiguousError(f"ambiguous login_name under main_id={main_id}")
    return rows[0]


async def resolve_embed_end_user(
    db: Any,
    main_id: str,
    login_name_input: str,
    *,
    auto_provision: bool,
) -> dict[str, Any] | None:
    """Find or optionally provision the embed end user."""

    user_doc = await find_embed_user(db, main_id, login_name_input)
    if user_doc:
        await ensure_embed_default_position_role(db, main_id, str(user_doc["_id"]))
        return user_doc
    if not auto_provision:
        return None
    return await provision_embed_end_user(db, main_id, login_name_input)
