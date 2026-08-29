# Staging MCP client acceptance

This procedure proves that the public HTTPS MCP endpoint works from real Codex
and Claude Code clients. The first gate uses only bundled public examples and
one disposable read-only token. A later gate checks project ownership,
optimistic versioning, non-applying model proposals, and scoped writes.

Agent clients send MCP tool results to their own model services. The automated
read gate therefore permits only `list_examples`. It never enables private
project tools, creates a project, or calls an ABDA-NL model provider.

## Automated read and revocation gate

1. Sign in at `https://demo.abda-nl.org` with the verified staging account.
2. Open **Research workspace**, then **Codex and Claude**.
3. Create a 30-day credential named `MCP read acceptance` with only
   `projects:read` selected.
4. Inspect the generated Claude command. Confirm that `--` appears after the
   complete `--header` value and before the `abda-nl` server name.
5. Copy the one-time token. Do not paste it into chat, a repository file, a
   command argument, or the acceptance record.
6. Run `deploy/azure/gate10-mcp-read-client-acceptance.sh` from a machine where
   Codex and Claude Code are installed and signed in. Paste the token only at
   the hidden prompt.
7. Confirm the inspected command boundary by typing the exact phrase requested
   in section 3. The gate does not run `claude mcp add` in an isolated first-run
   profile because that unrelated setup path can wait for interactive startup.
8. The gate runs one public-example read through each client. When prompted,
   revoke the same token in the browser and type `TOKEN_REVOKED` in the shell.
9. Copy back only the final content-free status block and shell exit code.

The gate uses ephemeral Codex state, a read-only Codex sandbox, an inline
Claude MCP configuration that references the token only by environment name,
disabled Claude built-in tools, hard client timeouts, and a strict
`list_examples` allowlist. It disables Claude session persistence and deletes
all raw transcripts on exit.

Pass criteria:

- The generated Claude command is accepted with the intended argument boundary.
- Both clients call `list_examples` exactly once and receive the bundled public
  examples.
- A direct HTTPS check returns `401` after browser revocation.
- Neither client can access MCP with the revoked token.
- No private project tool or ABDA-NL model provider is called.

## Scoped write, version, and proposal test

The second gate uses direct MCP protocol calls for deterministic write
acceptance. The real Codex and Claude clients are already covered by the first
gate. Direct calls keep a language-model agent from choosing additional tools
or receiving private project content.

1. Create a 30-day credential named `MCP scope read acceptance` with only
   `projects:read`.
2. Create a separate 30-day credential named `MCP scoped write acceptance`
   with all three permissions.
3. Run `deploy/azure/gate10-mcp-scoped-write-acceptance.sh` from a normal Delta
   terminal. Paste both values only at their hidden prompts.
4. The gate safely proves that the read-only token cannot create a project. Its
   denial probe deliberately names a nonexistent source example, so a broken
   scope check still cannot create anything.
5. The gate creates one disposable project from `fire_prevention`, reads it,
   updates only its description at version 1, and proves a second write with
   stale version 1 is rejected.
6. The gate makes one funded `add-fact` proposal using an instruction already
   covered by the model evaluation suite. It verifies a positive settled cost,
   then proves the complete project payload and version stayed unchanged.
7. When prompted, delete only `MCP scoped acceptance, delete me` from the
   browser. The gate proves the project is no longer accessible.
8. Revoke both acceptance tokens when prompted. The gate proves that both now
   receive HTTP 401.

The gate never calls `apply_project_ops`, prints private MCP payloads, or
changes Azure configuration. Its temporary state is mode 600 and removed on
exit. If it stops after project creation, delete the named disposable project
and revoke both tokens before retrying.

## Content-free receipt

Record only:

```text
read_client_gate: passed
scoped_write: passed
stale_version_rejected: passed
proposal_did_not_apply: passed
funded_proposal_cost_recorded: passed
disposable_project_removed: passed
all_acceptance_tokens_revoked: passed
result: LIVE_CODEX_AND_CLAUDE_MCP_ACCEPTANCE_VERIFIED
```

Do not record token prefixes, project identifiers, project names returned by
the server, account email, tool payloads, or agent transcripts.

## References

- [Codex MCP configuration](https://developers.openai.com/codex/mcp/)
- [Claude Code MCP configuration](https://code.claude.com/docs/en/mcp)
