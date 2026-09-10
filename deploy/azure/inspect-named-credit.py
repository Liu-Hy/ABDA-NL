#!/usr/bin/env python3
"""Inspect the five approved hosted credit accounts without changing cloud or DB state."""
from __future__ import annotations

import argparse
import base64
from copy import deepcopy
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import shlex
import subprocess
import sys


SUBSCRIPTION = "00e62f6e-2174-40b2-b428-8ebfd7c2ac54"
TENANT = "040f05eb-33ab-462f-af54-fb4bedb055ae"
OPERATOR = "hliu2@cloudbank.org"
GROUP = "abda-nl-staging"
APP = "abda-nl-stg-web"
MARKER = "ABDA_NAMED_CREDIT_READ_ONLY "

# The deployed image supplies its existing restricted database credentials.
# Raw SQL avoids importing a newer ORM model before migration 0006 exists.
RUNNER = r'''
import json, os
from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL

EMAILS = (
    "hl57@illinois.edu", "ludaesch@illinois.edu", "bowers@gonzaga.edu",
    "caminadam@cardiff.ac.uk", "tmcphill@illinois.edu",
)

def main():
    database = os.environ.get("ABDA_DATABASE_URL")
    if not database:
        database = URL.create("postgresql+psycopg", username=os.environ["ABDA_DATABASE_APP_LOGIN"],
            password=os.environ["ABDA_DATABASE_APP_PASSWORD"], host=os.environ["ABDA_POSTGRES_HOST"],
            port=5432, database="abda", query={"sslmode": "require"})
    engine = create_engine(database, connect_args={"connect_timeout": 15})
    if engine.dialect.name != "postgresql":
        raise RuntimeError("this inspection requires the hosted PostgreSQL database")
    with engine.connect().execution_options(isolation_level="REPEATABLE READ") as connection:
        connection.execute(text("SET TRANSACTION READ ONLY"))
        connection.execute(text("SET LOCAL statement_timeout = '15s'"))
        report = {
            "database_read_only": connection.execute(text("SHOW transaction_read_only")).scalar_one() == "on",
            "schema": list(connection.execute(text("SELECT version_num FROM alembic_version")).scalars()),
            "entitlement_table_exists": connection.execute(text(
                "SELECT to_regclass('public.named_credit_entitlements') IS NOT NULL"
            )).scalar_one(),
            "accounts": [],
        }
        for email in EMAILS:
            rows = list(connection.execute(text("""
                SELECT u.id, u.status, u.email_verified,
                       g.program_key, g.granted_microusd, g.spent_microusd, g.reserved_microusd
                FROM users u LEFT JOIN trial_grants g ON g.user_id = u.id
                WHERE lower(u.email) = :email
            """), {"email": email}).mappings())
            if len(rows) > 1:
                raise RuntimeError("ambiguous named account")
            account = {"email": email, "registered": bool(rows)}
            if rows:
                row = rows[0]
                account.update({key: row[key] for key in (
                    "status", "email_verified", "program_key", "granted_microusd",
                    "spent_microusd", "reserved_microusd",
                )})
                account["reservation_summary"] = [dict(item) for item in connection.execute(text("""
                    SELECT program_key, status, count(*) AS count,
                           sum(reserved_microusd) AS reserved_microusd,
                           sum(coalesce(actual_microusd, 0)) AS actual_microusd
                    FROM usage_reservations WHERE user_id = :user_id
                    GROUP BY program_key, status ORDER BY program_key, status
                """), {"user_id": row["id"]}).mappings()]
            if report["entitlement_table_exists"]:
                entitlement = connection.execute(text("""
                    SELECT user_id IS NOT NULL AS linked, bound_at IS NOT NULL AS bound
                    FROM named_credit_entitlements WHERE email = :email
                """), {"email": email}).mappings().one_or_none()
                account["entitlement"] = dict(entitlement) if entitlement is not None else None
            report["accounts"].append(account)
        report["programs"] = [dict(item) for item in connection.execute(text("""
            SELECT p.key, p.enabled, p.max_users, p.grant_microusd, p.budget_microusd,
                   p.activation_count, p.allocated_microusd, p.spent_microusd,
                   (SELECT count(*) FROM trial_grants g WHERE g.program_key = p.key) AS actual_grant_count,
                   (SELECT coalesce(sum(g.granted_microusd), 0) FROM trial_grants g WHERE g.program_key = p.key) AS actual_granted_microusd,
                   (SELECT coalesce(sum(g.spent_microusd), 0) FROM trial_grants g WHERE g.program_key = p.key) AS actual_spent_microusd,
                   (SELECT coalesce(sum(g.reserved_microusd), 0) FROM trial_grants g WHERE g.program_key = p.key) AS actual_reserved_microusd
            FROM trial_programs p ORDER BY p.key
        """)).mappings()]
        report["pending_reservations"] = [dict(item) for item in connection.execute(text("""
            SELECT program_key, count(*) AS count, sum(reserved_microusd) AS reserved_microusd
            FROM usage_reservations WHERE status = 'pending' GROUP BY program_key ORDER BY program_key
        """)).mappings()]
        report["emergency_budget"] = [dict(item) for item in connection.execute(text("""
            SELECT key, enabled, hard_limit_microusd, spent_microusd, reserved_microusd
            FROM emergency_budgets ORDER BY key
        """)).mappings()]
        connection.rollback()
    engine.dispose()
    print("ABDA_NAMED_CREDIT_READ_ONLY " + json.dumps(report, sort_keys=True), flush=True)

try:
    main()
except Exception:
    print("ABDA_NAMED_CREDIT_INSPECTION_FAILED", flush=True)
    raise SystemExit(1)
'''


class InspectionError(RuntimeError):
    """Messages are fixed and contain no raw Azure or database output."""


def read_only_job_template(application: dict, job: dict, postgres: dict) -> dict:
    """Render one execution override using only the restricted application DB role."""
    web = application.get("properties", {}).get("template", {}).get("containers", [])
    if (application.get("name") != APP or len(web) != 1 or web[0].get("name") != "web"
            or not re.fullmatch(r"ghcr\.io/liu-hy/abda-nl@sha256:[0-9a-f]{64}", web[0].get("image", ""))):
        raise InspectionError("the existing immutable web image boundary changed")
    properties = job["properties"]
    config = properties["configuration"]
    if (job.get("name") != "abda-nl-stg-migrate" or config.get("triggerType") != "Manual"
            or config.get("replicaRetryLimit") != 0
            or config.get("manualTriggerConfig") != {"parallelism": 1, "replicaCompletionCount": 1}
            or "app-database-password" not in {item["name"] for item in config.get("secrets", [])}):
        raise InspectionError("the existing manual job boundary changed")
    template = deepcopy(properties["template"])
    if len(template.get("containers", [])) != 1 or template["containers"][0]["name"] != "migrate":
        raise InspectionError("the existing migration container contract changed")
    container = template["containers"][0]
    entries = {entry["name"]: entry for entry in container.get("env", [])}
    login = entries.get("ABDA_DATABASE_APP_LOGIN", {}).get("value")
    if login != "abda_app" or postgres.get("name") != "abda-nl-stg-postgres-bgjhpbgw":
        raise InspectionError("the existing restricted PostgreSQL boundary changed")
    host = postgres.get("fullyQualifiedDomainName")
    if not isinstance(host, str) or not host.endswith(".postgres.database.azure.com"):
        raise InspectionError("the existing PostgreSQL hostname is invalid")
    encoded = base64.b64encode(RUNNER.encode()).decode()
    container.update(image=web[0]["image"],
                     command=["/opt/venv/bin/python"],
                     args=["-c", f"exec(__import__('base64').b64decode('{encoded}'))"],
                     env=[{"name": "ABDA_DATABASE_APP_LOGIN", "value": login},
                          {"name": "ABDA_DATABASE_APP_PASSWORD", "secretRef": "app-database-password"},
                          {"name": "ABDA_POSTGRES_HOST", "value": host}])
    return template


def azure(command: list[str], environment: dict[str, str], *, timeout: int = 60) -> str:
    executable = Path.home() / ".local/share/abda-azure/cli/bin/az"
    if not executable.is_file():
        raise InspectionError("the authorized private Azure CLI is unavailable")
    result = subprocess.run(  # noqa: S603, command is an argv list built below; no shell is used.
        [str(executable), *command, "--only-show-errors"], env=environment,
        capture_output=True, text=True, timeout=timeout, check=False,
    )
    if result.returncode:
        # Known console failure is safe to classify without exposing its URL or token.
        combined = result.stdout + result.stderr
        if "Handshake status 404" in combined:
            raise InspectionError("the existing container exec channel returned handshake 404; do not retry unchanged")
        raise InspectionError("the protected Azure read or console operation failed")
    return result.stdout


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--expected-revision", required=True)
    parser.add_argument("--output", type=Path, help="create a mode-600 sanitized JSON receipt")
    parser.add_argument("--write-job-template", type=Path,
                        help="prepare an execution-only read-only probe; do not start the job")
    args = parser.parse_args(argv)
    try:
        environment = dict(os.environ)
        environment.update(
            AZURE_CONFIG_DIR=str(Path.home() / ".local/share/abda-azure/config"),
            AZURE_CORE_COLLECT_TELEMETRY="false", AZURE_LOGGING_ENABLE_LOG_FILE="false",
            AZURE_EXTENSION_USE_DYNAMIC_INSTALL="no",
        )
        identity = json.loads(azure(["account", "show", "--output", "json"], environment))
        if (identity.get("id"), identity.get("tenantId"), identity.get("user", {}).get("name", "").lower(), identity.get("state")) != (SUBSCRIPTION, TENANT, OPERATOR, "Enabled"):
            raise InspectionError("the Azure session is outside the authorized identity boundary")
        application = json.loads(azure(["containerapp", "show", "--name", APP,
            "--resource-group", GROUP, "--output", "json"], environment))
        properties = application["properties"]
        if properties.get("latestReadyRevisionName") != args.expected_revision:
            raise InspectionError("the live ready revision changed; inspect it before proceeding")
        containers = properties["template"]["containers"]
        if len(containers) != 1 or containers[0]["name"] != "web":
            raise InspectionError("the existing web container contract changed")
        if args.write_job_template:
            job = json.loads(azure(["containerapp", "job", "show", "--name", "abda-nl-stg-migrate",
                "--resource-group", GROUP, "--output", "json"], environment))
            postgres = json.loads(azure(["postgres", "flexible-server", "show", "--name", "abda-nl-stg-postgres-bgjhpbgw",
                "--resource-group", GROUP, "--output", "json"], environment))
            template = read_only_job_template(application, job, postgres)
            descriptor = os.open(args.write_job_template, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(descriptor, "w") as stream:
                json.dump(template, stream, indent=2)
            print("READ_ONLY_NAMED_CREDIT_JOB_TEMPLATE_READY job_started=false administrator_secret_used=false")
            return 0
        replicas = json.loads(azure(["containerapp", "replica", "list", "--name", APP,
            "--resource-group", GROUP, "--revision", args.expected_revision, "--output", "json"], environment))
        if not replicas:
            raise InspectionError("the expected live revision has no replica")
        encoded = base64.b64encode(RUNNER.encode()).decode()
        command = shlex.join(["/opt/venv/bin/python", "-c", f"exec(__import__('base64').b64decode('{encoded}'))"])
        output = azure(["containerapp", "exec", "--name", APP, "--resource-group", GROUP,
            "--revision", args.expected_revision, "--replica", replicas[0]["name"],
            "--container", "web", "--command", command], environment, timeout=60)
        receipts = [line.partition(MARKER)[2].strip() for line in output.splitlines() if MARKER in line]
        if len(receipts) != 1:
            raise InspectionError("the read-only probe did not return exactly one receipt")
        report = json.loads(receipts[0])
        if report.get("database_read_only") is not True:
            raise InspectionError("the database did not confirm a read-only transaction")
        report.update(inspected_utc=datetime.now(timezone.utc).isoformat(),
                      application=APP, revision=args.expected_revision,
                      image=containers[0]["image"], cloud_resources_changed=False)
        rendered = json.dumps(report, indent=2) + "\n"
        if args.output:
            descriptor = os.open(args.output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(descriptor, "w") as stream:
                stream.write(rendered)
        print(rendered, end="")
        return 0
    except InspectionError as error:
        print(f"Named credit inspection stopped: {error}", file=sys.stderr)
    except Exception:
        print("Named credit inspection failed; raw Azure and database output was suppressed.", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
