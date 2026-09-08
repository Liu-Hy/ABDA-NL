# Reviewed community examples, September 8, 2026

Status: implementation and automated acceptance in progress. No production
scenario has been submitted or published by the agent.

## Authorized scope

Add ordinary-user applications and administrator publication of preloaded
scenario snapshots. Scenario curators are the three verified email addresses
specified by the operator: hl57@illinois.edu, ludaesch@illinois.edu, and
bowers@gonzaga.edu. They receive no broader private-project or infrastructure
access. The repository defaults to an empty curator allowlist.

The feature is built on development. Stable main is unchanged. No Auth0
dashboard role changes, notification emails, model calls, or new cloud
resources are needed.

## Design and privacy

- New scenario_submissions rows store a normalized immutable snapshot of a
  saved project version, publication consent, review status, and decision
  metadata. Only an active verified owner can submit their project.
- Consent is explicit. The project name is the public title. Scenario content
  and its bundled-corpus reference are included. The private project
  description, email, conversations, keys, and private sharing data are not
  copied. Personal information deliberately written into the scenario is not
  automatically redacted, so the preview requires the author to check it.
- Users see only their submissions and can withdraw a pending request.
  Curators review snapshots, approve or decline requests, publish their own
  projects directly, and remove published examples. Review decisions are
  version-checked. Retrying a project/version submission is idempotent.
- Included filesystem examples remain unchanged. Public catalog identifiers
  use the reserved community_ prefix. The public resolver checks publication
  and account status on every request, without a stale process-local cache.
  Private copies retain their independent contents and real bundled-corpus
  provenance. HTTP analysis, AI, portable downloads, and MCP use that resolver.
- Snapshot metadata is paginated for review. Per-account limits are five
  pending and fifty total submissions. Withdrawal and removal do not share
  the submission rate limit. Status is in-app, without email notifications.
- Privacy export includes submissions. Suspension hides public snapshots.
  Account deletion removes them, while copies downloaded or saved by other
  people cannot be recalled.

## Additive schema rollout

Migration 20260908_0005 creates one table and indexes. It does not alter existing
scenario, project, identity, credential, or billing rows.

1. Publish and verify one immutable tested image.
2. Deploy that image with ABDA_COMMUNITY_CATALOG_ENABLED=false and the exact
   three-address ABDA_SCENARIO_ADMIN_EMAILS allowlist. This bridge release
   serves the previous feature set on database revision 20260817_0004.
3. Run the reviewed migration command in one execution of the existing manual
   migration job with the same saved credential references and the new image.
   No credentials are read into the agent or changed. Keep the stored job
   configuration unchanged. Verify that execution succeeded.
4. Enable ABDA_COMMUNITY_CATALOG_ENABLED=true in a new web revision. Verify
   readiness, restricted-role access, public assets, anonymous/authentication
   boundaries, unchanged budgets and routing, and the public browser shell.

The revision check permits only that exact prior schema while the feature is
explicitly disabled. It still rejects missing or unrelated migrations.
After migration, rollback should use this same image with the catalog disabled
or a newer schema-compatible image. Do not restart the September 8
scenario-library image against the new head: its older strict schema check
does not recognize this additive revision. Never downgrade or drop the new
table as a rollback, because it may contain user submissions.

## Acceptance evidence

Local verification passed: 936 Python tests, with 37 opt-in tests skipped;
all 36 Chromium browser tests; and the focused community workflow in Chromium
and Firefox. The workflow covers ordinary submissions, administrator review,
direct publication, removal, anonymous opening, downloads, mobile layout, and
accessibility. The final Chromium workflow was rerun after the dependency and
modal-lifecycle changes. PostgreSQL, Python 3.10, and WebKit acceptance run in CI.
Local WebKit is unavailable because this Delta node lacks its system libraries.

Live deployment receipts are pending. Automated browser acceptance uses
isolated local accounts and databases. It does not fabricate hosted Auth0
sessions or publish disposable content to the real public catalog.

Dependency audit also identified CVE-2026-84379, CVE-2026-84380, and
CVE-2026-84382 in the existing httpx2 2.10.0 lock. Updated only httpx2 and its
matching httpcore2 dependency to 2.12.0 in all four locks, and added a minimum
secure version constraint. Both runtime and development audits now report no
known vulnerabilities. See the [maintainer's advisory](https://github.com/pydantic/httpx2/security/advisories/GHSA-8xx6-hgc6-gc2m)
and [release notes](https://github.com/pydantic/httpx2/releases/tag/v2.12.0).
