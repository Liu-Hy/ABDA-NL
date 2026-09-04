# MCP read abuse boundary, 2026-09-04

State: source implementation and local regression evidence complete, live image
deployment deferred by the source license gate

Source commit:
`1f576e71909114c1d94aabfcb167dfafc1a432e5`

## Risk closed

MCP project mutations and metered model tools already consumed database-backed
per-account rate limits. The four deterministic read tools did not. A valid
personal token could therefore request repeated argument graph builds without
sharing the browser computation ceiling. The deterministic work budget bounded
each individual build, but it did not bound request frequency.

## Implemented boundary

The following tools now share the `mcp_read` fixed-window bucket for the
authenticated account:

- `list_examples`
- `get_example`
- `list_projects`
- `get_project`

The limit uses `ABDA_ANONYMOUS_REQUESTS_PER_MINUTE`, currently 120 by default.
The counter is stored as an HMAC subject digest, not as an email address, user
identifier, or bearer token. PostgreSQL makes the counter common to all web
replicas. An exceeded limit returns a sanitized MCP tool error with a bounded
retry interval.

Each read also refreshes the durable active-account boundary before doing work.
This does not change MCP scopes, project ownership, token expiry, or token
revocation. Same-origin browser credential revocation remains deliberately
unthrottled so a user can always disable a credential.

## Verification

The regression test first demonstrated that five consecutive reads all
succeeded under a four-request ceiling. With the implementation present, the
four different read tools succeed and the fifth shared-bucket request is
rejected without affecting the token.

Local evidence for the exact source commit:

- MCP, account, acceptance-gate, and security focus: 91 passed
- complete test suite: 788 passed, 7 skipped
- Ruff: passed
- Python bytecode compilation: passed
- whitespace and conflict-marker check: passed
- all six bundled state payloads remained byte-canonical across hash seeds 1,
  2, 3, 17, 101, and a random seed
- [GitHub CI run 33868272783](https://github.com/Liu-Hy/ABDA-NL/actions/runs/33868272783):
  passed for the exact source commit
- [CodeQL run 33868272754](https://github.com/Liu-Hy/ABDA-NL/actions/runs/33868272754):
  passed for the exact source commit

No dependency, schema migration, environment value, model route, secret, or
cloud resource changes are required. A later correctly licensed cumulative
image can carry this source through the ordinary image-only deployment and
release audit. This checkpoint does not authorize publishing the currently
blocked image.
