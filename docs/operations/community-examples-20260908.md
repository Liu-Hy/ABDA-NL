# Reviewed community examples, September 8, 2026

This records the September 8 release. The owner's later instruction makes all
five named credit identities scenario administrators and adds normal user view;
the [current requirements](../demo-revision-contract.md) supersede the role
defaults below.

Status: deployed and enabled at https://demo.abda-nl.org. Automated source,
database, browser, and live release acceptance passed. No production scenario
was submitted or published by the agent.

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

Both source CI runs [34282280517](https://github.com/Liu-Hy/ABDA-NL/actions/runs/34282280517)
and [34282276965](https://github.com/Liu-Hy/ABDA-NL/actions/runs/34282276965)
passed all eight jobs, including PostgreSQL and all three browser engines.
CodeQL [34282280747](https://github.com/Liu-Hy/ABDA-NL/actions/runs/34282280747)
also passed. Automated authenticated browser acceptance uses isolated accounts
and databases. It does not fabricate hosted Auth0 sessions or publish
disposable content to the real public catalog.

Dependency audit also identified CVE-2026-84379, CVE-2026-84380, and
CVE-2026-84382 in the existing httpx2 2.10.0 lock. Updated only httpx2 and its
matching httpcore2 dependency to 2.12.0 in all four locks, and added a minimum
secure version constraint. Both runtime and development audits now report no
known vulnerabilities. See the [maintainer's advisory](https://github.com/pydantic/httpx2/security/advisories/GHSA-8xx6-hgc6-gc2m)
and [release notes](https://github.com/pydantic/httpx2/releases/tag/v2.12.0).

## Published artifact

- Source: `a72872fd215dea34954d2f50ba52115620f8008b`
- Tag: `service-image-community-20260908-a72872f`
- Image: `ghcr.io/liu-hy/abda-nl@sha256:ebb6be7dafd77bd503176be8c25c017ca6e4993e5b2079c74ff5c3e4417fb49a`
- Image config: `sha256:262170dc28cfddd402306e6c9e1b55a0b5fce5e3e945a687587acad780518b3b`

The [publisher run](https://github.com/Liu-Hy/ABDA-NL/actions/runs/34282277002)
passed tests, dependency audits, exact-image smoke, container vulnerability
and secret scanning, SBOM generation, and provenance attestation. Anonymous
registry reads verified the manifest and config hashes, linux/amd64 platform,
source revision, repository, and GPL-3.0-only label. Independent
`gh attestation verify` accepted the expected GitHub-hosted publisher workflow
with self-hosted runners denied.

## Live rollout receipt

The agent used the operator-authorized dedicated Azure session. No additional
Cloud Shell handoff or Auth0 dashboard change was needed.

- Existing resource group: `abda-nl-staging`
- Application: `abda-nl-stg-web`
- Prior revision: `abda-nl-stg-web--scenarios-54a0885`
- Healthy disabled-catalog bridge: `abda-nl-stg-web--curation-pre-a72872f`
- Migration execution: `abda-nl-stg-migrate-aa4ig7b`
- Migration state: `Succeeded`, September 8, 2026, 21:52:37 to 21:53:04 UTC
- Current enabled revision: `abda-nl-stg-web--curation-a72872f`
- Current revision: active, Provisioned, Healthy, with one replica
- Latest revision and latest ready revision both match the current revision
- Database head: `20260908_0005`; the enabled image's strict startup check passed

Only the web image, revision suffix, and the two reviewed catalog settings
changed. Comparison of the remaining desired-state configuration preserved
ingress, certificates, identity, secret references, probes, scaling, resource
limits, and provider and budget settings. The existing manual migration job's
saved template and configuration are unchanged. Its one execution override
used the new image and the same saved administrator/application credential
references. Future migration runs must likewise select a schema-compatible
image, not blindly start the historical saved job image.

PostgreSQL remained Ready with public access Disabled and seven-day backups.
Sampled HTTPS readiness requests succeeded throughout both web transitions.
This is sampled evidence, not a claim of continuous zero-downtime monitoring.

## Live acceptance

- Catalog enabled; anonymous sessions have no administrator capability.
- Anonymous submission and review-list reads return 401. Cross-origin
  submission returns 403. An unknown community snapshot returns 404.
- Seven served assets match the tested source bytes, including curation.js.
- All six included scenarios retain exactly the same canonical state hashes
  as before the deployment. The initial community catalog is empty.
- After activation, public Chromium and Firefox each passed six accessibility
  scans, three viewport checks, and three keyboard checks with no console or
  page errors. Reduced-motion and policy-page checks passed.
- The full live release checker passed HTTPS, HTTP redirect, readiness,
  liveness, security headers, policy pages, configuration exposure, protected
  metrics, database pooling, and hard-cap accounting checks.
- Trial settings remain 100 users, a $5 grant, and a $500 total cap. Emergency
  OpenRouter routing remains enabled with its existing $500 cap. BYOK and
  the CloudBank-funded default profile remain unchanged.
- At 21:56:03 UTC, one trial was active. Settled trial spending was 465849
  microdollars and emergency spending was 149 microdollars. Uncertain charged
  reservations remained zero. These deployment checks made no model calls;
  ordinary user traffic may continue during the rollout.

The three configured verified emails become scenario curators on their normal
sign-in. The role does not create accounts, consume trial slots, or grant
access to another user's private projects. No real-user session was forged for
acceptance. Stable main remains unchanged.
