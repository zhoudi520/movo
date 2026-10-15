"""Local / PyCharm entry: run document-parser Celery worker with mixed-dev defaults."""

from __future__ import annotations

import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from services.dev_launcher import main_document_worker


def main() -> int:
    """Run the document-parser Celery worker in the current process."""
    return main_document_worker()


if __name__ == "__main__":
    raise SystemExit(main())
