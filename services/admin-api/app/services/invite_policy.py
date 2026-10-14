from fastapi import HTTPException

from app.position_roles.constants import POSITION_ROLE_COLLECTION
from app.repositories.directory_repository import DEPARTMENT_COLLECTION


def single_invite_role_ids(primary_role_id: str, role_ids: list[str]) -> list[str]:
    if any(role_id != primary_role_id for role_id in role_ids):
        raise HTTPException(status_code=400, detail="邀请只能指定一个岗位角色；额外角色请在员工入职后单独设置")
    return [primary_role_id] if primary_role_id else []


async def validate_invite_placement(db, main_id: str, department_id: str | None, role_id: str, role_ids: list[str], role_service) -> None:
    departments_exist = await db[DEPARTMENT_COLLECTION].count_documents(
        {"main_id": main_id, "status": "active", "code": {"$ne": "root"}}
    )
    if departments_exist and not department_id:
        raise HTTPException(status_code=400, detail="企业已有部门，请选择邀请员工所属部门")
    roles_exist = await db[POSITION_ROLE_COLLECTION].count_documents({"main_id": main_id, "status": "active"})
    if roles_exist and not role_id:
        raise HTTPException(status_code=400, detail="企业已有岗位角色，请选择主要岗位角色")
    if role_id or role_ids:
        await role_service.validate_roles(main_id, role_ids, role_id)
