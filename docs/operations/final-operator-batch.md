# Final public-service operator batch

State: hardened image and remaining manual release Gates prepared

Runbook revision: `source-security-20260902.2`

Before running any remaining phase, confirm that the consolidated helper block
below uses commit `ec32553dd88f2d27bf349fc58b3397e68f81be00`. Stop and refresh this
file from the personal repository's `development` branch if a saved copy uses
an older commit.

The managed-boundary image already passed capacity, public Chromium and
Firefox accessibility, and live OpenRouter BYOK acceptance. The subsequent
runtime changes remove private or model-derived identifiers from operational
logs and reduce evaluator route-list output. They do not change authentication,
BYOK key handling, projects, sharing, MCP, routing, budgets, database schema,
or browser code. CodeQL reports zero findings for the new source, and the
image workflow rebuilt, smoke-tested, and attested its exact digest.

This runbook collects the remaining cloud and account work into one operator
batch. The Azure alert deployment, alert-email delivery, BYOK browser Gate,
bounded capacity smoke, and automated Chromium and Firefox accessibility Gate
are already complete. Do not rerun them unless their corresponding code or
configuration changes.

The hardened release identity is:

- application source commit: `c173dd5983ba209b17c585c0c82aeb33c2e49028`
- source tag: `service-image-staging-source-security-20260902-182221`
- image digest: `sha256:ecf7531064fe6f86d3d647e9f0239bfbe5e082d71c5fcdd5e7e7fb91e9b32a64`
- provenance attestation: `https://github.com/Liu-Hy/ABDA-NL/attestations/44790406`
- target pilot revision: `abda-nl-stg-web--harden-c173dd5`
- public origin: `https://demo.abda-nl.org`

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
c='ec32553dd88f2d27bf349fc58b3397e68f81be00'
f='deploy/azure/consolidated-operator-gate.sh'
s='cf70a0ad04cdcb09f86214dd48c299427702206d45ca72b621adbf4ba8b1b949'
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

Status: completed on 2026-09-02. Do not rerun for the source-security image.
The intervening runtime diff changes logging and evaluator output only, while
the new deployment Gate proves that the complete application contract remains
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

Run the first privacy phase:

```bash
bash "$p" privacy
```

Enter `RUN_ABDA_PRIVACY_ACCEPTANCE` at the wrapper confirmation. Enter the
disposable email only at the hidden prompt. Inside the privacy runner, enter
`PREPARE_PRIVACY_ACCEPTANCE`. Success ends with:

```text
result: PRIVACY_ACCEPTANCE_PREPARED_WAIT_15_MINUTES
```

Keep the Auth0 user blocked and wait at least 15 minutes. The Cloudflare work
in the next section can be completed during this wait. Then run the same
command again. Enter `RUN_ABDA_PRIVACY_ACCEPTANCE`, the same hidden email, and
finally `DELETE_PRIVACY_ACCEPTANCE`. The required second receipt is:

```text
result: LIVE_PRIVACY_EXPORT_AND_DELETION_VERIFIED
```

Only after this second receipt, return to the same Auth0 user and select
**Delete User** from the details page or actions menu. Confirm deletion. The
private project is removed by the privacy Gate, so there is no separate
browser Archive action. The shareable Gate receipts omit both the email address
and its derived account fingerprint.

## 3. Add the friendly root-domain redirect

Follow the exact dashboard values in
[`cloudflare-apex-redirect.md`](cloudflare-apex-redirect.md). This creates only
the proxied `@` and `www` placeholder records and one narrowly matched 301
redirect rule. It must not match `demo`, `login`, or `auth`.

After the two records and rule are saved, return to the same Cloud Shell and
run this read-only check:

```bash
bash "$p" hostname
```

It verifies root and `www` redirects, path and query preservation, direct demo
readiness, Auth0 discovery, and the Resend DNS boundary. It makes no change and
uses no credential. Success ends with:

```text
result: PUBLIC_HOSTNAME_AND_EMAIL_DNS_BOUNDARY_VERIFIED
```

## 4. Rehearse rollback, promote, and run the final audit

Proceed only after the hardened deployment and audit, BYOK, privacy, and
hostname receipts above are present.
Before starting this section, confirm the transactional-email plan that backs
the Auth0 Resend provider:

1. Sign in to the Resend account that owns `auth.abda-nl.org`.
2. Open **Settings**, then **Billing**. The Billing page is the documented
   place to view or change the subscription.
3. For a 100-user public launch, use **Transactional Pro**, 50,000 emails per
   month for $20 per month. It has no daily email limit. Do not select a
   marketing plan, Scale, a dedicated IP, or an additional-domain add-on for
   ABDA-NL. Transactional overages are also unnecessary for this launch size.
4. Confirm that Billing shows the paid transactional plan. Do not copy payment
   details into an operator receipt. The existing domain, API key, Auth0
   provider configuration, and verified delivery evidence remain unchanged.

The [Resend pricing page](https://resend.com/pricing?product=transactional)
currently lists Free at 100 emails per day and Transactional Pro at $20 per
month with no daily limit. The
[Resend billing guide](https://resend.com/docs/dashboard/settings/billing)
documents the **Settings**, **Billing** path. If the account remains on Free,
do not run the 100-user promotion. Keep the ten-user pilot and stagger access
until sender capacity is increased.

Run these commands in order:

```bash
bash "$p" rollback
bash "$p" promote
bash "$p" final-audit
```

The rollback Gate changes only the web image, accepts the compatible older
image, and restores the exact candidate automatically. The promotion Gate
changes exactly three values: the trial user limit from 10 to 100, the total
trial allocation from $50 to $500, and the public OpenRouter outage switch from
disabled to enabled. It preserves the independent $500 OpenRouter hard cap.
Each mutating Gate displays its exact confirmation phrase before making a
change.

Required final receipts are:

```text
result: COMPATIBLE_IMAGE_ROLLBACK_AND_RESTORE_VERIFIED
result: PUBLIC_BUDGETS_AND_OUTAGE_FALLBACK_PROMOTED
result: FINAL_PUBLIC_RELEASE_AND_OBSERVABILITY_AUDIT_VERIFIED
```

The final audit is read-only. It verifies the promoted revision, public caps,
idle reservations, protected metrics, HTTPS behavior, 30-day log retention,
and zero sensitive-pattern log counts.

## 5. Conference and team readiness batch

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
