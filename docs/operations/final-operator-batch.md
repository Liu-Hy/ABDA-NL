# Final public-service operator batch

State: hardened image live; privacy preparation complete; permanent deletion next

Runbook revision: `rate-limit-retention-20260904.4`

## Resume here after the completed privacy preparation

The next live operator action is the permanent-deletion half of Section 2.
The 15-minute hold has already elapsed. Keep the disposable Auth0 user blocked,
load and verify the `p` helper exactly as documented below, then run only the
privacy phase. Enter `RUN_ABDA_PRIVACY_ACCEPTANCE`, followed by
`DELETE_PRIVACY_ACCEPTANCE`. Do not recreate the disposable account, project,
share, or MCP token, and do not repeat the preparation phase.

Continue only after the Gate returns
`LIVE_PRIVACY_EXPORT_AND_DELETION_VERIFIED`:

1. Delete that same blocked disposable identity in Auth0.
2. Move to Section 3 and load the separate `q` helper.
3. Run its verify, deploy, and audit phases in that order.
4. Complete the Cloudflare redirect and its hostname check in Section 4.
5. Confirm Resend production sending capacity, then run rollback, promotion,
   and the final audit in Section 5.

The hardened-image deployment, its audit, BYOK, MCP, capacity, Chromium, and
Firefox checks are already complete. Do not rerun them unless the relevant
application code or configuration changes. The remaining presentation-hardware
checks and recovery tabletop are batched in Section 6.

Before running any remaining phase, confirm that the consolidated helper block
below uses commit `9fb7386c271355f5adb07b4e8457368d1db44ad8`. Stop and refresh this
file from the personal repository's `development` branch if a saved copy uses
an older commit.

The managed-boundary image already passed live OpenRouter BYOK acceptance. The
current hardened service passed fresh public Chromium and Firefox accessibility
and bounded capacity checks on 2026-09-04 CDT. The subsequent
runtime changes remove private or model-derived identifiers from operational
logs, reduce evaluator route-list output, and prevent unexpected exception
messages or tracebacks from entering logs. Safe diagnostics retain only the
exception class and internal code location. These changes do not alter
authentication, BYOK key handling, projects, sharing, MCP, routing, budgets,
database schema, or browser code. CodeQL reports zero findings for the new
source, and the image workflow rebuilt, smoke-tested, and attested its exact
digest.

This runbook collects the remaining cloud and account work into one operator
batch. The hardened-image deployment and live audit, Azure alert deployment,
alert-email delivery, BYOK browser Gate, bounded capacity smoke, and automated
Chromium and Firefox accessibility Gate are already complete. The last two
were rerun against the unchanged hardened service after privacy preparation.
Do not rerun them unless their corresponding code or configuration changes.

The hardened release identity is:

- application source commit: `51702e175bd14d4cb54075808f839d173d561324`
- source tag: `service-image-staging-safe-exceptions-20260902-191532`
- image digest: `sha256:a0b3ba24aff06ecf461f86547131d86451c541e306a7ecfc278f280fcef5c0bc`
- provenance attestation: `https://github.com/Liu-Hy/ABDA-NL/attestations/44802693`
- target pilot revision: `abda-nl-stg-web--harden-51702e1`
- public origin: `https://demo.abda-nl.org`

The queued post-privacy maintenance identity is:

- application source commit: `e008067e3dc9c96862cf4f75228bdf0250848665`
- source tag: `service-image-staging-rate-limit-retention-notice-20260904-063308`
- image digest: `sha256:b20cfe100f94d22e5734badaf5ec4e52e3445b72fcdc1879339f7b905109eb29`
- provenance attestation: `https://github.com/Liu-Hy/ABDA-NL/attestations/45178541`
- target pilot revision: `abda-nl-stg-web--retain-e008067`
- public origin: `https://demo.abda-nl.org`

Do not deploy the queued image before the disposable-account privacy deletion
receipt. The current privacy Gate is intentionally bound to the hardened live
image. The post-privacy helper has no privacy phase, and its deployment
confirmation requires the operator to attest that deletion succeeded.

Before running the final promotion, confirm production email capacity. The
current Resend Free limit of 100 messages per day has no headroom for 100 new
OTP users plus retries and returning logins. The recommended public-launch
choice is Resend Transactional Pro, currently $20 per month with no daily
limit. Keep the existing verified domain and API key integration. If the
service remains on Free, stop after the ten-user pilot and stagger invitations
instead of running the 100-user promotion.

## Prepare one Cloud Shell session

A new or existing Azure Cloud Shell session is acceptable. Paste this complete
block once. It downloads a small helper from an immutable commit and verifies
its checksum before saving its temporary path in `p`.

```bash
u='https://raw.githubusercontent.com/Liu-Hy/ABDA-NL'
c='9fb7386c271355f5adb07b4e8457368d1db44ad8'
f='deploy/azure/consolidated-operator-gate.sh'
s='dc75d1295906cdeae9d10dcc4494441e3d12247481fbc8d725a1746ebb4253b6'
p="$(mktemp /tmp/abda-operator.XXXXXX)"
curl -fsSL "$u/$c/$f" -o "$p"
printf '%s  %s\n' "$s" "$p" | sha256sum --check
```

The final line must report `OK`. Keep this shell open. Cloud Shell may not show
typed confirmation text after a prompt. Type each exact phrase once, press
Enter once, and wait. The confirmation was accepted if the next numbered step
appears. Do not type it again at the ordinary `haoyang [ ~ ]$` shell prompt.
If the Cloud Shell session closes, no release state is lost. Open a new session
and repeat only the preparation block above to recreate its temporary `p`
value, then resume the required phase.

Verify the complete immutable Gate bundle before running a phase:

```bash
bash "$p" verify
```

Required success ends with:

```text
result: ALL_CONSOLIDATED_OPERATOR_GATES_VERIFIED
```

## 0. Deploy and audit the hardened image

Status: completed on 2026-09-04 UTC. The deployed source is `51702e1`, the
image digest is `sha256:a0b3ba24aff06ecf461f86547131d86451c541e306a7ecfc278f280fcef5c0bc`,
and the healthy Azure revision is `abda-nl-stg-web--harden-51702e1`. The
deployment returned `SOURCE_SECURITY_IMAGE_DEPLOYED_AUDIT_REQUIRED`, and the
immediate read-only audit returned
`RELEASE_AND_OBSERVABILITY_AUDIT_VERIFIED`. Do not rerun either command unless
the image or relevant configuration changes. The commands remain below as a
recovery and audit reference.

Deploy the exact attested image:

```bash
bash "$p" deploy
```

At the confirmation prompt, type `DEPLOY_ABDA_SOURCE_SECURITY_IMAGE` once and
press Enter. The Gate changes only the web image and revision suffix. It proves
that application settings and secret references are unchanged, does not rerun
a migration, and completes public endpoint checks before returning:

```text
result: SOURCE_SECURITY_IMAGE_DEPLOYED_AUDIT_REQUIRED
```

Then run the read-only Azure, HTTPS, accounting, and count-only log audit:

```bash
bash "$p" audit
```

It does not change Azure or call a model. It creates one readiness request,
then waits up to three minutes for current-revision request logs before checking
the 30-day workspace and sensitive-pattern counts. Required success ends with:

```text
result: RELEASE_AND_OBSERVABILITY_AUDIT_VERIFIED
```

## 1. Complete the BYOK browser Gate

Status: completed on 2026-09-02. Do not rerun for the hardened image. The
intervening runtime diff changes logging and evaluator output only, while the
new deployment Gate proves that the complete application contract remains
unchanged.

Use the normal browser account that has already activated the funded pilot.
Start the Gate:

```bash
bash "$p" byok
```

When step 5 asks for the browser action:

1. Open `https://demo.abda-nl.org` and sign in.
2. Open **Workspace**, then **AI access**.
3. Select **Bring your own API key**, provider **OpenRouter**, and model
   **Gemini 3.7 Flash**.
4. Paste the current OpenRouter key only into **Provider API key** in the
   browser. Do not paste it into Cloud Shell, chat, a document, or a project.
5. Select **Use this access setting**. Ask one short question and wait for a
   useful answer labeled as using the own key.
6. Return to Cloud Shell and enter `BYOK_OPENROUTER_CALL_CONFIRMED`.
7. When instructed, reload the webpage, open **Workspace**, then **AI access**,
   and confirm that **Provider API key** is empty. Enter
   `BYOK_RELOAD_CLEAR_CONFIRMED`.
8. Re-enter and apply the key without asking another question. Sign out, sign
   in again, and confirm that the field is empty. Enter
   `BYOK_SIGNOUT_CLEAR_CONFIRMED`.

Success ends with:

```text
result: LIVE_BYOK_PRIVACY_AND_ACCOUNTING_ACCEPTANCE_VERIFIED
```

The Gate confirms that the BYOK request did not charge the trial or the
owner-funded emergency ledger, and that no key-like value appeared in the
count-only log audit. If unrelated funded traffic occurs during the same
window, the Gate accepts it only when separate funded-route result logs account
for the exact trial-spend change.

If the browser answer succeeded but the Gate reports that the call was not
confirmed, do not make another model request. Rerun `bash "$p" byok` in the
same Cloud Shell session. The Gate will report `resume_phase: awaiting_call`
from its protected three-hour baseline. Enter
`BYOK_OPENROUTER_CALL_CONFIRMED`, then complete only the reload and sign-out
clearing checks. An empty or mistyped confirmation cannot spend funds or
change Azure, and it does not discard the saved baseline.

## 2. Prepare and delete one disposable privacy account

Status: preparation completed on 2026-09-04 CDT through job execution
`abda-nl-stg-migrate-7tlx9gq`. The execution succeeded, the saved job and web
application configurations remained unchanged, and the receipt reported no
terminal email input or model-provider call. Keep the disposable Auth0 user
blocked and continue with the deletion phase only after the 15-minute hold.

Use a fresh private browser window and a separate reachable email address or
inbox-supported plus alias. Auth0 must treat it as a new user. Do not use the
normal funded account.

Prepare the disposable state:

1. Sign in with the disposable address. Do not activate the trial and do not
   call a model.
2. Keep any bundled example open and select **Save project**.
3. Name it `Privacy acceptance disposable`, then select
   **Create private project**.
4. Open **Workspace**, then **Projects**, and select **Create share link** for
   the open project. Do not copy the one-time link.
5. Open **Codex and Claude**. Name the credential
   `Privacy acceptance disposable`, choose 30 days, keep only
   **Read examples and private projects**, and select **Create token**. Do not
   reveal or copy the token.
6. Sign out of ABDA-NL.
7. In Auth0, open **User Management**, then **Users**, select this exact
   disposable user, and choose **Block User** from its details or actions.
   Confirm the block. Keep the user blocked through both Gate runs.

For a new acceptance account, run the first privacy phase:

```bash
bash "$p" privacy
```

Enter `RUN_ABDA_PRIVACY_ACCEPTANCE` at the wrapper confirmation, then enter
`PREPARE_PRIVACY_ACCEPTANCE` at the phase prompt. The gate locates exactly one
account by the disposable project and credential names, so it does not ask for
or store the email address in Cloud Shell or the Azure execution template. It
starts one short execution-only override of the existing manual migration job.
The override uses the restricted application database password, does not run
the migration command, and does not change the job's saved configuration.
Success ends with:

```text
result: PRIVACY_ACCEPTANCE_PREPARED_WAIT_15_MINUTES
```

Keep the Auth0 user blocked and wait at least 15 minutes. The Cloudflare work
in Section 4 can be completed during this wait. Then run the same command
again. Enter `RUN_ABDA_PRIVACY_ACCEPTANCE`, then
`DELETE_PRIVACY_ACCEPTANCE`. The required second receipt is:

```text
result: LIVE_PRIVACY_EXPORT_AND_DELETION_VERIFIED
```

Before it creates a deletion execution, the current Gate finds the exact
successful preparation execution and measures 900 seconds from that
execution's end time. If the hold has not elapsed, it reports the remaining
seconds and exits without creating a failed deletion execution. Wait for the
reported interval and rerun the same command.

Only after this second receipt, return to the same Auth0 user and select
**Delete User** from the details page or actions menu. Confirm deletion. The
private project is removed by the privacy Gate, so there is no separate
browser Archive action. The shareable Gate receipts omit both the email address
and its derived account fingerprint.

If an older privacy gate failed with `Handshake status 404 Not Found` before
the email prompt, it did not reach the runner and did not change application
data. Keep the existing disposable state and blocked Auth0 user. Load the
current helper above and run the first phase. Do not recreate the project,
share, token, or account.

## 3. Deploy and audit the retention maintenance image

Proceed only after the privacy Gate returned
`LIVE_PRIVACY_EXPORT_AND_DELETION_VERIFIED` and the disposable Auth0 identity
was deleted. A new or existing Cloud Shell session is acceptable. Paste this
complete block once:

```bash
u='https://raw.githubusercontent.com/Liu-Hy/ABDA-NL'
c2='7b59ff28a696d598618103e15ab38bf26798015e'
f2='deploy/azure/post-privacy-operator-gate.sh'
s2='4eb447b805654c9c2e17ea5b96a589ba95eba3a99e53b26b893b4412fae999f7'
q="$(mktemp /tmp/abda-post-privacy.XXXXXX)"
curl -fsSL "$u/$c2/$f2" -o "$q"
printf '%s  %s\n' "$s2" "$q" | sha256sum --check
```

The final line must report `OK`. Keep the shell open, then verify every phase
wrapper before running one:

```bash
bash "$q" verify
```

Required success ends with:

```text
result: ALL_POST_PRIVACY_OPERATOR_GATES_VERIFIED
```

Deploy the exact attested maintenance image:

```bash
bash "$q" deploy
```

At its prompt, type
`PRIVACY_DELETION_VERIFIED_DEPLOY_ABDA_RETENTION_IMAGE` once and press Enter.
Use that phrase only after both privacy deletion steps above succeeded. The
Gate changes only the web image and revision suffix. It verifies the new
retention disclosure and preserves the existing managed-service and
shared-view boundaries. Required success ends with:

```text
result: RATE_LIMIT_RETENTION_IMAGE_DEPLOYED_AUDIT_REQUIRED
```

Then run the read-only audit:

```bash
bash "$q" audit
```

Required success ends with:

```text
result: RATE_LIMIT_RETENTION_RELEASE_AND_OBSERVABILITY_AUDIT_VERIFIED
```

Do not repeat BYOK, MCP, or a funded model call for this maintenance image.
The image-only Gate proves those application contracts unchanged. After the
deployment receipt is available, Codex can run the automated public browser
and bounded deterministic capacity checks from Delta without another manual
browser action.

If Cloud Shell closes, repeat only the block that creates `q`, run
`bash "$q" verify`, then resume the required phase. Every mutating Gate detects
its exact completed or pending revision.

## 4. Add the friendly root-domain redirect

Follow the exact dashboard values in
[`cloudflare-apex-redirect.md`](cloudflare-apex-redirect.md). This creates only
the proxied `@` and `www` placeholder records and one narrowly matched 301
redirect rule. It must not match `demo`, `login`, or `auth`.

After the two records and rule are saved, return to the same Cloud Shell and
run this read-only check:

```bash
bash "$q" hostname
```

It verifies root and `www` redirects, path and query preservation, direct demo
readiness, Auth0 discovery, and the Resend DNS boundary. It makes no change and
uses no credential. Success ends with:

```text
result: PUBLIC_HOSTNAME_AND_EMAIL_DNS_BOUNDARY_VERIFIED
```

## 5. Rehearse rollback, promote, and run the final audit

Proceed only after the retention-image deployment and audit, prior BYOK and
MCP acceptance, privacy deletion, and hostname receipts above are present.
Before starting this section, confirm the transactional-email plan that backs
the Auth0 Resend provider:

1. Sign in to the Resend account that owns `auth.abda-nl.org`.
2. Open **Settings**, then **Billing**. The Billing page is the documented
   place to view or change the subscription.
3. For a 100-user public launch, use **Transactional Pro**, 50,000 emails per
   month for $20 per month. It has no daily email limit. Do not select a
   marketing plan, Scale, a dedicated IP, or an additional-domain add-on for
   ABDA-NL. Keep **Transactional Overages** disabled because they are
   unnecessary for this launch size.
4. Confirm that Billing shows the paid transactional plan and that overages are
   disabled. Do not copy payment details into an operator receipt. The existing
   domain, API key, Auth0 provider configuration, and verified delivery evidence
   remain unchanged.

The [Resend pricing page](https://resend.com/pricing?product=transactional)
currently lists Free at 100 emails per day and Transactional Pro at $20 per
month with no daily limit. The
[Resend billing guide](https://resend.com/docs/dashboard/settings/billing)
documents the **Settings**, **Billing** path, and the
[Resend overage announcement](https://resend.com/changelog/pay-as-you-go-pricing)
documents its separate opt-in toggle. If the account remains on Free, do not
run the 100-user promotion. Keep the ten-user pilot and stagger access until
sender capacity is increased.

The operator has accepted the current OpenRouter key for the initial public
fallback. The application enforces its independent $500 ledger cap. Rotating to
a dedicated provider key with a matching lifetime limit remains recommended
defense in depth after the deadline, but is not a prerequisite for this Gate.

Run these commands in order:

```bash
bash "$q" rollback
bash "$q" promote
bash "$q" final-audit
```

The rollback Gate changes only the web image, accepts the compatible older
image, and restores the exact candidate automatically. The promotion Gate
changes exactly three values: the trial user limit from 10 to 100, the total
trial allocation from $50 to $500, and the public OpenRouter outage switch from
disabled to enabled. It preserves the independent $500 OpenRouter hard cap.
Each mutating Gate displays its exact confirmation phrase before making a
change.

At the rollback prompt, type `RUN_ABDA_ROLLBACK_REHEARSAL` once. At the
promotion prompt, type `PROMOTE_ABDA_PUBLIC_BUDGETS` once, but only after the
transactional-email capacity check above is complete. The final audit has no
mutation confirmation because it is read-only.

Required final receipts are:

```text
result: COMPATIBLE_RETENTION_IMAGE_ROLLBACK_AND_RESTORE_VERIFIED
result: PUBLIC_BUDGETS_AND_OUTAGE_FALLBACK_PROMOTED
result: FINAL_PUBLIC_RELEASE_AND_OBSERVABILITY_AUDIT_VERIFIED
```

The final audit is read-only. It verifies the promoted revision, public caps,
idle reservations, protected metrics, HTTPS behavior, 30-day log retention,
and zero sensitive-pattern log counts.

## 6. Conference and team readiness batch

Use the
[`COMMA 2026 demonstration playbook`](comma-2026-demo-playbook.md) for the
rehearsed narrative, role split, preflight, and recovery ladder.

These checks require the actual presentation hardware and can be performed
closer to COMMA without blocking the public-service accounting promotion:

1. In Safari on macOS, complete example selection, Explain, Workspace open and
   close, verified-email sign-in, and sign-out.
2. At actual 200 percent browser zoom, confirm that all four reasoning panels,
   modal controls, status messages, and close buttons remain reachable.
3. With VoiceOver or another screen reader, confirm that the page title,
   buttons, dialog names, selected tabs, errors, and completion notices are
   understandable.
4. On an ordinary computer checkout, run `python3 -m venv .venv`,
   `make install`, then `.venv/bin/abda-nl`. Confirm that the default browser
   opens the loopback demo automatically. Stop it with Ctrl+C.
5. From the presentation laptop, keep one ordinary `ssh delta-demo` session
   open. On Delta run `demo doctor` and `demo status`, then open
   `http://127.0.0.1:8765` on the laptop and confirm the ABDA-NL page and
   `/config` response.
6. Complete two narrated dry runs using the public site, then rehearse the
   deterministic local or Delta fallback without a model provider.
7. With Haoyang and one technical reviewer, complete the content-free tabletop
   in the [PostgreSQL recovery runbook](database-recovery.md). Do not create a
   restored server for this review.

Record only content-free receipts and observations. Never project or retain an
API key, OTP, session cookie, share token, MCP token, Auth0 secret, or private
project content.
