# Final public-service operator batch

State: replacement, capacity, public browser, and BYOK Gates passed; run the pilot audit

Runbook revision: `managed-boundary-20260902.3`

Before running any remaining phase, confirm that the consolidated helper block
below uses commit `fef96609bcda828e0a30c5a0a2ebcabfc1dca7fc`. Stop and refresh this
file from the personal repository's `development` branch if a saved copy uses
an older commit. The previous helper remains harmless for completed phases,
but its BYOK phase cannot distinguish a real billing error from unrelated
funded traffic during the same public acceptance window.

Gate 18 deployed the replacement as `abda-nl-stg-web--secure-b873112`, proved
that the managed filesystem-save route is rejected without mutation, and
preserved the application contract and all settings. Gate 17 then completed
123 requests at concurrency 20 with no failure or response drift. Scenario p95
was 306 ms and state p95 was 763 ms against a 6,000 ms limit. Gate 13 passed
the public Chromium and Firefox WCAG, viewport, keyboard, reduced-motion, and
policy-link checks with no console or page errors.

Acceptance evidence for this exact artifact is recorded in
[the managed-boundary release record](managed-boundary-release-acceptance-20260902.md).

This runbook collects the remaining account and browser work into one operator
session. The Azure alert deployment and its email-delivery test are already
complete. Do not rerun the alerts phase unless the monitoring configuration
changes.

The replacement release identity is:

- application source commit: `b873112040dbfe645683d1b5e7d9adb122173ed2`
- image digest: `sha256:567ec34602e1b5ab1e1a9b01864f2a67219910dc3080300bc108eb33d569856c`
- pilot revision: `abda-nl-stg-web--secure-b873112`
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
c='fef96609bcda828e0a30c5a0a2ebcabfc1dca7fc'
f='deploy/azure/consolidated-operator-gate.sh'
s='71693677973fd21388df8fe1a0003109c5b9e2dee1e154536f52c9d44875f4af'
p="$(mktemp /tmp/abda-operator.XXXXXX)"
curl -fsSL "$u/$c/$f" -o "$p"
printf '%s  %s\n' "$s" "$p" | sha256sum --check
```

The final line must report `OK`. Keep this shell open. Cloud Shell may not show
typed confirmation text after a prompt. Type each exact phrase once, press
Enter once, and wait. The confirmation was accepted if the next numbered step
appears. Do not type it again at the ordinary `haoyang [ ~ ]$` shell prompt.

Verify the complete immutable Gate bundle before running a phase:

```bash
bash "$p" verify
```

Required success ends with:

```text
result: ALL_CONSOLIDATED_OPERATOR_GATES_VERIFIED
```

## 0. Audit the replacement image

Run the read-only Azure, HTTPS, accounting, and count-only log audit:

```bash
bash "$p" audit
```

It does not change Azure or call a model. The bounded Log Analytics queries can
take a few minutes. Required success ends with:

```text
result: RELEASE_AND_OBSERVABILITY_AUDIT_VERIFIED
```

## 1. Complete the BYOK browser Gate

Status: completed on 2026-09-02 for the managed-boundary image. Do not rerun
unless the application image, BYOK handling, routing, or accounting changes.

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
browser Archive action.

## 3. Add the friendly root-domain redirect

Follow the exact dashboard values in
[`cloudflare-apex-redirect.md`](cloudflare-apex-redirect.md). This creates only
the proxied `@` and `www` placeholder records and one narrowly matched 301
redirect rule. It must not match `demo`, `login`, or `auth`.

After the two records and rule are saved, run this read-only check from the
repository on Delta:

```bash
.venv/bin/python deploy/cloudflare/gate16_public_hostname_boundary.py
```

It verifies root and `www` redirects, path and query preservation, direct demo
readiness, Auth0 discovery, and the Resend DNS boundary. It makes no change and
uses no credential. Success ends with:

```text
result: PUBLIC_HOSTNAME_AND_EMAIL_DNS_BOUNDARY_VERIFIED
```

## 4. Rehearse rollback, promote, and run the final audit

Proceed only after the BYOK, privacy, and hostname receipts above are present.
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

## 5. Conference hardware batch

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

Record only content-free receipts and observations. Never project or retain an
API key, OTP, session cookie, share token, MCP token, Auth0 secret, or private
project content.
