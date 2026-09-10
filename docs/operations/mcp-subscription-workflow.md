# MCP exploration with a client subscription

Codex or Claude Code can use its own subscribed model to explore an ABDA
scenario and make an authorized edit. Create a personal MCP token with
`projects:read` and `projects:write`. These tools work with no ABDA credit:
they return scenario data and deterministic argumentation results, or save an
explicit project edit. Keep the token in an environment variable and use the
client configuration shown by the demo when creating it.

An example task for either client is:

> Read the Prescribed Burn example and make a private copy. Explain the
> current conclusion about whether burning is legal today. Show me how
> removing the permit assumption would change it. After I approve that edit,
> apply it at the version you read and verify the resulting conclusion.

The optional `ask_project` and `propose_project_edit` tools invoke ABDA's
server model. They require `llm:use` and consume ABDA credit even when the
client has its own subscription. A proposal never applies itself. The client
can instead construct its own diff operation from `get_project`, show it for
approval, and call `apply_project_ops` directly. MCP advertises the same
qualified funded model pool as the browser. Its write schemas describe the
available operation types and required fields.

The remote HTTP and bearer-token configuration follows the official
[Codex MCP documentation](https://learn.chatgpt.com/docs/extend/mcp?surface=cli)
and [Claude Code MCP documentation](https://code.claude.com/docs/en/mcp).

## Repeatable client acceptance

The launcher
[mcp_client_acceptance.py](../../app/cli/mcp_client_acceptance.py) runs a
bounded task in an already authenticated client. It uses one new private copy
of the public Prescribed Burn scenario. The task explicitly authorizes only
toggling its permit assumption once. The launcher permits only example
discovery, project creation, reads, and application of operations. Provider API
keys and gateway environment settings are removed from the child process, and
server LLM tools are excluded. Its preflight requires the token to lack
`llm:use`, proving that the task cannot bill ABDA's model providers.

Run each client once with a separate disposable token belonging to a
disposable verified account with zero ABDA credit. Existing client subscription
authentication is required. The launcher does not start the demo; on Delta,
use the repository's normal `demo` launcher first.

Before starting a model turn, the launcher checks the client's local login
status and rejects stored API-key authentication. This keeps acceptance on
the existing subscriptions as well as preventing ABDA provider charges.

```sh
python -m app.cli.mcp_client_acceptance \
  --client codex \
  --endpoint https://demo.abda-nl.org/mcp/ \
  --receipt /protected/path/codex-mcp-acceptance.json
python -m app.cli.mcp_client_acceptance \
  --client claude-code \
  --endpoint https://demo.abda-nl.org/mcp/ \
  --receipt /protected/path/claude-mcp-acceptance.json
```

The token is read from `ABDA_NL_MCP_TOKEN`, or the variable named by
`--token-env`. It is never included in process arguments or printed. Receipt
files are created exclusively with mode 600. Each receipt identifies the
bounded cleanup project and records client/server versions. Raw transcripts
remain in memory and are not included in the report. Existing receipt files
are not overwritten by a new run.

Success requires actual client tool calls for discovery, creation, a read
before editing, exactly one authorized edit, and a subsequent read. A model's
claim of success is insufficient. The launcher independently reads the saved
project, confirms the changed grounded outcome, checks stale-version and
invalid-operation rejection, and proves those rejected edits did not mutate
the accepted result. It prints
`MCP_SUBSCRIPTION_WORKFLOW_VERIFIED` only after these checks.

The acceptance task explicitly requires both `get_project` calls, even when
the create and apply responses already contain project snapshots. A real
Claude Code run otherwise skipped those reads. A client authentication
failure retains a `client_failed` cleanup receipt. A concurrent Claude Code
OAuth refresh gets a bounded diagnostic without printing client output or
credentials. Check for any created project before retrying a failed turn.

Complete acceptance by checking the same project in the browser, recording
zero changes in the account's usage and reservation ledgers, checking a second
account cannot access or edit it, archiving the disposable project, and
revoking its personal token. Then run the same command with
`--verify-revoked` to verify repeated protocol rejection. This final flag tests
HTTP authentication, not another model turn. The older
[read-client gate](../../deploy/azure/gate10-mcp-read-client-acceptance.sh)
can separately exercise revocation through both real clients.

`tests/test_mcp.py` covers successful full protocol workflows with zero credit,
scope/ownership/version failures, browser readback, repeated revocation, and
exact server-tool ledger deductions using injected model responses.
`tests/test_mcp_client_acceptance.py` checks that the new launcher rejects
incomplete, failed, or out-of-scope tool evidence. These local tests do not
substitute for a dated successful run of both actual clients. Optional live
server-LLM acceptance must use the shared CloudBank-only evaluation budget.
Do not run the older scoped-write gate's paid proposal outside that budget.

The [September 9, 2026 acceptance receipt](mcp-client-acceptance-20260909.md)
records successful subscribed Codex and Claude Code workflows against the
local Delta demo, including browser readback, ownership denial, accounting,
and cleanup. It does not certify the hosted service.
