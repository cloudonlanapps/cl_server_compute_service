"""Database migration CLI tool.

Run this before starting the compute server to create/upgrade database tables.
"""

from __future__ import annotations

import sys


def main() -> int:
    """Run database migrations."""
    print("Running database migrations...")

    # Ensure CL_SERVER_DIR exists before running migrations
    from .utils import ensure_cl_server_dir, run_migrations

    try:
        _ = ensure_cl_server_dir()
    except SystemExit:
        return 1

    # Run migrations

    try:
        run_migrations()
        print("✓ Database migrations completed successfully")
        return 0
    except (FileNotFoundError, RuntimeError) as e:
        print(f"\nERROR: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
