# Decision 0006: Public service security and operations

Date: 2026-08-17
Amended: 2026-08-27

## Status

Accepted, with the image distribution amendment below.

## Context

The COMMA demo should remain useful after the conference, with verified users,
funded trial calls, private research projects, BYOK, sharing, and MCP access.
Those capabilities make a public deployment materially different from the
loopback-only paper demo. A public service needs explicit trust boundaries,
repeatable deployment, bounded financial exposure, and a recovery path.

## Decision

The public service runs in Azure Container Apps from an immutable container
image. It does not run from a Delta login node. A tag-gated GitHub Actions
workflow builds the public repository, reruns source and dependency checks,
pushes the image to the repository owner's `ghcr.io/OWNER/abda-nl` package,
smoke-tests the exact pushed digest, and creates a provenance attestation.
Azure receives the public owner-scoped package name and accepts only its
`ghcr.io/OWNER/abda-nl@sha256:...` form. It never deploys a mutable tag. Public
anonymous pull removes the need for an Azure registry, registry credential,
managed pull identity, or role assignment. Keeping the owner as an explicit
deployment parameter allows reviewed releases to move between an
operator-controlled repository and the project organization without changing
the application image contract.

Azure terminates HTTPS and forbids insecure ingress. The application binds a
generated Azure hostname first, then an operator-owned ABDA-NL hostname after
DNS and certificate validation. Cloudflare may provide registration and
authoritative DNS, but its HTTP proxy remains disabled so Azure sees the
documented connection and client-address boundary.

Persistent state uses PostgreSQL Flexible Server through private virtual
network integration. The server has no public endpoint and keeps seven days of
backups. Migrations run as a single manual Container Apps job before the web
image changes. That job retains the administrator credential, then provisions
the web login with explicit table CRUD and sequence grants. It revokes public
schema creation and database defaults. The web revision receives only the
restricted login. The migration process converts its cleartext password to a
SCRAM verifier before issuing role DDL, so PostgreSQL statements and error logs
do not receive the reusable password. A failed or unknown migration result
stops the release.
An isolated PostgreSQL 16 acceptance test applies the real migrations, starts
the application with that login, exercises every persistent feature family,
and confirms that permanent DDL, temporary tables, table alteration, and role
creation are denied.

The selected `Standard_B1ms` database currently provides 35 user connections
after Azure reservations. Each web replica is therefore limited to four pooled
connections and one overflow connection, and this Bicep deployment permits at
most three replicas. The web tier can use at most 15 database connections,
leaving capacity for migration, recovery, and platform activity. A scale-out
beyond three replicas requires a database capacity decision first. This follows
Azure's [published Flexible Server connection limits](https://learn.microsoft.com/en-us/azure/postgresql/configure-maintain/concepts-limits),
not SQLAlchemy's substantially larger per-process defaults.

Production startup enforces the following configuration:

- OIDC with an exact HTTPS public origin
- a unique signed-session secret and secure `__Host-` cookie
- a dedicated MCP token pepper that differs from the session secret
- a migrated PostgreSQL schema with automatic schema creation disabled
- a PostgreSQL web login with no administrative, ownership, object-creation,
  temporary-object, role-membership, replication, or row-security bypass
  capability
- a public-ready Foundry primary and bounded OpenRouter outage route
- authenticated funded calls and preserved registered-user BYOK
- abuse protection, trusted host validation, and a protected metrics token

The first identity release uses Auth0-hosted email OTP. ABDA-NL accepts only an
exact issuer and stable subject with the Boolean claim `email_verified: true`.
Duplicate concurrent callbacks for one stable identity converge on the same
account. It does not automatically link different identities by email. Auth0's
production email delivery uses its supported Resend integration from a
dedicated sending subdomain rather than the test sender. Cloudflare Email
Routing forwards monitored support and privacy aliases at the root domain.
Browser sign-out clears the ABDA-NL session, then uses the end-session endpoint
from trusted OIDC discovery with the exact allowed return origin. When Auth0
provides a session identifier, the application includes it as a logout hint. It
does not place the ID token in the signed browser session cookie.

## Request and data controls

Anonymous example reading remains available. Account, project, trial, share,
and MCP mutations require same-origin browser requests or scoped MCP bearer
credentials. Staging and production reject the legacy filesystem save API.

The application limits request bodies before parsing them. PostgreSQL-backed
rate buckets apply separate limits to anonymous traffic, mutations, and LLM
calls. Remote network identifiers are HMAC-derived rather than stored as raw IP
addresses. The Azure deployment reads only the rightmost `X-Forwarded-For`
address, which Container Apps documents as the value that it appends. Local and
Delta runs ignore forwarded client headers. These controls bound ordinary abuse
but are not a replacement for Azure platform denial-of-service protection or a
future WAF if traffic grows.

Private projects are always selected with the authenticated internal user ID.
Optimistic versions prevent silent overwrites. Read-only shares use revocable
bearer tokens in URL fragments, so normal HTTP access logs do not receive the
token. OIDC return paths discard queries and fragments. Login from a shared
view therefore opens in a separate tab, leaving the secret fragment in the
original tab. MCP secrets are disclosed once and stored only as keyed digests.

A BYOK secret exists only in the current browser tab and one request's provider
client. It is excluded from storage, cookies, URLs, project records, share
links, audit events, application logs, and MCP arguments. Provider endpoints and
models come from fixed allowlists, so BYOK cannot create an arbitrary network
proxy.

Assistant Markdown is untrusted provider output. Marked parses it, then the
current supported DOMPurify release restricts it to a small set of semantic
text, list, table, code, heading, and link elements. Images, forms, embedded
content, scripts, styles, SVG, and MathML are excluded. The sanitized
`DocumentFragment` is appended directly without converting it back into a
wrapper string. This avoids a second parsing context, blocks tracking images,
and limits UI redressing. Link referrers are suppressed. Real Chromium and
Firefox tests exercise script, event-handler, dangerous-URL, namespace, and
context-switch payloads against this exact rendering path. CSP remains a
separate defense.

Browser libraries are self-hosted so the demo does not depend on a conference
network CDN. Their package versions, source URLs, registry or release
integrities, final file hashes, and license copies are tracked in
`app/static/vendor/manifest.json`. DOMPurify's security policy supports only
the [latest release](https://github.com/cure53/DOMPurify/security), so updating
that asset and its exploit regressions is a release-maintenance requirement.
Marked explicitly states that its output requires a sanitizer in its
[official usage guidance](https://github.com/markedjs/marked#usage).

Uvicorn access logging is disabled. This prevents OIDC callback query values
from entering generic access logs. Application logs contain normalized event
types and request identifiers, not provider bodies or secrets. Static responses
carry CSP, HSTS in HTTPS deployments, frame denial, nosniff, a restrictive
referrer policy, and explicit cache rules.

## Financial controls

Trial activation is first-come and database-atomic. The configured policy is at
most 100 grants of $5, with a $500 total allocation cap. Every physical model
call reserves conservatively before the provider request and settles from
reported usage after it completes. A stale reservation whose provider outcome
is unknown is charged at its full conservative value instead of being released.
This rare fail-closed charge protects the user and owner hard caps from worker
loss between provider dispatch and settlement.

OpenRouter is used only for qualifying primary transport, throttling, or
provider-service failures. Authentication errors, missing deployments, invalid
requests, and model-quality validator failures do not spend emergency funds.
The emergency ledger defaults to $500, requires explicit acknowledgement above
$500, and cannot exceed $1,000 without a code and policy change.

## Observability and retention

Container logs go to Log Analytics for 30 days. The application exposes
low-cardinality HTTP counts, durations, in-flight requests, trial allocation
and spending, OpenRouter budget and reservations, LLM event counts, and database
pool capacity and occupancy through a bearer-protected Prometheus text endpoint.
Liveness excludes database state; readiness includes it, so an unhealthy
database removes replicas from traffic without causing a restart loop.

The research privacy notice and terms are linked from every main workspace.
Private project content, model prompts, and model responses are not analyzed as
research data. Application and managed container logs are retained for up to 30
days, database backups expire after seven days, and verified access, correction,
or permanent deletion requests are completed within 30 days. The notices
describe this research service and do not substitute for a general University
of Illinois policy or legal review.

Account suspension is serialized with project mutations, share creation, MCP
credential creation, and trial activation through the locked user row. Each
mutation refreshes the row instead of trusting an identity already cached by
the request session. Share resolution also requires an active project owner.
These checks prevent a request that authenticated just before suspension from
creating durable state or restoring public bearer access after suspension
commits. The deletion hold remains necessary for model requests that were
already in flight.

Rate-limit counters stop affecting requests when their fixed window ends. An
indexed deletion removes expired rows during application startup and at most
once per process each hour when later rate-limited traffic arrives. The cleanup
uses a nonblocking process lock, retries after five minutes on failure, and
cannot turn a successfully recorded request into a failed request. Multiple
replicas may each issue the bounded deletion, which is safe and avoids a
separate scheduler for this low-cost service.

## Availability tradeoff

The initial service uses a low-cost burstable PostgreSQL instance without zone
redundancy and a Container Apps environment without zone redundancy. This is a
deliberate research-demo cost choice, not an enterprise availability claim.
Container Apps keeps at least one web replica and may scale to three. The
tested local and Delta flows remain presentation fallbacks. If sustained public
usage justifies it, the next infrastructure step is a general-purpose database,
zone redundancy, alert routing, and an institutional incident owner.

The image registry is an additional external availability dependency for new
replicas and redeployments. A running replica does not need to pull its image
again. The deployment keeps at least one replica, records every accepted image
digest, and retains local and Delta presentation fallbacks. If future service
usage warrants a private Azure mirror, it can be added without changing the
application image or database design.

## Consequences

- Public deployment requires Azure, GitHub Packages, Auth0, DNS, email, funded
  Foundry, and OpenRouter operator access that cannot be embedded in this
  repository. It does not require CloudBank staff to change Azure permissions.
- Every release records the Git commit, immutable image digest, image
  attestation, migration result, public-origin checks, and live identity
  acceptance.
- Both container stages use the same reviewed Python base image pinned by OCI
  index digest. A base security refresh is an explicit source change that must
  rebuild and retest the complete image.
- Making the GitHub container package public is a deliberate one-time action.
  The package contains only material already built from the public repository,
  and no secret is included in the Docker context or image layers.
- Secret rotation is an operational event. Session rotation signs users out,
  MCP-pepper rotation revokes every existing MCP token, and an application
  database password rotation requires a coordinated migration and web deploy.
- Code rollback does not imply database downgrade. Releases keep schema changes
  backward-compatible across at least one application version.
- Public availability does not remove the loopback local or Delta workflows.
  They remain useful for development and conference contingency.
- A release must verify vendored browser asset hashes and keep DOMPurify on its
  currently supported security release.
