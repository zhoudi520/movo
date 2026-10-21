"""Use the execution router to decide whether public search belongs in a profile."""

from __future__ import annotations

import logging

from app.enterprise_capabilities.research.progressive.provider_router import ProviderRouter


logger = logging.getLogger(__name__)


async def search_available(tenant_id: str) -> bool:
    try:
        return bool(await ProviderRouter().available_providers(main_id=tenant_id))
    except Exception:
        # Configuration lookup failure must not expose a tool that cannot run,
        # or prevent the rest of the conversation from starting.
        logger.exception("public_search_availability_check_failed tenant_id=%s", tenant_id)
        return False
