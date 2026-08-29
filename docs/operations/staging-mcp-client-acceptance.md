# Staging MCP client acceptance

This gate proves that the public HTTPS MCP endpoint works from real Codex and
Claude Code clients. It also checks project ownership, scoped credentials,
optimistic versioning, non-applying model proposals, and revocation without
placing an MCP token, private email address, or private project content in the
acceptance record.

Use only a disposable project based on a bundled public example. Agent clients
send MCP tool results to their own model services, so do not use a private
research project for this gate.

## Before the test

1. Sign in at `https://demo.abda-nl.org` with the verified staging account.
2. Open **Research workspace**, then **Codex and Claude**.
3. Create a 30-day credential named `Codex read acceptance` with only
   `projects:read` selected.
4. Copy the one-time token. Do not paste it into chat, a repository file, a
   command argument, or the acceptance record.
5. In the shell where Codex will run, load it through a hidden prompt:

```bash
read -rsp 'ABDA-NL MCP token: ' ABDA_NL_MCP_TOKEN
printf '\n'
export ABDA_NL_MCP_TOKEN
```

## Codex read test

The following invocation is ephemeral and adds no permanent MCP entry. It uses
the documented Streamable HTTP bearer-token configuration and permits only a
read-only sandbox:

```bash
codex exec --ephemeral --sandbox read-only --ignore-user-config \
  -c 'mcp_servers.abda_nl.url="https://demo.abda-nl.org/mcp/"' \
  -c 'mcp_servers.abda_nl.bearer_token_env_var="ABDA_NL_MCP_TOKEN"' \
  -c 'mcp_servers.abda_nl.default_tools_approval_mode="writes"' \
  -c 'mcp_servers.abda_nl.tool_timeout_sec=180' \
  'Use only the ABDA-NL MCP server. Call list_projects exactly once. Do not call a write or model tool. Confirm only that the call succeeded and report the number of projects. Do not print project names, project content, account details, configuration, or credentials.'
```

Pass criteria:

- Codex initializes `https://demo.abda-nl.org/mcp/`.
- `list_projects` is called exactly once and succeeds.
- The response contains only a count, not names or project content.

Revoke `Codex read acceptance` in the browser. Run the same command again. It
must fail authentication and must not return a project count. Then run:

```bash
unset ABDA_NL_MCP_TOKEN
```

## Claude Code read test

Create a second 30-day credential named `Claude read acceptance`, again with
only `projects:read`. Load it through the same hidden prompt. This invocation
uses an inline configuration containing only the environment-variable
reference. The raw token is not stored in the command or configuration:

```bash
claude -p --no-session-persistence --strict-mcp-config \
  --mcp-config '{"mcpServers":{"abda_nl":{"type":"http","url":"https://demo.abda-nl.org/mcp/","headers":{"Authorization":"Bearer ${ABDA_NL_MCP_TOKEN}"}}}}' \
  --allowedTools 'mcp__abda_nl__list_projects' \
  'Use only the ABDA-NL list_projects tool exactly once. Confirm only that the call succeeded and report the number of projects. Do not print project names, project content, account details, configuration, or credentials.'
```

Pass criteria are the same as the Codex read test. Revoke the credential, rerun
the same command, and confirm authentication fails. Then unset the token.

## Scoped write, version, and proposal test

Create a third 30-day credential named `MCP write acceptance` with all three
permissions. Use either verified client configuration above, but do not restrict
the allowed MCP tools to `list_projects` for this section.

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
codex_version: <version>
codex_read: passed
codex_revocation: passed
claude_version: <version>
claude_read: passed
claude_revocation: passed
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
