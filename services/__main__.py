"""Entry point for ``python -m services`` from the repository root."""

from services.run_backends import main

if __name__ == "__main__":
    raise SystemExit(main())
