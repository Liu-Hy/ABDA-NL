# Decision 0002: Identity, projects, sharing, and trial credit

Date: 2026-08-16

## Status

Accepted.

## Decision

ABDA-NL keeps deterministic exploration of bundled examples anonymous. Features
that consume funded LLM credit, save private work, or create MCP credentials
require a registered user with an email address verified by an OpenID Connect
provider.

One issuer and subject pair always resolves to one local account. Concurrent
first-login callbacks retry after database uniqueness races and converge on the
same user. The retry rechecks the stable identity before interpreting an email
collision. A different issuer and subject pair with the same verified address
remains blocked pending an explicit account-linking flow.

The production identity integration uses standard OIDC. Auth0 is the initial
deployment default because its hosted login, passwordless authentication, and
current free allowance fit the expected research audience. Microsoft Entra
External ID remains compatible through configuration. Local development has a
clearly isolated email login mode. Staging and production refuse to start with
that mode enabled.

PostgreSQL is the production system of record. SQLite is supported for local
development and tests. Bundled examples remain immutable. A saved project stores
the validated full scenario document, its source example, owner, timestamps, and
an optimistic version. Project deletion archives the row. An update succeeds
only when the caller supplies the version it loaded and requests at least one
metadata or scenario change. Empty updates are rejected without advancing the
version, which avoids creating artificial conflicts with another editor.

Share links are read-only and revocable. The database stores only a SHA-256 hash
of each random bearer token. The browser receives the token once in a URL
fragment, which prevents it from appearing in HTTP access logs or referrer
headers. It submits the token in a request body when resolving the share.
If a signed-out visitor starts login from a shared view, login opens in a new
tab. The original tab keeps the fragment and refreshes its account state when
the visitor returns. OIDC return paths discard queries and fragments, so the
share token cannot be copied into an ingress-visible login URL.

The free trial is claimed explicitly, not automatically at registration. The
first 100 successful claims receive 5,000,000 microdollars, equal to five US
dollars. One locked program row enforces both the 100-user cap and the
500,000,000-microdollar total liability cap. LLM requests reserve a conservative
maximum cost before dispatch, then settle the actual cost or release the
reservation after a confirmed uncharged failure. If a worker is lost after a
request might have reached the provider, the expired reservation is charged at
its full conservative amount. This fail-closed rule preserves both global hard
caps when the actual provider outcome cannot be recovered. Monetary values are
integers, never floating point.

## Rationale

Hosted OIDC provides a professional account lifecycle without making this
research project responsible for password storage, password reset, email
delivery, or phone-number verification. A provider-neutral boundary avoids
coupling project ownership to one vendor.

Explicit trial activation reduces unused grants while retaining the promised
first-come policy. Database constraints plus row locking make the budget a hard
invariant under concurrent requests. Optimistic project versions prevent two
browser tabs from silently overwriting one another.

## Consequences

- Production startup requires OIDC, HTTPS, a unique session secret, PostgreSQL,
  and an applied Alembic migration.
- Session cookies contain only a signed internal user identifier. Provider
  access tokens and user API keys never belong in browser cookies.
- The legacy filesystem save remains available for local paper-demo workflows,
  but managed staging and production deployments reject it and direct users to
  private projects.
- Share tokens cannot be recovered after creation. A lost token is replaced by
  creating a new share link.
- Raising the free-trial budget requires an explicit database and deployment
  decision. Restarting the service cannot reset or silently raise it.
