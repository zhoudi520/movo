from types import SimpleNamespace
from datetime import datetime, timedelta, timezone

from bson import ObjectId
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.routes import directory, invite_history, invite_members
from app.services.invite_links import request_portal_origin, resolve_portal_base
from app.services.invite_policy import single_invite_role_ids, validate_invite_placement
import pytest
from fastapi import HTTPException


def test_invite_link_uses_public_origin_and_local_portal() -> None:
    assert resolve_portal_base("http://localhost:3000", "", "http://192.0.2.25:3001", "http://127.0.0.1:8100/") == "http://192.0.2.25:3001"
    assert resolve_portal_base("http://localhost:3000", "", "http://localhost:3100", "http://127.0.0.1:8100/") == "http://localhost:3000"
    assert resolve_portal_base("http://localhost:3000", "https://movo.example.com", "http://localhost:3100", "http://127.0.0.1:8100/") == "http://localhost:3000"
    assert resolve_portal_base("https://movo.example.com", "https://movo.example.com", "http://localhost:3100", "http://127.0.0.1:8100/") == "http://localhost:3000"
    assert request_portal_origin(SimpleNamespace(headers={"referer": "http://localhost:3100/organizations/users"})) == "http://localhost:3100/organizations/users"
    assert resolve_portal_base("http://localhost:3000", "https://movo.example.com", "https://movo.example.com", "http://admin-api:8100/") == "https://movo.example.com"


def test_one_invite_registers_two_members_with_same_roles(monkeypatch) -> None:
    invite = {"_id": ObjectId(), "main_id": "tenant-a", "user_id": None, "token": "same-code", "status": "active", "purpose": "register", "org_name": "Example", "role_ids": ["role-a"], "primary_role_id": "role-a", "default_department_id": None, "created_at": datetime.now(timezone.utc), "expires_at": datetime.now(timezone.utc) + timedelta(hours=1)}
    users = []
    assignments = []

    class Users:
        async def find_one(self, query):
            return next((user for user in users if user["login_name"] == query.get("login_name")), None)

        async def insert_one(self, doc):
            doc["_id"] = ObjectId()
            users.append(doc)
            return SimpleNamespace(inserted_id=doc["_id"])

        def find(self, query):
            class Cursor:
                async def to_list(self, length):
                    return [user for user in users if user["_id"] in query["_id"]["$in"]][:length]
            return Cursor()

    class Departments:
        async def find_one(self, _query):
            return {"_id": ObjectId()}

        async def count_documents(self, _query):
            return 0

    class PositionRoles:
        async def count_documents(self, _query):
            return 1

    class Invites:
        async def count_documents(self, _query): return 1

        async def find_one(self, _query): return invite

        def find(self, _query):
            class Cursor:
                def sort(self, *_args): return self
                def skip(self, *_args): return self
                def limit(self, *_args): return self
                def __aiter__(self):
                    async def iterate(): yield invite
                    return iterate()
            return Cursor()

        async def update_one(self, _query, update):
            invite["accepted_count"] = invite.get("accepted_count", 0) + update["$inc"]["accepted_count"]
            return SimpleNamespace(matched_count=1)

    class Roles:
        async def validate_roles(self, *_args): pass

        def __init__(self): self.repository = self

        async def replace_user_roles(self, main_id, user_id, role_ids, primary_role_id, **_kwargs):
            assignments.append((main_id, user_id, role_ids, primary_role_id))

        async def audit(self, *_args): pass

    acceptances = []

    class Acceptances:
        async def update_one(self, query, update, upsert=False):
            if not any(item["user_id"] == query["user_id"] for item in acceptances):
                acceptances.append({**query, **update["$setOnInsert"]})
                return SimpleNamespace(upserted_id=ObjectId())
            return SimpleNamespace(upserted_id=None)

        async def count_documents(self, _query): return len(acceptances)

        def find(self, _query):
            class Cursor:
                def sort(self, *_args): return self
                def skip(self, count): self.offset = count; return self
                def limit(self, count): self.limit_count = count; return self
                async def to_list(self, length): return acceptances[self.offset:self.offset + min(length, self.limit_count)]
            return Cursor()

    async def find_invite(_token): return invite
    async def noop(*_args): return None

    db = {directory.USER_COLLECTION: Users(), directory.DEPARTMENT_COLLECTION: Departments(), directory.USER_INVITE_COLLECTION: Invites(), directory.POSITION_ROLE_COLLECTION: PositionRoles(), invite_members.USER_INVITE_ACCEPTANCE_COLLECTION: Acceptances()}
    monkeypatch.setattr(directory, "get_db", lambda: db)
    monkeypatch.setattr(invite_history, "get_db", lambda: db)
    monkeypatch.setattr(invite_members, "get_db", lambda: db)
    monkeypatch.setattr(directory, "_find_active_invite", find_invite)
    monkeypatch.setattr(directory, "PositionRoleService", Roles)
    monkeypatch.setattr(directory, "assert_member_capacity", noop)
    monkeypatch.setattr(directory, "_upsert_user_relations", noop)
    monkeypatch.setattr(directory, "_write_audit", noop)

    app = FastAPI()
    app.include_router(directory.router, prefix="/api/directory")
    app.include_router(invite_history.router, prefix="/api/directory")
    app.include_router(invite_members.router, prefix="/api/directory")
    app.dependency_overrides[invite_history.get_current_admin_user] = lambda: {"main_id": "tenant-a"}
    app.dependency_overrides[invite_members.get_current_admin_user] = lambda: {"main_id": "tenant-a"}
    with TestClient(app) as client:
        for login_name in ("employee-one", "employee-two"):
            response = client.post("/api/directory/invite-links/same-code/accept", json={
                "loginName": login_name, "name": f"Employee {login_name}", "email": f"{login_name}@example.com", "password": "example-password-123",
            })
            assert response.status_code == 200, response.text
            assert response.json() == {"success": True}
        history = client.get("/api/directory/invites")
        assert history.status_code == 200, history.text
        assert history.json()["items"][0]["acceptedCount"] == 2
        members = client.get(f"/api/directory/invites/{invite['_id']}/members", params={"pageSize": 1, "page": 2})
        assert members.status_code == 200, members.text
        assert members.json()["total"] == 2
        assert len(members.json()["items"]) == 1
        assert members.json()["unattributedCount"] == 0
    assert invite["status"] == "active"
    assert invite["accepted_count"] == 2
    assert {user["login_name"] for user in users} == {"employee-one", "employee-two"}
    assert len(assignments) == 2
    assert all(role_ids == ["role-a"] and primary == "role-a" for _, _, role_ids, primary in assignments)
    assert all(user["name"].startswith("Employee ") and user["email"].endswith("@example.com") for user in users)


def test_placement_is_required_only_when_enterprise_has_choices():
    import asyncio
    class Collection:
        def __init__(self, count): self.count = count
        async def count_documents(self, _query): return self.count

    class Roles:
        async def validate_roles(self, *_args): pass

    db = {directory.DEPARTMENT_COLLECTION: Collection(1), directory.POSITION_ROLE_COLLECTION: Collection(1)}
    with pytest.raises(HTTPException, match="请选择邀请员工所属部门"):
        asyncio.run(validate_invite_placement(db, "tenant-a", None, "", [], Roles()))
    with pytest.raises(HTTPException, match="请选择主要岗位角色"):
        asyncio.run(validate_invite_placement(db, "tenant-a", "department-a", "", [], Roles()))
    db = {directory.DEPARTMENT_COLLECTION: Collection(0), directory.POSITION_ROLE_COLLECTION: Collection(0)}
    asyncio.run(validate_invite_placement(db, "tenant-a", None, "", [], Roles()))


def test_invitation_registration_requires_real_name():
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        directory.InviteAcceptPayload(loginName="employee", name="", password="example-password-123")


def test_new_invitation_assigns_exactly_one_role():
    assert single_invite_role_ids("role-a", []) == ["role-a"]
    assert single_invite_role_ids("role-a", ["role-a"]) == ["role-a"]
    assert single_invite_role_ids("", []) == []
    with pytest.raises(HTTPException, match="只能指定一个岗位角色"):
        single_invite_role_ids("role-a", ["role-a", "role-b"])


def test_invite_member_pages_scale_to_thousand_records(monkeypatch):
    invite_id = ObjectId()
    rows = [{"user_id": str(ObjectId()), "accepted_at": datetime.now(timezone.utc)} for _ in range(1000)]

    class Invites:
        async def find_one(self, query):
            return {"_id": invite_id, "accepted_count": 1000} if query["main_id"] == "tenant-a" else None

    class Acceptances:
        async def count_documents(self, query):
            assert query == {"main_id": "tenant-a", "invite_id": str(invite_id)}
            return len(rows)

        def find(self, _query):
            class Cursor:
                def sort(self, *_args): return self
                def skip(self, offset): self.offset = offset; return self
                def limit(self, limit): self.limit_count = limit; return self
                async def to_list(self, length): return rows[self.offset:self.offset + min(length, self.limit_count)]
            return Cursor()

    class Users:
        def find(self, _query):
            class Cursor:
                async def to_list(self, length): return []
            return Cursor()

    db = {invite_members.USER_INVITE_COLLECTION: Invites(), invite_members.USER_INVITE_ACCEPTANCE_COLLECTION: Acceptances(), invite_members.USER_COLLECTION: Users()}
    monkeypatch.setattr(invite_members, "get_db", lambda: db)
    app = FastAPI()
    app.include_router(invite_members.router, prefix="/api/directory")
    app.dependency_overrides[invite_members.get_current_admin_user] = lambda: {"main_id": "tenant-a"}
    with TestClient(app) as client:
        first = client.get(f"/api/directory/invites/{invite_id}/members", params={"page": 1, "pageSize": 25})
        last = client.get(f"/api/directory/invites/{invite_id}/members", params={"page": 40, "pageSize": 25})
        outside = client.get(f"/api/directory/invites/{invite_id}/members", params={"page": 41, "pageSize": 25})
        assert first.status_code == last.status_code == outside.status_code == 200
        assert first.json()["total"] == 1000
        assert len(first.json()["items"]) == len(last.json()["items"]) == 25
        assert outside.json()["items"] == []
        assert first.json()["items"][0]["userId"] != last.json()["items"][0]["userId"]
