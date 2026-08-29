# Staging Gate 8 authenticated browser checkpoint, 2026-08-29

State: complete for the deployed shared-view candidate

This record contains no email address, OTP, project identifier, session value,
or share token.

## Live authenticated acceptance

The operator exercised the following paths at `https://demo.abda-nl.org`:

- Auth0 rejected an intentionally incorrect email OTP without creating an
  ABDA-NL session.
- A private project was created, reopened from a second authenticated tab,
  saved as version 2, and recovered after a full page reload.
- A stale version 1 tab received a version-conflict response instead of
  overwriting version 2. The accepted change remained present.
- An anonymous fresh private-browser context opened a share URL whose token was
  confined to the `#share=` fragment. The project was readable, while
  assumption, rule, chat, and editing actions were blocked.
- Revoking the share in the owner session made the anonymous shared view stop
  resolving after reload.

The only reported deviation was that clicking a disabled chat question-mark
control correctly showed the read-only notice but also opened the signed-out
Research workspace dialog. That extra dialog did not grant access, but it made
the read-only experience confusing.

## Shared-view correction

Commit `6d0fb4403c01b37d101f0d03bd9c3070b8f1e343` changed the shared-view access
result to omit a Workspace destination and guarded the caller so it opens the
dialog only when a destination exists. Browser regression coverage uses a fresh
context, clicks a shared-view chat control, checks the read-only notice, and
requires the Workspace dialog to remain hidden.

The immutable correction is:

- image:
  `ghcr.io/liu-hy/abda-nl@sha256:282a2cb13cbdabe7f60a7efaa41c5fded7b1a4efeb467cc758064c7cadf30f13`
- GitHub provenance attestation:
  `https://github.com/Liu-Hy/ABDA-NL/attestations/43876833`
- image workflow:
  `https://github.com/Liu-Hy/ABDA-NL/actions/runs/33268412561`
- deployed revision: `abda-nl-stg-web--ux-6d0fb44`

Gate 8 changed only the web image and revision suffix. Its Azure deployment and
configuration comparison succeeded, and the replacement revision became
healthy with one ready replica. The first postdeployment verifier then requested
`/static/workspace.js`, which does not exist because this application serves
the same asset at `/workspace.js`. The resulting HTTP 404 was a verifier defect,
not a service or deployment failure.

Commit `0120874e08cb72ee8cc24f14f2203fdec93c80fd` corrected both asset paths and
added regression assertions for them. CI run
`https://github.com/Liu-Hy/ABDA-NL/actions/runs/33269225172` passed all seven jobs.
The corrected live check found `/health/ready`, `/`, `/config`, both policy
pages, and both root-level JavaScript assets available, while protected metrics
still returned HTTP 401. It also found the exact two deployed shared-view guards.

The operator then repeated the affected action in a fresh private browser
window and confirmed that the read-only notice remains while the Research
workspace dialog no longer opens. This completes Gate 8.

## Boundary of this evidence

This checkpoint completes invalid-OTP, private-project persistence,
optimistic-conflict, anonymous read-only sharing, revocation, and the reported
shared-view usability defect. It does not establish live MCP client use,
public-origin BYOK calls, privacy-command operation, Log Analytics review, or a
rollback rehearsal. Those remain separate gates.
