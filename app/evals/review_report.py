"""Attach explicit answer inspection to an immutable evaluation report."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from app.evals.evidence import apply_semantic_reviews


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--reviews", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = json.loads(args.report.read_text(encoding="utf-8"))
    reviews = json.loads(args.reviews.read_text(encoding="utf-8"))
    report = apply_semantic_reviews(report, reviews)
    if args.output.resolve() == args.report.resolve():
        raise ValueError("keep the original untuned evaluation report; write review evidence to a new file")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"application_accepted": report["application_accepted"], "output": str(args.output)}))
    return 0 if report["gate_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
