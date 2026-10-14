from datetime import datetime, timedelta, timezone

from bson import ObjectId
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.routes import invite_history


def test_invitation_history_paginates_and_filters_departments(monkeypatch):
    now = datetime.now(timezone.utc)
    invites = [
        {
            "_id": ObjectId(), "main_id": "tenant-a", "purpose": "register", "user_id": None,
            "default_department_id": "engineering" if index % 2 else "finance",
            "status": "active", "token": f"code-{index}", "accepted_count": index,
            "created_at": now - timedelta(minutes=index), "expires_at": now + timedelta(days=1),
        }
        for index in range(205)
    ]

    class Invites:
        def matching(self, query):
            return [row for row in invites if all(row.get(key) == value for key, value in query.items() if key not in {"status", "expires_at"})]

        async def count_documents(self, query): return len(self.matching(query))

        def find(self, query):
            rows = self.matching(query)

            class Cursor:
                def sort(self, *_args): return self
                def skip(self, count): self.offset = count; return self
                def limit(self, count): self.limit_count = count; return self
                def __aiter__(self):
                    async def iterate():
                        for row in rows[self.offset:self.offset + self.limit_count]: yield row
                    return iterate()
            return Cursor()

    monkeypatch.setattr(invite_history, "get_db", lambda: {invite_history.USER_INVITE_COLLECTION: Invites()})
    app = FastAPI()
    app.include_router(invite_history.router, prefix="/api/directory")
    app.dependency_overrides[invite_history.get_current_admin_user] = lambda: {"main_id": "tenant-a"}
    with TestClient(app) as client:
        final = client.get("/api/directory/invites", params={"page": 11, "pageSize": 20}, headers={"referer": "http://localhost:3100/organizations/users"})
        assert final.status_code == 200
        assert final.json()["total"] == 205
        assert len(final.json()["items"]) == 5
        assert final.json()["items"][0]["inviteUrl"].startswith("http://localhost:3000/")
        filtered = client.get("/api/directory/invites", params={"page": 1, "pageSize": 20, "departmentId": "engineering"})
        assert filtered.status_code == 200
        assert filtered.json()["total"] == 102
        assert all(item["defaultDepartmentId"] == "engineering" for item in filtered.json()["items"])
