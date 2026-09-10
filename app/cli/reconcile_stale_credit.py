"""Preview conservative stale-reservation charges; --apply commits the sweep."""
from __future__ import annotations

import argparse
import json
import sys

from app.db.session import _require_restricted_postgres_role, get_session_factory
from app.services.llm_billing import reconcile_stale_llm_reservations


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__,
        epilog=(
            "Expired reservations become conservatively assessed charges, not refunds. "
            "Run with the configured restricted application database role. "
            "This command neither changes program limits nor calls providers."
        ),
    )
    parser.add_argument("--apply", action="store_true", help="commit the conservative sweep")
    args = parser.parse_args(argv)
    try:
        with get_session_factory()() as session:
            if session.get_bind().dialect.name == "postgresql":
                _require_restricted_postgres_role(session.get_bind())
            trial, emergency = reconcile_stale_llm_reservations(session, apply=args.apply)
        print(json.dumps({
            "applied": args.apply,
            "assessment": "full_reserved_amount",
            "trial_reservations": trial,
            "emergency_reservations": emergency,
        }, sort_keys=True))
    except Exception:
        # Driver exceptions can contain credentials and connection strings.
        print("Stale reservation reconciliation failed; no sweep was committed.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
