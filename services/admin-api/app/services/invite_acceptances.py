from datetime import datetime, timezone

from app.repositories.directory_repository import USER_INVITE_ACCEPTANCE_COLLECTION


async def record_invite_acceptance(db, *, main_id: str, invite_id: str, user_id: str) -> bool:
    """Return whether this employee was newly attributed to the invitation."""
    result = await db[USER_INVITE_ACCEPTANCE_COLLECTION].update_one(
        {"main_id": main_id, "invite_id": invite_id, "user_id": user_id},
        {"$setOnInsert": {"accepted_at": datetime.now(timezone.utc)}},
        upsert=True,
    )
    return result.upserted_id is not None
