# ABDA-NL

> **Development branch:** This branch contains experimental hosted-service,
> identity, usage-quota, model-routing, and MCP work. For the stable demo that
> accompanies the COMMA 2026 paper, use [`main`](../../tree/main).

ABDA-NL is a browser-based natural-language scenario explorer for
argument-based reasoning.

## Run the demo

Python 3.10 or newer is supported. Create the local environment and install the
application:

```bash
python3 -m venv .venv
make install
.venv/bin/abda-nl
```

`make install` selects a hash-pinned lock for the active Python version.
Python 3.10 has dedicated locks because several current scientific packages
have ended 3.10 support. Python 3.11 through 3.13 use the main locks. Use
`make install-dev` for the test and browser tooling. Native Python 3.10 and
3.13 CI jobs independently regenerate their locks, so a lock update cannot
silently drop the advertised minimum version.

The last command starts on loopback, waits for the application to be ready,
and opens the default browser. It enables LLM features when a valid local
configuration exists, otherwise it starts the complete deterministic demo.
Use `abda-nl --basic`, `abda-nl --llm`, or `abda-nl --no-browser` to choose
explicit behavior.

For the CloudBank-funded LLM features, place the Azure/Foundry credentials in
the gitignored `.env` file and select Foundry in `.env.local`:

```bash
ABDA_CLAUDE_PROVIDER=foundry
```

The supported fields are `AZURE_ANTHROPIC_ENDPOINT` or
`ANTHROPIC_FOUNDRY_BASE_URL` for the endpoint, and
`AZURE_ANTHROPIC_API_KEY`, `ANTHROPIC_FOUNDRY_API_KEY`, or
`AZURE_OPENAI_API_KEY` for authentication. ABDA-NL also understands an Azure
OpenAI endpoint and derives the matching Foundry Messages endpoint. See the
[CloudBank LLM setup tutorial](https://github.com/Liu-Hy/cloudbank-llm-setup)
for how those values are provisioned.

On NCSA Delta, start the full demo through the user-level launcher:

```bash
demo
```

The launcher uses the repository's `.demo.json`, runs the process detached,
and always serves it through the same bookmarked address,
<http://127.0.0.1:8765>. Run `demo status`, `demo logs`, or `demo stop` from any
directory. On the laptop, keep one ordinary `ssh delta-demo` session open while
using the browser. That session carries the loopback port forward. Run
`demo doctor` on Delta to inspect the pinned launcher profile. This login-node
mode is for short, lightweight development sessions; use a Delta Open OnDemand
or Slurm session for persistent hosting or heavy work.

The server-only repository command remains available on other systems:

```bash
make run
```

Then open <http://127.0.0.1:8000>. `make run-basic` starts the deterministic
argumentation UI without an LLM, `make demo-local` opens a local browser, and
`make test` runs the test suite.

## Funded models and BYOK

Public funded requests require a verified account and an activated trial. The
first 100 successful activations receive $5 of metered model usage. The server
reserves enough credit before each physical provider call and settles the
reservation from the returned token counts.

CloudBank Azure Foundry is the primary funded route. OpenRouter is used only
after bounded retries establish a transport, throttling, or provider-service
failure. The project-paid OpenRouter ledger defaults to a hard $500 cap.
Increasing it above $500 requires an explicit deployment acknowledgement, and
the application refuses values above $1,000.

Registered users may instead include a provider key in the `llm.byok` object of
a `/chat` or `/propose` request. BYOK supports Anthropic, OpenAI, Google Gemini,
and OpenRouter through fixed official endpoints. The key is request-scoped and
is never persisted by the server. BYOK calls do not require or consume trial
credit. Never place an API key in a URL, project record, or share link.

`GET /config` lists the currently available funded profiles and supported BYOK
models without exposing deployment credentials. Candidate funded profiles are
kept out of the public list until they pass the repository evaluation gate.

### Browser workspace

The webpage keeps anonymous example exploration available while placing private
and metered features in the **Workspace** dialog:

1. **Account** signs in through hosted verified-email OIDC in public deployments.
   Local and Delta development use a visibly labeled development login instead.
2. **Projects** saves the current analysis as a private database record. Reopened
   projects continue deterministic changes, grounded chat, and reviewed edits
   from the saved project state. The Save changes button uses an optimistic
   project version so another browser tab cannot be overwritten silently.
3. **AI access** chooses an approved funded profile or an Anthropic, OpenAI,
   Google, or OpenRouter key supplied by the user. A personal key exists only in
   memory for the current browser tab. Reloading or signing out clears it.
4. **Codex and Claude** creates, lists, and revokes scoped MCP credentials. A new
   secret is disclosed once and never stored in recoverable form.

The first Save project action creates a private project. A project owner can
create a revocable read-only link. The bearer token stays in the URL fragment,
and a recipient cannot toggle assumptions, change preferences, call models, or
save over the owner's project. A signed-in recipient can save a validated
private copy.

The interface supports keyboard dialog navigation, visible focus, reduced
motion, narrow-screen reflow, and screen-reader status announcements. The
argumentation panels and all workspace panels pass the repository's automated
WCAG A and AA browser scan. Automated checks complement, but do not replace,
manual keyboard and assistive-technology review before a public release.

## Codex and Claude Code through MCP

A verified user can create a personal MCP token through `POST /api/mcp/tokens`.
The token is displayed once, expires after 90 days by default, and can be
revoked at any time. The server stores only an HMAC-SHA-256 digest. Each token
can receive any subset of these scopes:

- `projects:read` lists examples and reads private projects.
- `projects:write` creates projects and applies version-checked edits.
- `llm:use` asks grounded questions and proposes edits using trial credit.

Set the one-time token with a hidden prompt, then export it to clients started
from that shell. This keeps the token out of shell history:

```bash
read -rsp 'ABDA-NL MCP token: ' ABDA_NL_MCP_TOKEN
printf '\n'
export ABDA_NL_MCP_TOKEN
```

Then add this entry to `~/.codex/config.toml`:

```toml
[mcp_servers.abda_nl]
url = "https://YOUR_ABDA_HOST/mcp/"
bearer_token_env_var = "ABDA_NL_MCP_TOKEN"
default_tools_approval_mode = "writes"
tool_timeout_sec = 180
```

The write approval mode lets Codex use read-only exploration directly while
asking before project mutations. The longer tool timeout accommodates funded
model calls, which can legitimately exceed Codex's default MCP timeout.

Claude Code accepts the same endpoint and expands environment variables in HTTP
headers. Keep the header in single quotes so the shell stores the variable
reference instead of the token itself. User scope makes the service available
across the user's Claude Code projects:

```bash
claude mcp add --transport http --scope user \
  --header 'Authorization: Bearer ${ABDA_NL_MCP_TOKEN}' \
  abda-nl "https://YOUR_ABDA_HOST/mcp/"
```

Run `claude mcp get abda-nl` to check the connection. Start Claude Code from a
shell where `ABDA_NL_MCP_TOKEN` is set. Revoking the token in ABDA-NL makes the
saved client configuration harmless until it is removed or given a new token.
Unset the shell value when the session is finished:

```bash
unset ABDA_NL_MCP_TOKEN
```

The current configuration fields and HTTP transport are documented by the
[Codex MCP guide](https://developers.openai.com/codex/mcp/) and the
[Claude Code MCP guide](https://code.claude.com/docs/en/mcp).

The MCP tools never accept a provider API key. Use the browser BYOK flow for a
personal Anthropic, OpenAI, Google, or OpenRouter key. That keeps the provider
secret request-scoped and out of agent transcripts and MCP configuration.

MCP writes require the project version returned by the preceding read. An LLM
proposal never changes a project. Review its operation and advisory issues,
then call `apply_project_ops` explicitly with the unchanged expected version.

## Public service operation

The public service uses the same application entrypoint in a non-root,
hash-locked container, with Azure Container Apps, private PostgreSQL, verified
email OIDC, and an explicit migration job. Operator documentation is tracked in:

- [Operator account and domain bootstrap](docs/operations/operator-service-bootstrap.md)
- [Azure deployment](docs/operations/public-deployment.md)
- [Auth0 email OTP](docs/operations/auth0-email-otp.md)
- [Funded model promotion](docs/operations/model-promotion.md)
- [Staging MCP client acceptance](docs/operations/staging-mcp-client-acceptance.md)
- [Privacy request operations](docs/operations/privacy-requests.md)
- [Public and COMMA release checklist](docs/operations/release-checklist.md)
- [Public security and operations decision](docs/decisions/0006-public-service-security-and-operations.md)

Local and Delta launch behavior remains independent of public hosting. A normal
local `abda-nl` command opens the browser automatically. Delta continues to use
`demo` plus the laptop's persistent `ssh delta-demo` tunnel.
