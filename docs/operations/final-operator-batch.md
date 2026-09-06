# Final public-service operator batch

State: GPL cumulative image live; pilot audit, funded smoke, public browser,
and bounded capacity checks passed; privacy recovery and Auth0 cleanup complete;
friendly redirects verified; production email capacity and public promotion pending

Runbook revision: `gpl-pilot-and-hostname-verified-20260905`

This runbook covers the remaining live service operations. The maintainer has
chosen GPL-3.0 for the combined development distribution. The preserved
notices and artifact checks are recorded in
[the source license review](source-license-review.md).

The previously queued `084817f` image is superseded. Section 3 now pins the
[tested, attested GPL image](gpl-distribution-checkpoint-20260905.md) and its
verified helper. The privacy database-destination review is complete, and the
operator confirmed deletion of the exact disposable Auth0 identity. The
[GPL live checkpoint](gpl-live-checkpoint-20260905.md) records the completed
rollout audit and model smoke. Section 4's hostname check has also passed.
Continue at Section 5 after its email-capacity prerequisite, not the completed
Section 3 deployment or Section 4 setup. Do not repeat privacy deletion. The source decision is
no longer waiting for an MIT exception or a license choice.
The verified Cloudflare configuration and pending Resend capacity decision are
independent of the completed privacy recovery.

## Privacy recovery complete, do not repeat the gate

Gate 11 revision 10 started the read-only preflight execution
`abda-nl-stg-migrate-n9lelb6`, which ended in `Failed` on September 5. The
deletion execution was not started by that failed attempt.
[The recovery record](privacy-preflight-failure-20260905.md)
documents the subsequent investigation. Its first receipt identified an account-matching
refusal. Diagnostic revision 2 with `--preparation` has now verified the
earlier execution's actual command and inner preparation receipt. A subsequent
read-only inspection has also completed, with zero named test objects and zero
prepared accounts. Diagnostic revision 3 with `--history` then found successful
deletion execution `abda-nl-stg-migrate-w9hv7gt`, with the reviewed revision 10
runner and image, one deletion success marker, no refusal, and one deleted
identity, project, share link, and MCP credential each. Its exit 2 concerns
unrecognized historical database inputs, not a failed deletion job. The
final metadata receipt subsequently confirmed the expected PostgreSQL host
and the preparation, deletion, and inspection ordering. Review of the exact
runner code established the fixed `abda` destination without reading passwords.
The password-reference-name mismatch does not change that destination; the
old diagnostic has not been rerun or relabeled as passed. The operator then
confirmed deletion of the disposable Auth0 identity. Do not rerun the SQL
inspection or any privacy phase just to obtain a different exit code.

The preparation and deletion commands in Section 2 are historical instructions,
not the next task for this already exercised disposable account. Do not recreate
the account, project, share, or MCP token. The prerequisite is closed by the
combined historical receipts, destination review, and operator-confirmed Auth0
cleanup, not by a newly executed destructive gate.

The first revision 9 deletion attempt stopped before starting a deletion
execution because its historical-template preflight found no exact match.
Revision 10 replaces that brittle check with a read-only database-state
preflight. The prior attempt changed no account or Azure state.

Remaining operator work:

1. Confirm the Resend production sending capacity described in Section 5.
2. Then run the current helper's rollback, promotion, and final audit in
   Section 5. Keep the ten-user pilot until those prerequisites are met.

Section 3, including its funded request and audit, is complete. Public
Chromium and Firefox checks and the bounded capacity smoke passed afterward.
No new privacy, token, BYOK, or browser model test is required now.
Section 4's root and `www` redirects and its complete public hostname gate are
also verified. Do not repeat the DNS or redirect setup.

The hardened-image deployment, its audit, BYOK, MCP, capacity, Chromium, and
Firefox checks are already complete. Do not rerun them unless the relevant
application code or configuration changes. The remaining presentation-hardware
checks and recovery tabletop are batched in Section 6.

The historical `p` helper block below uses commit
`4d62e92c443480d1a72530d3dcc4022a0e5adbfd`. Do not use it to repeat privacy work.
The separate `q` helper in Section 3 is the current GPL rollout helper.
Refresh saved copies of this runbook from the
personal repository's `development` branch before any new cloud operation.

The managed-boundary image already passed live OpenRouter BYOK acceptance. The
then-current hardened service passed fresh public Chromium and Firefox accessibility
and bounded capacity checks on 2026-09-04 CDT. Subsequent runtime changes remove
private or model-derived identifiers from operational logs, reduce evaluator
route-list output, and prevent unexpected exception messages or tracebacks from
entering logs. The current GPL cumulative image also disables hidden Anthropic SDK
retries and conservatively settles provider attempts whose billing outcome
cannot be proven. It rejects empty or malformed billed responses while retaining
their usage evidence, distinguishes a Gemini content-policy rejection from an
outage, and deterministically closes provider network clients after API, MCP,
evaluation, and outage-drill calls. It does not alter authentication, BYOK key
storage, MCP scopes, budget limits, database schema, or browser interactions.
It also refreshes and locks the durable account row before project, share, MCP
credential, or trial mutations, so a request authenticated just before privacy
suspension cannot create new state afterward. CodeQL reports zero findings for
the new source, and the image workflow rebuilt, smoke-tested, and attested its
exact digest.

This runbook collects the remaining cloud and account work into one operator
batch. The hardened-image deployment and live audit, Azure alert deployment,
alert-email delivery, BYOK browser Gate, bounded capacity smoke, and automated
Chromium and Firefox accessibility Gate are already complete. The last two
were rerun against the unchanged hardened service after privacy preparation.
Do not rerun them unless their corresponding code or configuration changes.

The previous hardened release identity was:

- application source commit: `51702e175bd14d4cb54075808f839d173d561324`
- source tag: `service-image-staging-safe-exceptions-20260902-191532`
- image digest: `sha256:a0b3ba24aff06ecf461f86547131d86451c541e306a7ecfc278f280fcef5c0bc`
- provenance attestation: `https://github.com/Liu-Hy/ABDA-NL/attestations/44802693`
- target pilot revision: `abda-nl-stg-web--harden-51702e1`
- public origin: `https://demo.abda-nl.org`

The live, audited GPL cumulative identity is:

- application source commit: `ed241c1509739f16b2433ced686da76fe1ed1d94`
- source tag: `service-image-staging-gpl3-20260905-ed241c1`
- image digest: `sha256:b7025d4322e05a698e79eb120a233c68cf638d5cdd44c8f58223681ff15ae1c5`
- publication and verified provenance: [GPL artifact checkpoint](gpl-distribution-checkpoint-20260905.md#published-artifact)
- target pilot revision: `abda-nl-stg-web--gpl-ed241c1`
- public origin: `https://demo.abda-nl.org`

This exact image has completed Section 3. Do not repeat deployment merely to
collect another receipt. The privacy Gate was intentionally bound to the
previous hardened image; its completed work must not be repeated.

Before running the final promotion, confirm production email capacity. The
current Resend Free limit of 100 messages per day has no headroom for 100 new
OTP users plus retries and returning logins. The recommended public-launch
choice is Resend Transactional Pro, currently $20 per month with no daily
limit. Keep the existing verified domain and API key integration. If the
service remains on Free, stop after the ten-user pilot and stagger invitations
instead of running the 100-user promotion.

## Historical helper for completed gates

Do not start here for remaining operations. Use the separate Section 3 `q`
download and verification block if the previous session closed. Its deployment
and pilot audit are already complete. This `p` helper is a historical reference.

A new or existing Azure Cloud Shell session is acceptable. Paste this complete
block once. It downloads a small helper from an immutable commit and verifies
its checksum before saving its temporary path in `p`.

```bash
u='https://raw.githubusercontent.com/Liu-Hy/ABDA-NL'
c='4d62e92c443480d1a72530d3dcc4022a0e5adbfd'
f='deploy/azure/consolidated-operator-gate.sh'
s='41e992c4e5a1d98ec1c48975ab61ea66750af4281051b7f0810adc142879eb7c'
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

There are intentionally two different immutable commits in this handoff. The
download block above uses `4d62e92c443480d1a72530d3dcc4022a0e5adbfd`,
which pins the helper file itself. When that helper runs, it must print:

```text
ABDA-NL consolidated operator helper revision: 14
Pinned gate source commit: 335611df6bc4b749f491320c9713cc259773ca92
```

The second commit pins the complete child-Gate bundle. Seeing it does not mean
that the helper download used the wrong revision.

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

Historical instructions only. The existing privacy acceptance and external
Auth0 cleanup are complete. Do not run this section or recreate its account.
The status and steps below record the original two-phase workflow.

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

Before it creates a deletion execution, the current Gate runs a read-only
execution that checks the durable account state and measures 900 seconds from
the account's preparation timestamp. It also verifies that bearer access is
revoked, model reservations are settled, and trial credit was never activated.
Only a successful preflight can start the permanent deletion execution. A
failed read-only preflight can be retried after the reported interval without
repeating preparation or weakening the mutating execution boundary.

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

## 3. Deploy and audit the cumulative service image

Status: complete. The operator supplied the successful `gpl-6` pilot audit for
`abda-nl-stg-web--gpl-ed241c1` and confirmed a normal funded answer. Public
Chromium, Firefox, and bounded capacity checks passed afterward. See the
[live checkpoint](gpl-live-checkpoint-20260905.md). The steps below are retained
for recovery, not as a request to repeat completed work.

This image includes the WebKit keyboard correction and all cumulative fixes.
The license change itself does
not require an additional browser test.

The recovered successful deletion receipt has been reviewed against the
expected database, and the operator confirmed removal of the exact disposable
Auth0 identity. Do not repeat deletion. A new or existing Cloud Shell session
is acceptable. Paste this complete block once:

```bash
u='https://raw.githubusercontent.com/Liu-Hy/ABDA-NL'
c2='b14357722d8a2f6686d1fb14beb2c0806cb568be'
f2='deploy/azure/post-privacy-operator-gate.sh'
s2='2e8fa216c34c4ff96c674e1d6f00ebd8d7169e84c951a38a8209dfb887328dcb'
q="$(mktemp /tmp/abda-post-privacy.XXXXXX)"
curl -fsSL --connect-timeout 10 --max-time 60 "$u/$c2/$f2" -o "$q" &&
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

This helper also has two intentional commit identities. The download block
uses `b14357722d8a2f6686d1fb14beb2c0806cb568be` for the helper file. Its
verification output must begin with:

```text
ABDA-NL post-privacy operator helper revision: 7
Pinned gate source commit: 9ccbab542a93898c02223b94dfc9e0e1d4eacb7e
```

The printed commit pins the post-privacy child-Gate bundle and is expected to
differ from the helper file's download commit.

Deploy the exact attested cumulative image:

```bash
bash "$q" deploy
```

At its prompt, type
`PRIVACY_DELETION_VERIFIED_DEPLOY_ABDA_SERVICE_IMAGE` once and press Enter.
The privacy recovery prerequisite for that phrase is now met. The
Gate changes only the web image and revision suffix. It verifies the new
retention, conservative provider-billing, response-validation, client-lifecycle,
and account-suspension boundaries, and preserves the existing managed-service
and shared-view behavior. Required success ends with:

```text
result: SERVICE_INTEGRITY_IMAGE_DEPLOYED_AUDIT_REQUIRED
```

Before the audit, sign in with the existing funded pilot account. Keep
**Funded model trial** and **Balanced** selected, ask one short question, and
confirm that a useful answer appears and the displayed balance decreases. Do
not activate another account, use BYOK, or repeat the call. This single request
checks the real managed-provider path whose response validation and connection
lifetime changed in the cumulative image.

Then run the read-only audit:

```bash
bash "$q" audit
```

Required success ends with:

```text
result: SERVICE_INTEGRITY_RELEASE_AND_OBSERVABILITY_AUDIT_VERIFIED
```

Do not repeat MCP or OpenRouter BYOK acceptance for this image. Those paths and
their trust boundaries are unchanged. Provider accounting, client lifetime,
and stale-session suspension behavior are covered by focused tests, the real
PostgreSQL CI Gate, the full CI matrix, and the one funded smoke above. After
the audit receipt arrived, Codex ran the automated public Chromium and Firefox
checks and the bounded deterministic capacity smoke successfully. No further
manual browser action is needed for this checkpoint.

If Cloud Shell closes, repeat only the block that creates `q`, run
`bash "$q" verify`, then resume the required phase. Every mutating Gate detects
its exact completed or pending revision.

## 4. Add the friendly root-domain redirect

Status: complete. The operator saved the corrected hostname expression and
the unchanged read-only gate returned
`PUBLIC_HOSTNAME_AND_EMAIL_DNS_BOUNDARY_VERIFIED`, exit code 0. Both redirects,
path and query preservation, demo readiness, Auth0 discovery, and Resend DNS
passed. The instructions below are retained for recovery only.

Follow the exact dashboard values in
[`cloudflare-apex-redirect.md`](cloudflare-apex-redirect.md). This creates only
the proxied `@` and `www` placeholder records and one narrowly matched 301
redirect rule. It must not match `demo`, `login`, or `auth`.

After the two records and rule are saved, tell Codex. The complete read-only
check can run from Delta without your Cloud Shell or credentials. If you
prefer to run it yourself, use the same current `q` helper from Section 3:

```bash
bash "$q" hostname
```

If that Cloud Shell session closed, repeat the preparation block under
Section 3 to recreate `q`, and run `bash "$q" verify` first. Do not repeat
`deploy` or `audit` just to recreate the temporary helper.

It verifies root and `www` redirects, path and query preservation, direct demo
readiness, Auth0 discovery, and the Resend DNS boundary. It makes no change and
uses no credential. Success ends with:

```text
result: PUBLIC_HOSTNAME_AND_EMAIL_DNS_BOUNDARY_VERIFIED
```

## 5. Rehearse rollback, promote, and run the final audit

Proceed only after the cumulative-image deployment and audit, prior BYOK and
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
result: COMPATIBLE_SERVICE_IMAGE_ROLLBACK_AND_RESTORE_VERIFIED
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
