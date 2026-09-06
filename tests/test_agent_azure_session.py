"""Exercise the private login handoff without contacting Azure or handling tokens."""

from __future__ import annotations

import json
import os
from pathlib import Path
import stat
import subprocess
import sys

import pytest


SCRIPT = Path(__file__).resolve().parents[1] / "deploy/azure/agent-azure-session.sh"
ACCOUNT = {
    "subscription": "00e62f6e-2174-40b2-b428-8ebfd7c2ac54",
    "tenant": "040f05eb-33ab-462f-af54-fb4bedb055ae",
    "user": "hliu2@cloudbank.org",
    "state": "Enabled",
}


@pytest.fixture
def private_cli(tmp_path):
    root = tmp_path / "abda-azure"
    binary_dir = root / "cli/bin"
    binary_dir.mkdir(parents=True)
    (binary_dir / "python").symlink_to(sys.executable)
    cli = binary_dir / "az"
    cli.write_text(
        '#!/usr/bin/env bash\n'
        'printf "%s\\n" "$*" >> "$ABDA_TEST_CALLS"\n'
        'case "$1 ${2:-}" in\n'
        '  "account show") printf "%s\\n" "$ABDA_TEST_ACCOUNT" ;;\n'
        '  "login --tenant"|"account set"|"logout --only-show-errors") ;;\n'
        '  *) exit 90 ;;\n'
        'esac\n'
    )
    cli.chmod(0o700)
    calls = tmp_path / "calls"
    env = {
        **os.environ,
        "ABDA_AZURE_ROOT": str(root),
        "ABDA_TEST_CALLS": str(calls),
        "ABDA_TEST_ACCOUNT": json.dumps(ACCOUNT),
    }
    return root, calls, env


def run_helper(env, action):
    return subprocess.run(
        ["bash", str(SCRIPT), action],
        env=env,
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )


def test_login_is_tenant_pinned_and_creates_private_profile(private_cli):
    root, calls, env = private_cli
    result = run_helper(env, "login")
    assert result.returncode == 0, result.stderr
    assert "ABDA_AGENT_AZURE_SESSION_READY" in result.stdout
    assert calls.read_text().splitlines() == [
        f"login --tenant {ACCOUNT['tenant']} --use-device-code --output none",
        f"account set --subscription {ACCOUNT['subscription']} --only-show-errors",
        "account show --only-show-errors --query "
        "{subscription:id,tenant:tenantId,user:user.name,state:state} --output json",
    ]
    assert stat.S_IMODE(root.stat().st_mode) == 0o700
    assert stat.S_IMODE((root / "config").stat().st_mode) == 0o700


@pytest.mark.parametrize("field", ["subscription", "tenant", "user", "state"])
def test_mismatched_identity_is_refused(private_cli, field):
    _, _, env = private_cli
    env["ABDA_TEST_ACCOUNT"] = json.dumps({**ACCOUNT, field: "wrong"})
    result = run_helper(env, "status")
    assert result.returncode != 0
    assert "ABDA_AGENT_AZURE_SESSION_READY" not in result.stdout
    assert "identity or subscription" in result.stderr


def test_missing_account_is_refused_without_login(private_cli):
    _, calls, env = private_cli
    env["ABDA_TEST_ACCOUNT"] = ""
    result = run_helper(env, "status")
    assert result.returncode != 0
    assert "azure_session: unavailable" in result.stderr
    assert calls.read_text().startswith("account show ")
    assert "login " not in calls.read_text()


def test_symlinked_config_is_refused_before_cli_call(private_cli, tmp_path):
    root, calls, env = private_cli
    (root / "config").symlink_to(tmp_path)
    result = run_helper(env, "login")
    assert result.returncode != 0
    assert "not private" in result.stderr
    assert not calls.exists()


def test_logout_only_calls_local_logout(private_cli):
    _, calls, env = private_cli
    result = run_helper(env, "logout")
    assert result.returncode == 0
    assert "ABDA_AGENT_AZURE_SESSION_LOGGED_OUT" in result.stdout
    assert calls.read_text() == "logout --only-show-errors\n"
