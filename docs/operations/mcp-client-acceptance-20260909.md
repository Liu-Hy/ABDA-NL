# Subscribed MCP client acceptance, September 9, 2026

Both real clients completed the project workflow against the current local
ABDA working tree. The shared `demo` launcher served ABDA on dt-login03;
the test did not start another server or change the launcher configuration.
This is local acceptance, not certification of the hosted service. The test
window was September 9, 21:20 to 21:25 CDT (September 10, 02:20 to 02:25 UTC).

| Client | Subscribed model | Actual MCP calls | Result |
| --- | --- | --- | --- |
| Codex CLI 0.153.4 | GPT-5.6-sol | 6 | Passed |
| Claude Code 2.1.263 | Claude Sonnet 5 | 6 | Passed |

Each successful transcript contains `list_examples`, `get_example`,
`create_project`, `get_project`, `apply_project_ops`, and `get_project` in
that order. Each client created one private copy of `fire_prevention`, read
version 1, toggled `smp_permit` from active to inactive, and read version 2.
The grounded result for `legal_today` changed from accepted to rejected.
The helper independently confirmed the saved state and rejected stale-version
and invalid-operation writes without any further project change.

Chromium opened both saved projects through the real browser workspace.
The project list displayed version 2, the conclusion card was visible, and
the loaded browser state contained the inactive permit and grounded label
matching the server readback. There were no browser errors or inference
requests. A second account could neither read nor edit each project through
MCP, and the denied requests did not change the saved result.

The clients used separate disposable verified development accounts with
zero ABDA credit. Each token had only `projects:read` and `projects:write`.
The helper explicitly confirmed that `ask_project` was rejected for missing
`llm:use` before model execution. Provider keys and gateway settings were
removed from the client subprocesses, and local subscription authentication
was checked before starting each turn.

Canonical row hashes and counts were identical before and after acceptance
for all six accounting tables: `llm_usage_events`, `usage_reservations`,
`emergency_usage_reservations`, `trial_grants`, `trial_programs`, and
`emergency_budgets`. Existing historical records were preserved. This
acceptance added no usage event, reservation, trial credit, or CloudBank or
OpenRouter charge.

Claude's first turn connected to MCP but encountered a transient subscription
OAuth refresh lock before any project call. The next turn recovered without
changing credentials, created the correct project, and made the authorized
edit, but omitted explicit reads before and after the edit. The helper
correctly rejected that transcript. The acceptance prompt now specifies the
six required calls and explains why both `get_project` calls are necessary.
Claude then passed. No ABDA feature prompt was changed. The helper also now
records a failed client turn and reports a recognized refresh problem without
printing arbitrary client output. Its 21 focused tests passed.

All three disposable projects were archived, including the incomplete Claude
attempt. Both tokens were revoked. Repeating each revocation returned HTTP
204, and repeated MCP initialization using each revoked token returned HTTP
401, including through the helper's `--verify-revoked` mode. Credential
artifacts were kept privately during verification and removed after cleanup.
No account identities, token values, cookies, or raw transcripts are included
in the repository receipt.

The [sanitized JSON receipt](mcp-client-acceptance-20260909.json) records the
client versions, bounded tool sequences, formal outcomes, ledger hashes, and
cleanup results. The [repeatable workflow](mcp-subscription-workflow.md)
describes how to run the same helper against another authorized deployment.
