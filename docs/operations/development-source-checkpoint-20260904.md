# Development source checkpoint, 2026-09-04

State: locally verified and pushed, not deployed

This checkpoint records the `development` branch through source commit
`04df9b9357ef1d8c900d6ce638afe0b826b063ac`. It is source-level evidence only.
The public service at `https://demo.abda-nl.org` still runs the separately
attested and audited image from commit
`51702e175bd14d4cb54075808f839d173d561324`. No Azure, Auth0, Cloudflare,
Resend, database, provider-routing, or budget setting was changed while
creating this checkpoint.

The stable paper-facing `main` branch remains at
`e4be41c72f34dd555147a2de221d84b3fd735c9f`. It is an ancestor of the
development branch and was not modified.

## Source changes since the deployed image

The development source now includes cumulative fixes and tests for:

- deterministic argumentation-engine parity and bounded computation;
- provider response validation, conservative metered accounting, disabled
  hidden retries, and deterministic provider-client closure;
- account-suspension serialization, project and trial mutation integrity,
  authenticated MCP read throttling, and safe operational logging;
- private browser state, one-time MCP credentials, and BYOK key lifetime;
- stale asynchronous model, project, archive, and workspace responses;
- recoverable browser navigation, project-save serialization, and consistent
  failed state transitions;
- mobile, keyboard, Chromium, Firefox, and WebKit accessibility behavior;
- actionable non-JSON upstream failures instead of exposing a JSON parser
  error to the user; and
- ordinary local browser launch when the server uses the IPv6 loopback
  address `::1`.

The exact local unpublished inputs `Requirements.docx` and
`camera-ready.pdf` remain outside Git and the container build context. Their
SHA-256 hashes remained unchanged during this work:

- `Requirements.docx`:
  `fb934fec9ab180586774a80f01f5d57d23693f3814eb61fa0db6f0e54b240606`
- `camera-ready.pdf`:
  `2fa5737de77fa2ac799a1d5a34a49d4f27b894421cffa22ca57e7cffecc16c07`

## Verification evidence

The following local checks passed for the checkpoint source or its final
code-changing parent:

- complete Python suite: 808 passed, 29 skipped;
- browser regression suite: 28 passed;
- `ruff check .`;
- `ruff check --select S .`;
- every `deploy/azure/*.sh` file parsed with `bash -n`;
- `python -m pip check`, with no broken requirements; and
- `git fsck --full`, with no repository corruption.

[CodeQL run 33880698538](https://github.com/Liu-Hy/ABDA-NL/actions/runs/33880698538)
passed for the checkpoint commit. The complete CI matrix also passed in
[run 33880698564](https://github.com/Liu-Hy/ABDA-NL/actions/runs/33880698564).
It covers Python 3.10 and 3.13, PostgreSQL 16, deployment artifacts,
dependency and lock audits, complete-history secret scanning, and Chromium,
Firefox, and WebKit browser acceptance.

## Deployment and release hold

Do not build, publish, or deploy a cumulative image from this checkpoint yet.
The imported GPL-3.0 argumentation engine remains incompatible with labeling
the complete public repository and image as MIT without written permission,
compatible relicensing, or a replacement. The
[source license review](source-license-review.md) defines the acceptable
resolution paths and controls this release boundary.

The remaining external and operator acceptance work is also intentionally
separate from source verification:

- complete the permanent-deletion half for the prepared disposable privacy
  account, then delete its blocked Auth0 identity;
- configure and verify the Cloudflare apex and `www` redirect;
- confirm production Resend capacity before expanding beyond the ten-user
  pilot;
- record the exact available Azure Foundry deployment inventory;
- complete the presentation hardware, Safari, screen-reader, 200 percent
  zoom, Delta tunnel, rehearsal, and recovery-tabletop checks; and
- obtain the appropriate institutional privacy and terms review.

After the source-license gate is resolved, create a new immutable image from
the then-current development commit, rerun the deployment and read-only audit,
complete the compatible rollback rehearsal, and only then consider the
100-user trial and public OpenRouter fallback promotion. The ordered operator
sequence remains in the
[final public-service operator batch](final-operator-batch.md).
