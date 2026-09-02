# Consolidated staging release acceptance

State: candidate deployed; public browser, release audit, and alert gates verified;
remaining operator batch pending

This checkpoint keeps every remaining release test attached to one application
artifact. Small browser observations are collected into one operator session
instead of interrupting implementation after each individual fix.

## Immutable candidate

- source commit: `3faf6ebd94c4dcb69fa36cb1aba481db15a9f973`
- source tag: `service-image-staging-consolidated-20260830-213856`
- complete CI run: `33336918328`
- image workflow run: `33337010476`
- image: `ghcr.io/liu-hy/abda-nl@sha256:78481da1f49f9b049509eafc61da1c95d55ac42e425c4ab1dbb04d700971b55d`
- provenance attestation: `https://github.com/Liu-Hy/ABDA-NL/attestations/44007417`

The image workflow repeated the complete test suite and dependency audits,
built the production container, pulled the exact digest anonymously, passed the
container smoke test, and published GitHub build provenance. The registry also
returned the same digest during an independent anonymous manifest check.

## Verified live evidence

The following checks were completed against the same immutable candidate at
`https://demo.abda-nl.org`:

- Gate 15 deployed the candidate as revision
  `abda-nl-stg-web--release-3faf6eb` without rerunning migrations or changing
  secrets.
- Gate 9 passed the external release check, 30-day Log Analytics retention,
  count-only sensitive-pattern audit, and reconciled accounting checks.
- Gate 13 revision 2 passed on 2026-09-02. Chromium and Firefox each completed
  six WCAG A and AA scans, three viewport checks, and three keyboard checks with
  no console or page errors. Reduced motion and pre-registration policy links
  also passed.
- Gate 14 revision 3 verified the exact six Azure Monitor resources and
  submitted one static-threshold test notification. The message reached the
  monitored inbox through `support@abda-nl.org`. The receipt reported no
  application change and no model-provider call.

The Alert Gate initially found two verifier-only differences in real Azure
responses: Log Analytics fields are flattened by Azure CLI, and action-group
email receivers include the read-only `status` field. Focused regressions now
cover both real response contracts. Neither repair changed the deployed
application or widened the six-resource mutation boundary.

## Ordered release sequence

The order is intentional. A later step must not invalidate evidence gathered
for an earlier application identity.

1. Deploy only the candidate image with
   `gate15-consolidated-release-image.sh`.
2. Run the read-only public browser accessibility Gate 13.
3. Run the read-only release and sanitized-log Gate 9.
4. Run the public-origin BYOK Gate 10 and the disposable-account privacy Gate
   11 during one browser and Cloud Shell session.
5. Deploy the six bounded monitoring resources with Gate 14 and confirm its one
   test message in the support inbox.
6. Complete the combined presentation-hardware checks: Safari, a screen reader,
   actual 200 percent zoom, ordinary local browser opening, and the laptop
   `ssh delta-demo` tunnel.
7. Add the prepared apex and `www` Cloudflare redirect, then verify that the
   public, authentication, and email hostnames remain separate.
8. Rehearse the compatible image rollback and automatic restoration with Gate
   10. The restoration creates the exact revision expected by the promotion
   Gate.
9. Promote the verified pilot to 100 users, $5 per user, $500 total trial
   allocation, and the independently capped OpenRouter outage route with Gate
   12.
10. Run one final external release check and retain its content-free receipt.

Steps 1, 2, 3, and 5 are complete for this candidate. Steps 4 and 6 through 10
remain.

Steps 4 through 7 are the consolidated human acceptance batch. The operator
should receive one checklist for all observations after the candidate image is
healthy. The other steps are automated or have exact, narrowly bounded cloud
confirmations.

## Short Cloud Shell helper

`deploy/azure/consolidated-operator-gate.sh` gives the operator one short local
command for each cloud phase. It downloads each underlying Gate from one exact
source commit, checks its SHA-256 before execution, and prints the mutation
boundary first. Run its `verify` phase before `deploy`.

Operator helper revision 3 is recorded at commit `5927c9a`. It pins the repaired
Alert Gate at commit `9919911` and verifies every downloaded Gate before use.

The helper intentionally has no run-all option. Deployment, disposable-account
deletion, monitoring resources, rollback, and budget promotion keep their own
confirmations and recovery points. A failed phase can therefore be rerun without
silently advancing to a later mutation.

## Mutation boundaries

- Gate 15 changes only the web image and revision suffix.
- Gate 13 and Gate 9 are read-only.
- The rollback rehearsal changes only the image twice, then restores the
  candidate automatically.
- The BYOK Gate changes no Azure setting and never receives the provider key.
- The privacy Gate changes only one disposable account after exact phase
  confirmations.
- Gate 14 creates or updates only its six reviewed Azure Monitor resources.
- Gate 12 changes only the trial user cap, total trial allocation, and public
  OpenRouter fallback switch.

No gate changes Auth0, Cloudflare DNS, application secrets, database schema, or
the paper-facing `main` branch.
