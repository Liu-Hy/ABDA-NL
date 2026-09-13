# COMMA 2026 demonstration playbook

State: September 13 conference-readiness update; presentation-hardware acceptance remains pending

These labels describe the current development UI. Confirm the deployed version
before rehearsing the public URL; a local candidate capture is not evidence of
a hosted update.

This playbook keeps the live demonstration focused on the research contribution
while preserving a deterministic path when an external model, identity service,
network, or public host is unavailable. It does not replace the public release
checklist or authorize a cloud configuration change.

## Roles

- Bertram is the on-site presenter. He controls the projected browser and tells
  the argumentation story.
- Haoyang is the primary service operator. He watches health, the active model
  route, latency, and aggregate budget from a separate, unprojected device.
- Shawn is the technical backup for the paper example and original demo
  behavior when available.

During the talk, the operator reports only a short status such as "public site
healthy" or "use the deterministic fallback." Do not diagnose Azure, Auth0,
Cloudflare, or a provider on the projected screen.

## Prepared state

Complete these steps before the audience enters:

1. Sign in to `https://demo.abda-nl.org` with the dedicated presentation
   account. Do not show the email inbox or an OTP on the projector.
2. Confirm that the account has enough funded balance for the rehearsed calls.
   Do not activate a trial during the presentation.
3. Open the scenario-name menu and select **Popov v. Hayashi**. If changes are
   present, use **Reset** to return to baseline. Reset is hidden at baseline.
   Close every dialog and leave the four reasoning panels visible.
4. Keep a second, unprojected browser on
   `https://demo.abda-nl.org/health/ready`. A successful response is
   `{"status":"ready"}`.
5. Rehearse **AI off** in the top-bar model menu. The same setting is under
   **Account → AI access**; select **AI off**, then **Use this access setting**.
   It hides chat and AI authoring, stops pending requests, and retains manual
   exploration and drafts. The choice survives reloads in that tab. Selecting
   a model in the top bar, or applying funded/BYOK access, restores AI.
6. Prepare a Delta fallback with an existing `ssh delta-demo` tunnel, and a
   separate laptop installation with dependencies already installed. On the
   laptop, start `abda-nl --basic --host 127.0.0.1 --port 8766 --no-browser`
   and open `http://127.0.0.1:8766`. Distinct ports keep this separate from the
   Delta tunnel on 8765. Disconnect laptop networking and rehearse it once.
   Copy and extract the offline screenshot ZIP onto the laptop as well.
7. Close password managers, provider dashboards, email, Cloud Shell, developer
   tools, and any tab containing a token or private share link.

## Primary narrative

The sequence below is deliberately short. It leaves time for questions and can
be repeated consistently during rehearsal.

### 1. Orient the audience

Introduce Popov v. Hayashi as the dispute over Barry Bonds's 73rd home-run
baseball. Point out the four panels: conclusions, facts and assumptions, rules,
and **Chat & Explore**. Explain that natural-language descriptions make the
knowledge base readable, while the ABDA engine computes the arguments,
attacks, and conclusion labels.

### 2. Inspect a conclusion and its argument

Choose the accepted conclusion **Popov has a legitimate claim to the baseball**
and select **Explain**. A single argument opens directly; choose one if a
picker appears. Expand a support branch and identify an attack when shown.
An absent attack edge alone does not establish a preference. Emphasize that this
explanation comes from the deterministic argument graph, not from an
LLM-generated answer. Close the dialog with Escape to demonstrate keyboard
operation and focus return.

### 3. Demonstrate a reversible what-if change

Filter the facts panel to assumptions and activate **the court is exercising
its equitable power to divide the proceeds between the parties**. Use the
suspension-impact preview to show the consequences before selecting **Apply**.
Point out the modified-state indicator and that the equal-division conclusion
becomes undecided under the competing equity rules. Select **Reset** before
moving on, so later steps use the bundled baseline. **Undo reset** remains
available until the next edit or context change; the conversation is preserved.

### 4. Ask one grounded model question

Show that the small AI icon beside an item places its reference in the input
without sending. Add your question before **Ask**. Use this rehearsed question:

```text
Why do both Popov and Hayashi have legitimate claims, and which sources in this scenario support that conclusion?
```

Point out the answer's model, cost, and relevant source cards when present.
The source cards distinguish quoted wording from context; **Open in Sources**
reads the saved document. Verified quotation locations do not establish that
an answer's interpretation is correct. The argumentation engine determines
the labels. Ask only one question unless the audience requests another.

### 5. Show human-reviewed authoring

Open **+ Add** or a rule's action menu and choose an AI edit. Explain the
propose, validate, review, and apply sequence. If the rehearsed proposal returns promptly, show
its structured operations and advisory issues without applying it. If it is
slow or differs from rehearsal, cancel it and explain that model output
never changes the scenario without explicit human approval.

### 6. Close with portability

Briefly show **Conclusion graph** or **ASPIC- text**, then explain that the same
application runs at the public URL, on an ordinary laptop, and through the
Delta `demo` launcher. **Download scenario (.json)** in the scenario menu
includes the rules, meanings, and reference text for import elsewhere.
Mention private scenarios and scoped MCP access only if time permits. Do not
create or reveal an MCP token during the talk.

## Recovery ladder

Use the first healthy option. Do not spend presentation time debugging a failed
dependency.

1. **One model call fails or is slow:** use **Stop**, then **AI off** in the
   model menu. Continue with Explain, assumption changes, graph view, manual
   editing and ASPIC- view. These features do not need a model or sign-in.
2. **The CloudBank route has a qualifying service outage:** a deployment with
   fallback enabled automatically attempts the same qualified model through
   OpenRouter, ordinarily after at most one CloudBank retry. Recent failures
   can briefly open a circuit; later requests probe CloudBank again. With
   sufficient credit and budget, this covers eligible provider outages.
   Invalid input, missing local configuration, refusal, cancellation and
   expired request deadlines do not trigger backup spending. If both routes
   fail, manual reasoning remains available. No provider login refresh is
   needed on the presenter's laptop; the hosted server makes these calls.
3. **Email or Auth0 is unavailable:** keep using the already authenticated
   presentation session. Do not sign out or demonstrate registration.
4. **The public application is unavailable:** switch the projected browser to
   `http://127.0.0.1:8765` through the prepared `ssh delta-demo` tunnel.
5. **The public application and Delta are unavailable:** switch to the prepared
   local basic instance at `http://127.0.0.1:8766`. Continue the deterministic narrative and
   state plainly that the hosted model feature is unavailable.
6. **The presentation computer or conference network fails:** use a locally
   stored, non-secret recording or screenshots of the rehearsed deterministic
   flow, then take questions.

Database, identity-integrity, authorization, or accounting uncertainty is not
a reason to bypass a guard. Disable new funded use after the talk if necessary
and continue only with a deterministic instance.

For an operator-controlled, service-wide basic deployment, the application now
accepts `ABDA_ENABLE_LLM=0` in staging and production. Provider preflight is
skipped, while ordinary identity, database and configuration safeguards remain.
Prepare and verify such a revision before the event. The normal hosted service
can keep AI enabled while the presenter uses its tab-local **AI off** option.
Neither option makes a remote website work without a network connection.

Database recovery is an incident operation, not a live-demo action. Before the
conference, Haoyang and one technical reviewer should complete the content-free
tabletop in the [PostgreSQL recovery runbook](database-recovery.md). During the
talk, use the deterministic fallback instead of attempting a restore or
database cutover.

## Offline screenshot backup

The agent can prepare the network-independent visual backup without an account
or a model call:

```bash
.venv/bin/python deploy/capture_conference_fallback.py \
  --output artifacts/conference/new-capture
```

Choose a fresh output path for each capture. The command refuses to overwrite
an existing directory or ZIP. It selects **AI off**, captures the six deterministic narrative views
from the built-in Popov scenario in a new anonymous Chromium context, checks the
equity conclusion and Reset behavior, and writes a local HTML gallery, PNGs,
SHA-256 manifest, and adjacent ZIP. It verifies the gallery with browser
network access disabled. A request allowlist blocks model, project, token,
login, and unrelated network operations. The anonymous session-status read
is permitted. State computation may create expiring rate-limit counters but
does not save a private scenario or alter the built-in scenario.

Regenerate the pack from the deployed candidate being rehearsed.
For a local candidate, add `--base-url http://127.0.0.1:PORT` using the actual
loopback port. Only the public origin or an explicit HTTP loopback address is
accepted. On Delta, run browser capture in Slurm with a disposable local
server. The manifest and gallery identify the captured origin. The manifest's
`capture_tool_revision` describes the capture checkout, not the served release;
bind a local candidate's source and served asset hashes separately.

Copy the verified ZIP onto the presentation laptop before the conference,
extract it, and open `abda-nl-offline-backup/index.html` in a browser. No web
server or internet connection is needed. The page visibly labels these as
screenshots, not a live or interactive demonstration. Each PNG can also be
opened separately or incorporated into the presenter's slides. Generated
captures stay under gitignored `artifacts/`; the generator is tracked.

This backup does not replace the two actual-hardware rehearsals or prove
that local launching, the laptop tunnel, or a screen reader has passed.

## Operator preflight

On the presentation day, the operator checks these from unprojected devices:

```bash
curl -fsS https://demo.abda-nl.org/health/ready
```

On Delta:

```bash
demo doctor
demo status
curl -fsS http://127.0.0.1:8765/health/ready
```

On the presentation laptop, confirm that its browser can load both
`https://demo.abda-nl.org` and `http://127.0.0.1:8765`. A server-side Delta
check alone does not prove that the laptop tunnel works.

Do not run a deployment, migration, rollback, provider drill, budget promotion,
or DNS change during the presentation. Those actions belong in a separate
operator window before or after the event.

## Rehearsal record

Record each dry run without secrets or private content:

- date, location, presenter, and operator
- public, Delta, or local path used
- browser, display resolution, and actual zoom
- primary narrative completed or the exact step skipped
- model route label, approximate latency, and whether fallback appeared
- keyboard, Safari, and screen-reader observations
- known limitation discovered and its tracked resolution

Two complete rehearsals on the actual presentation laptop are required before
freezing the conference candidate. One rehearsal must include the deterministic
fallback transition.

The September 13 investigation reached the public site from five Spanish
probes, including three in Barcelona. This establishes regional reachability
at that time, not venue WiFi, actual-device sign-in or live model-generation
acceptance. The hosted backend remains in the US. Rehearse the public URL,
funded question, **AI off** transition and local backup from the venue.
