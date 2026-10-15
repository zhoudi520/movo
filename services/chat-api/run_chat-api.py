"""Local / PyCharm entry: run chat-api in the foreground with mixed-dev defaults."""

from __future__ import annotations

import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from services.dev_launcher import main_chat_api


def main() -> int:
    """Run chat-api uvicorn in the current process."""
    return main_chat_api()


if __name__ == "__main__":
    raise SystemExit(main())
