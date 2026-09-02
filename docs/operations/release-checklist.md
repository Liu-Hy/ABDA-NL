# Public and COMMA release checklist

Use this checklist for a public release and again for the conference build. A
release is identified by one Git commit and one immutable container image. Do
not combine evidence from different commits.

## Release identity

Record:

- Git commit:
- container image digest URI:
- image workflow run and attestation:
- evaluation suite version and SHA-256:
- model catalog version:
- Azure resource group:
- generated public origin:
- operator-owned public origin:
- Auth0 tenant and application name:
- operator and UTC date:

## Source and artifact gates

- [ ] The tracked worktree is clean and user-owned source documents are not in
      the commit.
- [ ] CI passes on Python 3.10 and 3.13.
- [ ] Ruff, migration parity, and the complete pytest suite pass.
- [ ] CI audits both runtime and development locks for known Python package
      vulnerabilities on Python 3.10 and 3.13.
- [ ] The pinned CodeQL `security-extended` workflow completes for the exact
      source commit, its SARIF clean check passes, and the development ref has
      zero open code-scanning alerts.
- [ ] The runtime and development locks regenerate without a diff on their
      native Python 3.10 and 3.13 interpreters.
- [ ] All Bicep modules and parameter files compile with the pinned Bicep CLI.
- [ ] The isolated PostgreSQL 16 CI job completes application CRUD and proves
      that the web role cannot create or alter database objects or roles.
- [ ] The production container builds and its basic-mode smoke test passes as a
      non-root user.
- [ ] The image workflow uses the full Git commit tag, never `latest`, and
      refuses to replace an existing commit image.
- [ ] The exact pushed digest passes the registry smoke test and has a valid
      GitHub provenance attestation for this repository.
- [ ] `ABDA_DEPLOY_IMAGE` contains the public owner-scoped
      `ghcr.io/OWNER/abda-nl@sha256:...` URI, not any tag.
- [ ] Anonymous pull from GHCR succeeds before Azure deployment.
- [ ] A staged-content secret scan is clean.
- [ ] `SECURITY.md` points to a working private vulnerability-reporting form,
      and repository Private Vulnerability Reporting is enabled.

## Model and budget gates

- [ ] The funded primary deployment responds on its real CloudBank route.
- [ ] The primary's most recent complete ABDA evaluation passes.
- [ ] The OpenRouter fallback's complete gate is current.
- [ ] A live OpenRouter smoke call confirms a privacy-compatible provider path.
- [ ] Model prices and route ceilings have been refreshed from primary sources.
- [ ] The trial program is capped at 100 grants, $5 each, and $500 total.
- [ ] The OpenRouter ledger has no stale reservations and remains below its
      configured hard limit.
- [ ] Any `expired_charged` reservation has an operator reconciliation note.
- [ ] One forced qualifying primary outage reaches OpenRouter and settles both
      ledgers correctly in staging.
- [ ] An authentication, deployment-name, or validator failure does not trigger
      OpenRouter spending.

## Identity and account gates

- [ ] `support@DOMAIN` and `privacy@DOMAIN` forward to a monitored operator
      inbox, and both routes pass an external delivery test.
- [ ] The public privacy and terms pages name those aliases instead of asking
      users to put account or deletion requests in a public issue.
- [ ] Auth0 uses exact callback URLs and no wildcard production origin.
- [ ] Email OTP is the only initial public identity connection.
- [ ] Resend is verified on the dedicated authentication subdomain, receiving
      and message tracking are disabled, and the Auth0 test message arrives.
- [ ] A correct OTP creates a verified account and an invalid OTP does not.
- [ ] Two concurrent callbacks for the same first login resolve to one account.
- [ ] Two accounts cannot read, modify, copy, or share one another's private
      project without an explicit share token.
- [ ] Trial activation is idempotent for one account and atomic near the final
      grant.
- [ ] Browser sign-out clears both the ABDA session and the hosted Auth0
      session, then returns to the exact allowed application origin.

## Project, BYOK, share, and MCP gates

- [ ] A private project survives reload and remains its own reasoning baseline.
- [ ] A stale browser tab receives a version conflict instead of overwriting.
- [ ] A BYOK request succeeds for each advertised provider with a disposable
      test key where practical.
- [ ] The live public-origin BYOK gate records a successful OpenRouter request,
      zero BYOK trial charge, an unchanged emergency ledger, exact
      reconciliation of any separate concurrent funded traffic, unchanged
      private project state, browser reload and sign-out clearing, and zero
      key-like log indicators.
- [ ] Reload and sign-out remove the browser's BYOK value.
- [ ] Database, logs, cookies, URLs, project exports, and share records contain
      no BYOK secret.
- [ ] A share token is confined to the URL fragment, is read-only, and stops
      working after revocation.
- [ ] MCP read and write scopes are enforced independently.
- [ ] MCP writes require the observed project version.
- [ ] An MCP proposal never applies itself.
- [ ] Revoked, expired, cross-user, and malformed MCP tokens are rejected.

## Public platform gates

- [ ] The migration job succeeds before the new web revision is deployed.
- [ ] The migration job uses the administrator login, while the web revision
      contains only the distinct restricted application login.
- [ ] Production startup confirms that the web database role cannot create
      roles, databases, schemas, temporary objects, or public-schema objects,
      owns no public objects, and has no role membership.
- [ ] Protected metrics report a database pool capacity of five per replica,
      occupancy does not exceed that value, and the B1ms deployment has no more
      than three replicas.
- [ ] The application role can complete the account, project, trial, share,
      rate-limit, usage-accounting, and MCP write paths on staging PostgreSQL.
- [ ] PostgreSQL has no public endpoint and readiness fails when it is
      unavailable.
- [ ] HTTPS redirects or rejects insecure traffic, and the certificate is valid.
- [ ] The custom-domain certificate ID is retained in the Bicep deployment
      inputs.
- [ ] Liveness, readiness, `/config`, privacy, and terms return 200 externally.
- [ ] Security headers pass the release assertions.
- [ ] `/config` exposes no credentials or private provider endpoint.
- [ ] Metrics require the bearer token and report trial and OpenRouter state.
- [ ] `abda-nl-release-check` passes from outside Azure and its sanitized JSON
      output is attached to the release record.
- [ ] Log Analytics receives sanitized application events and retains them for
      30 days.
- [ ] The exact Azure alert deployment gate creates only its reviewed action
      group, platform alerts, Application Insights component, standard web
      test, and public-readiness alert.
- [ ] The public readiness test checks HTTP 200 and TLS from three regions, and
      a test notification reaches the monitored support mailbox.
- [ ] The bounded public capacity smoke completes 40 readiness, 40 bundled
      scenario, and 40 deterministic state requests at concurrency 20 with no
      HTTP failure, response drift, or post-burst readiness loss.
- [ ] OIDC callback codes and share fragments are absent from logs.
- [ ] A previous compatible image has a documented rollback command.
- [ ] PostgreSQL point-in-time restore ownership and the seven-day window are
      understood by at least two team members.

## Accessibility and browser gates

Test the final public origin, not a static file copy.

Run the read-only automated public-origin gate after the final image is healthy:

```bash
.venv/bin/python deploy/azure/gate13_public_browser_accessibility.py
```

Retain only its content-free status receipt. It does not take screenshots,
submit credentials, call a model, or change Azure configuration.

- [ ] Automated WCAG A and AA checks pass at desktop and narrow widths.
- [ ] Chromium and Firefox complete the primary workflow.
- [ ] Safari completes the primary workflow when a macOS device is available.
- [ ] Keyboard-only use can open, traverse, submit, and close every dialog.
- [ ] Focus remains visible, dialog focus is trapped, Escape closes, and focus
      returns to the opener.
- [ ] Screen-reader names, state changes, errors, and completion notices are
      understandable.
- [ ] Reduced-motion mode avoids nonessential animation.
- [ ] At 200 percent zoom, controls remain reachable without overlapping text.
- [ ] Privacy and terms links are reachable before registration.

## Local and Delta contingency gates

- [ ] On an ordinary computer, `abda-nl` starts on loopback and opens the browser
      automatically.
- [ ] `abda-nl --no-browser` and `--basic` behave as documented.
- [ ] On Delta, `demo doctor` passes from the assigned login node.
- [ ] `.demo.json` retains `{host}` and `{port}` and the foreground command.
- [ ] `demo restart`, `demo status`, and remote `/health/ready` pass through the
      pinned-node relay.
- [ ] One ordinary laptop `ssh delta-demo` session carries the browser tunnel.
- [ ] The laptop, not only Delta, reaches `http://127.0.0.1:8765` and loads the
      correct ABDA-NL `/config` response.
- [ ] The deterministic demo remains usable without any model provider.

## Conference dry run

- [ ] Freeze a release candidate after two complete dry runs.
- [ ] Rehearse on the actual presentation laptop, browser, display resolution,
      clicker, and conference network when available.
- [ ] Keep the public origin, Delta tunnel, and a local deterministic instance
      as three distinct recovery paths.
- [ ] Preload one verified presentation account with enough funded balance.
- [ ] Do not display `.env`, provider dashboards, email inbox contents, API keys,
      share tokens, MCP tokens, or Azure deployment output on the projected
      screen.
- [ ] Keep a local copy of the paper examples and a short narrated fallback for
      each external call.
- [ ] Assign one presenter and one operator. The operator watches health, model
      route, latency, and budget without changing configuration during the talk.
- [ ] Record the final successful checks, known limitations, and rollback image.

## Stop conditions

Do not open public registration or begin the live demonstration when any of
these conditions holds:

- database migrations or readiness are uncertain
- trial or OpenRouter reservations cannot be reconciled
- identity callbacks accept an unverified or mismatched issuer
- a secret appears in logs, browser storage, URLs, or a committed file
- the funded primary and fallback are both unavailable
- the browser cannot complete the deterministic core workflow
- disk, inode, database storage, or provider quota is near a hard limit

Use the deterministic local or Delta workflow when model service is the only
failed dependency. Pause public mutations when identity, persistence,
authorization, or accounting integrity is uncertain.
