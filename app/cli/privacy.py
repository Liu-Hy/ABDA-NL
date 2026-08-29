"""Operator-only access export and two-phase permanent account deletion."""

from __future__ import annotations

import argparse
import getpass
import json
import os
from pathlib import Path
import stat
import sys
from typing import Any, Sequence

from app.db.session import database_is_ready, get_session_factory
from app.services.privacy_requests import (
    PrivacyRequestError,
    delete_privacy_account,
    export_privacy_account,
    inspect_privacy_account,
    prepare_privacy_deletion,
    public_receipt,
    public_summary,
    validate_privacy_request_reference,
)


_EMAIL_ENV = "ABDA_PRIVACY_USER_EMAIL"
_CONFIRMATION_ENV = "ABDA_PRIVACY_CONFIRMATION"


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="abda-nl-privacy",
        description="Inspect, export, or permanently delete one verified ABDA-NL account",
    )
    parser.add_argument(
        "--email-env",
        default=_EMAIL_ENV,
        help="environment variable containing the verified account email",
    )
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("inspect", help="show content-free account counts")

    export = commands.add_parser(
        "export",
        help="write a private user access export to a new mode-600 JSON file",
    )
    export.add_argument("--output", required=True, type=Path)

    for name, help_text in (
        (
            "prepare-delete",
            "suspend the account and revoke share and MCP bearer access",
        ),
        ("delete", "permanently remove the prepared account and private content"),
    ):
        command = commands.add_parser(name, help=help_text)
        command.add_argument("--request-reference", required=True)
        command.add_argument(
            "--execute",
            action="store_true",
            help="perform the mutation after the exact environment confirmation",
        )
    return parser


def _email_from_environment(name: str) -> str:
    value = os.getenv(name)
    if value:
        return value
    if sys.stdin.isatty():
        return getpass.getpass("Verified ABDA-NL account email: ")
    raise PrivacyRequestError(
        f"set {name} or run interactively so the account email never enters shell history"
    )


def _json_ready(value: dict[str, Any]) -> str:
    return json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False)


def _write_private_export(path: Path, payload: dict[str, Any]) -> Path:
    target = path.expanduser().resolve()
    parent = target.parent
    if not parent.is_dir():
        raise PrivacyRequestError("the export parent directory does not exist")
    parent_mode = stat.S_IMODE(parent.stat().st_mode)
    if parent_mode & 0o077:
        raise PrivacyRequestError(
            "the export parent directory must not grant group or other permissions"
        )
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        descriptor = os.open(target, flags, 0o600)
    except FileExistsError as exc:
        raise PrivacyRequestError("the export output already exists") from exc
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, sort_keys=True, ensure_ascii=False)
            handle.write("\n")
    except Exception:
        target.unlink(missing_ok=True)
        raise
    if stat.S_IMODE(target.stat().st_mode) != 0o600:
        target.unlink(missing_ok=True)
        raise PrivacyRequestError("the private export did not receive mode 600")
    return target


def _confirmation(action: str, request_reference: str) -> str:
    return f"{action}:{request_reference}"


def _require_confirmation(action: str, request_reference: str) -> None:
    expected = _confirmation(action, request_reference)
    if os.getenv(_CONFIRMATION_ENV) != expected:
        raise PrivacyRequestError(
            f"set {_CONFIRMATION_ENV} to the exact value {expected!r} for this one operation"
        )


def _run(args: argparse.Namespace) -> dict[str, Any]:
    if not database_is_ready():
        raise PrivacyRequestError("the configured ABDA-NL database is not ready")
    email = _email_from_environment(args.email_env)
    with get_session_factory()() as session:
        if args.command == "inspect":
            return {
                "action": "inspect",
                "account": public_summary(inspect_privacy_account(session, email)),
                "mutated": False,
            }
        if args.command == "export":
            target = _write_private_export(
                args.output,
                export_privacy_account(session, email),
            )
            return {
                "action": "export",
                "mutated": False,
                "output": str(target),
                "output_mode": "0600",
            }

        request_reference = validate_privacy_request_reference(args.request_reference)
        summary = inspect_privacy_account(session, email)
        action = "PREPARE" if args.command == "prepare-delete" else "DELETE"
        if not args.execute:
            return {
                "action": args.command,
                "account": public_summary(summary),
                "confirmation": _confirmation(action, request_reference),
                "mutated": False,
            }
        _require_confirmation(action, request_reference)
        if args.command == "prepare-delete":
            prepared = prepare_privacy_deletion(
                session,
                email,
                request_reference=request_reference,
            )
            return {
                "action": "prepare-delete",
                "account": public_summary(prepared),
                "mutated": True,
            }
        receipt = delete_privacy_account(
            session,
            email,
            request_reference=request_reference,
        )
        return {
            "action": "delete",
            "mutated": True,
            "receipt": public_receipt(receipt),
        }


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        result = _run(args)
    except PrivacyRequestError as exc:
        print(f"privacy operation refused: {exc}", file=sys.stderr)
        return 1
    except Exception:
        print(
            "privacy operation failed; the database transaction was rolled back",
            file=sys.stderr,
        )
        return 1
    print(_json_ready(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
