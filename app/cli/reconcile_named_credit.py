"""Preview named allocations; use --apply to commit the reviewed reconciliation."""
from __future__ import annotations

import argparse
import json
import sys

from sqlalchemy import inspect

from app.db.session import _require_restricted_postgres_role, get_engine, get_session_factory
from app.services.credit_eligibility import CreditEligibilityError, initialize_credit_eligibility
from app.services.trials import (
    TrialUnavailableError, UsageReservationError, initialize_named_credit,
    reconcile_named_credit,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__,
        epilog=(
            "Explicit reconciliation ignores ABDA_NAMED_CREDIT_AUTO_ACTIVATE. "
            "Stop incompatible database writers before applying allocations."
        ),
    )
    parser.add_argument("--apply", action="store_true", help="commit the reviewed allocation")
    args = parser.parse_args(argv)
    try:
        engine = get_engine()
        if engine.dialect.name == "postgresql":
            _require_restricted_postgres_role(engine)
        if not inspect(engine).has_table("named_credit_entitlements"):
            raise TrialUnavailableError("run the database migrations before reconciling named credit")
        with get_session_factory()() as session:
            # Seeding also rolls back in preview mode. It never changes public
            # grant configuration or the independent OpenRouter budget.
            initialize_named_credit(session)
            initialize_credit_eligibility(session)
            report = reconcile_named_credit(session, apply=args.apply)
        print(json.dumps({"applied": args.apply, "allocations": report}, indent=2))
    except (TrialUnavailableError, UsageReservationError, CreditEligibilityError) as exc:
        print(f"Named credit reconciliation stopped: {exc}", file=sys.stderr)
        return 1
    except Exception:
        # Database connection strings may contain credentials. Do not expose
        # driver exceptions or tracebacks in a review receipt.
        print("Named credit reconciliation failed; no allocation was committed.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
