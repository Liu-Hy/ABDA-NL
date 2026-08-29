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
7. The gate runs one public-example read through each client. When prompted,
   revoke the same token in the browser and type `TOKEN_REVOKED` in the shell.
8. Copy back only the final content-free status block and shell exit code.

The gate uses ephemeral Codex state, an isolated temporary Claude configuration,
a read-only Codex sandbox, disabled Claude built-in tools, hard client timeouts,
and a strict `list_examples` allowlist. It deletes all raw transcripts and the
temporary Claude configuration on exit.

Pass criteria:

- The generated Claude command is accepted with the intended argument boundary.
- Both clients call `list_examples` exactly once and receive the bundled public
  examples.
- A direct HTTPS check returns `401` after browser revocation.
- Neither client can access MCP with the revoked token.
- No private project tool or ABDA-NL model provider is called.

## Scoped write, version, and proposal test

Create a separate 30-day credential named `MCP write acceptance` with all three
permissions. Use the separate scoped-write gate for the exact client tool
allowlist. The read gate intentionally cannot perform this workflow.

Ask the client to perform this exact bounded workflow:

1. Create one disposable private project named `MCP acceptance 2026-08-29`
   from the bundled `fire_prevention` example.
2. Read the project and retain its current integer version.
3. Change only its description, using that exact expected version.
4. Repeat a metadata update with the stale earlier version and confirm the
   server rejects it as a version conflict.
5. Read the accepted project version.
6. Ask `propose_project_edit` for one simple, harmless change. Confirm the tool
   returns a proposal and advisory review, then read the project again and
   confirm its version did not change.
7. Do not call `apply_project_ops` on the proposal.

Delete the disposable project from the browser, revoke the credential, and
confirm one further MCP read fails authentication. Unset the environment value.

## Content-free receipt

Record only:

```text
read_client_gate: passed
scoped_write: passed
stale_version_rejected: passed
proposal_did_not_apply: passed
disposable_project_removed: passed
all_acceptance_tokens_revoked: passed
result: LIVE_CODEX_AND_CLAUDE_MCP_ACCEPTANCE_VERIFIED
```

Do not record token prefixes, project identifiers, project names returned by
the server, account email, tool payloads, or agent transcripts.

## References

- [Codex MCP configuration](https://developers.openai.com/codex/mcp/)
- [Claude Code MCP configuration](https://code.claude.com/docs/en/mcp)
