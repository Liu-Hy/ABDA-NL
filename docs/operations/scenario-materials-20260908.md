# Three-part scenario materials, September 8, 2026

Status: deployed and healthy at <https://demo.abda-nl.org>. The agent performed
the approved image-only update through the existing dedicated Azure session.
No operator Cloud Shell relay or new authentication setup was needed.

## Correction to the scenario design

Shawn's original model separates ASPIC- rules, a glossary of term meanings,
and a document corpus for LLM context. The simple new-scenario builder already
captured rules and descriptions, but lacked a private custom corpus and a
direct rule-text/glossary import. This release fills those gaps without
changing the argumentation engine or replacing the simple builder.

- The ASPIC- importer accepts bounded propositional notation from the viewer,
  explicit or inferred focus conclusions, block priorities, and suspended
  defeasible rules. Unsupported syntax is rejected. YAML/JSON remains the
  complete scenario round-trip format.
- A glossary is the existing description/negated-description vocabulary,
  not an independent competing metadata layer. Partial glossary imports
  preserve other definitions and never rewrite rules.
- Optional `sources` contain validated citation filenames, plain reference
  text, and optional HTTPS attribution URLs. Source URLs are not fetched.
  No arbitrary local paths, remote URL retrieval, ZIP extraction, object
  storage, vector database, or new cloud resource is introduced.
- Documents are reviewed before saving. The original PDF is discarded after
  extraction. Only normalized text is stored in the existing scenario JSON.
  Reference text does not become logical facts or rules automatically.
- Chat, proposer, and reviewer prompts receive bounded lexical excerpts
  selected using the question or instruction, plus the glossary and engine
  state. Excerpt selection is not exhaustive semantic retrieval. Prompts mark
  documents as untrusted data and preserve the engine's authority.
- Private ownership, optimistic version checks, read-only sharing, MCP access,
  public snapshot consent, export, suspension, and deletion continue through
  their existing boundaries. Publication preview explicitly exposes complete
  attached text, rather than only the selected LLM excerpts.

## Resource and privacy limits

Each upload is at most 1 MB. A scenario holds at most ten documents, each with
100,000 characters, and 400 KB of UTF-8 reference text in total. Existing
scenario and HTTP-body limits still apply. The source-preview endpoint requires
a verified session, same-origin writes, and its own ten-request/minute limit.

PDF extraction uses hash-locked pypdf in one disposable subprocess at a time
per web process, with a minimal environment that excludes service credentials.
The fixed worker receives bytes via stdin, writes no files, and has six CPU
seconds, a twelve-second parent timeout, zero core-dump allowance, and a
512 MiB virtual address-space limit. This is resource isolation, not an OS
security sandbox. The original 128 MiB address-space limit was insufficient
for Delta's Python, which maps roughly 230 MiB of mostly shared libraries
before pypdf loads. Hosted containers retain their own memory boundary.
Scans, encrypted PDFs, more than forty pages, empty extraction, and excessive
output are refused with a text-upload/paste alternative. PDF extraction is
unavailable on hosts without POSIX resource limits; text input still works.

Private materials are not research data. Saved text follows project retention
and deletion. Active project shares expose saved materials, and a consented
public submission publishes their full text and URLs. Uploaded files are not
an authorization to fetch the URL or train on private content.

## Compatibility and deployment boundary

No database migration is required; database revision remains `20260908_0005`.
Serialization omits the new field when empty, preserving all six bundled
scenario payloads and computations. Portable exports with materials use
version 2; this image accepts versions 1 and 2.

The completed rollout changed only the web image and revision suffix. It did
not change secrets, catalog/admin configuration, Auth0, DNS, probes, scaling,
the saved migration job, trial limits, or provider routing. Stable main remains
untouched.

Once users save scenarios containing `sources`, a pre-materials image cannot
parse those scenario objects even though the database schema is unchanged.
Use this image or a newer compatible image for recovery. Do not roll back to
an older parser or remove user materials to make an old image start working.

## Acceptance and rollout evidence

See [the user guide](../scenarios.md) for the workflow.

- Application source: `995c83c6b577c084ff8833725c0ef347798b9041`.
- Public image: `ghcr.io/liu-hy/abda-nl@sha256:d231e7e70226928ca1e6d8bb4b15063527c0cbae57de03d5912baaf0d527cab6`.
- Healthy Azure revision: `abda-nl-stg-web--materials-995c83c`, one ready web
  replica, zero restarts at acceptance.
- Superseded revision: `abda-nl-stg-web--curation-a72872f`.
- [Source CI](https://github.com/Liu-Hy/ABDA-NL/actions/runs/34286609164)
  and [tag CI](https://github.com/Liu-Hy/ABDA-NL/actions/runs/34286622530)
  passed Python 3.10/3.13, native lock verification, migrations, PostgreSQL,
  secrets, deployment artifacts, and Chromium/Firefox/WebKit acceptance.
- [CodeQL](https://github.com/Liu-Hy/ABDA-NL/actions/runs/34286609058)
  and [image publication](https://github.com/Liu-Hy/ABDA-NL/actions/runs/34286622543)
  passed. Publication recorded 973 passed and 41 opt-in tests skipped;
  browser and PostgreSQL suites ran separately. Dependency audits found no
  known vulnerabilities. Exact-container smoke included real PDF extraction.
  Container security checks, SBOM publication, and provenance attestation passed.
- Anonymous GHCR retrieval verified the manifest digest, Linux/amd64 platform,
  source labels, and GPL label. Independent `gh attestation verify` passed
  with the expected publisher workflow and self-hosted signers disallowed.
- Local focused material/frontend tests: 48 passed. Final local Chromium
  suite: 40 passed. The test-only follow-up `1360273` waits for development
  sign-in's asynchronous refresh before injecting a save-order fixture; its
  application, migration, and dependency files are identical to the image source.
- All eight checked public application assets matched the reviewed source
  bytes. Canonical payload hashes for all six bundled scenarios were unchanged.
- All three new preview endpoints rejected anonymous calls with 401 and
  cross-origin calls with 403. Both generated and custom origins were ready.
- Live Chromium and Firefox acceptance each completed six axe scans, three
  viewport checks, and three keyboard checks, with no page or console errors.
  Each browser also passed three additional live axe scans of the new materials
  and import dialogs, including mobile layouts, read-only public glossaries,
  sign-in-required import controls, and an enabled scenario download.
- The external release check passed at `2026-09-08T22:42:38Z`: TLS, HTTP redirect,
  readiness, liveness, security headers, policies, public config, authenticated
  metrics, database pool, and budget invariants. Trial configuration remains
  100 users, $5 each, $500 total; bounded OpenRouter failover remains enabled
  with a $500 cap. Aggregate spending is operational evidence, not a promise
  that concurrent user activity stops during deployment.
- Structural before/after comparison proved that only the web image and
  revision suffix changed. Identity, environment, application configuration,
  and saved migration-job configuration were unchanged. No migration, provider
  call, real-account modification, or private-project write was performed.

Initial CodeQL review flagged the filename regular expression's unbounded
repetition. Added explicit start anchoring and a repetition bound matching the
filename limit in the validator, schema, and browser. The deployed candidate
passed the unchanged security gate.

Browser CI also exposed a timing-dependent download defect: opening New / Open
during a scenario request left Download current scenario disabled after the
request ended. Request start/completion now refreshes those controls, without
letting an older cancelled request enable them during a newer request. Two
deterministic browser cases hold the request while opening the dialog and
verify recovery and the exported scenario after both success and failure.
