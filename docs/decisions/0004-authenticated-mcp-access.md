# ADR 0004: Authenticated MCP access

Status: Accepted

Date: 2026-08-17

## Context

ABDA-NL should let registered researchers use their private projects from
Codex and Claude Code. The integration must not weaken project ownership,
optimistic updates, trial accounting, or BYOK secrecy. The server must also
remain compatible with an ordinary local run, the Delta loopback demo, and a
future public HTTPS deployment.

Codex and Claude Code both support remote Streamable HTTP MCP servers with a
bearer token. MCP OAuth would improve one-click setup later, but a partial or
fake authorization server is worse than a clear personal-token flow. In
particular, protected-resource metadata must not advertise an authorization
server that cannot issue tokens accepted by this service.

The official MCP Python SDK 2.0 is the maintained protocol implementation. It
requires Python 3.10 or newer, serves current and previous protocol clients,
and provides stateless Streamable HTTP transport. Its HTTP session manager is
intentionally single-use for one ASGI lifespan.

## Decision

ABDA-NL uses verified-account personal access tokens for the first public MCP
release. A token has 256 bits of random secret material and the `abda_mcp_`
marker. It is returned only by the creation response. The database stores a
short display prefix and an HMAC-SHA-256 digest keyed by the dedicated
`ABDA_MCP_TOKEN_PEPPER` secret. Production requires this pepper to differ from
the browser session secret.

Tokens expire after 90 days by default and cannot exceed 365 days. A user can
have at most ten active tokens. Token creation locks the user row before
counting active credentials, which makes this cap deterministic on PostgreSQL.
Revocation is immediate. Last-use timestamps are persisted at most once per
hour to retain useful security evidence without writing on every MCP request.
Suspended users, unverified users, expired tokens, and revoked tokens all
receive the same bearer-authentication failure.

The browser credential endpoints are:

- `GET /api/mcp/tokens`, which never returns a secret
- `POST /api/mcp/tokens`, which returns the new secret once and sets
  `Cache-Control: no-store`
- `DELETE /api/mcp/tokens/{id}`, which revokes an owned token

Token creation and revocation reject cross-origin browser requests. Staging
and production require an `Origin` header that exactly matches the configured
public base URL.

Token creation is rate limited, but revocation is deliberately not rate
limited. Revocation already requires a verified session, an exact same-origin
request, and ownership of the selected credential. A creation throttle must
never prevent a user from disabling a credential that may be exposed.

The MCP endpoint is `/mcp/`. It uses the official SDK's stateless Streamable
HTTP implementation and its bearer-authentication components. Static personal
tokens do not enable or advertise MCP OAuth metadata. A later OAuth
authorization server can issue the same logical scopes without changing the
tool authorization layer.

The host application constructs a fresh MCP runtime for every FastAPI
lifespan. A small mounted proxy delegates requests to that runtime. This
matches the SDK lifecycle contract in production and also lets tests start and
stop the application repeatedly without reusing a closed session manager.

DNS rebinding protection allows loopback hosts for local and Delta use, the
test host in tests, and the exact configured public host in managed
deployments. The production endpoint is usable only behind HTTPS even though
Delta continues to serve it through a local SSH tunnel.

## Scopes and tools

Tokens carry an ordered subset of three scopes:

| Scope | Tools |
| --- | --- |
| `projects:read` | `list_examples`, `get_example`, `list_projects`, `get_project` |
| `projects:write` | `create_project`, `apply_project_ops`, `update_project_metadata` |
| `llm:use` | `ask_project`, `propose_project_edit` |

Every private-project query includes the authenticated internal user ID.
Unknown and cross-user project IDs have the same not-found result. Write tools
reuse the existing project service and require `expected_version`, so an agent
cannot silently overwrite a browser edit or another agent call.

Expected edit, schema, argument-construction, and computation-limit failures are
returned as stable, actionable tool errors. Complexity and construction details
are summarized rather than exposing internal exception text. Unexpected
failures retain only exception type and source location in the server log and
return a generic retry message to the client.

Read tools return compact grounded outcome summaries by default. A caller can
request the complete argument graph when it is actually needed. Tool
annotations mark project mutations and metered LLM calls as writes, which lets
clients apply appropriate approval policies.

The LLM tools use the existing quality-gated router and the authenticated
user's trial ledger. Their public schema exposes only profiles that have passed
the application quality gate. `propose_project_edit` returns a reviewed
operation and the current expected version but never applies it. The caller
must review the result and invoke `apply_project_ops` separately.

MCP tools do not accept BYOK credentials. Passing a provider key through an
agent tool argument could place it in transcripts, approval views, or client
logs. BYOK remains available through the browser's one-request flow, where the
server already guarantees that the key is not persisted.

## Consequences

- The project minimum is Python 3.10, and Delta uses its Python 3.13 module.
- Production secret management must include a dedicated MCP token pepper.
- Users can connect Codex and Claude Code immediately with a revocable token.
- OAuth login remains a future enhancement and is not implied by current
  server metadata.
- Rotating the MCP pepper invalidates all existing MCP tokens. Operators must
  treat that as an intentional credential reset and notify users.
- MCP availability does not make Delta a public host. Public MCP traffic still
  belongs on the managed HTTPS deployment.

## Sources

- [OpenAI MCP documentation](https://developers.openai.com/codex/mcp)
- [Claude Code MCP documentation](https://code.claude.com/docs/en/mcp)
- [Official MCP Python SDK](https://github.com/modelcontextprotocol/python-sdk)
