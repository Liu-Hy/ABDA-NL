# Three-part scenario materials, September 8, 2026

Status: implementation and validation in progress. Not yet a live deployment
receipt. The community-example release remains the public baseline until the
rollout evidence below is completed.

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

The planned rollout changes only the web image and revision suffix. It does
not change secrets, catalog/admin configuration, Auth0, DNS, probes, scaling,
the saved migration job, trial limits, or provider routing. Stable main remains
untouched.

Once users save scenarios containing `sources`, a pre-materials image cannot
parse those scenario objects even though the database schema is unchanged.
Use this image or a newer compatible image for recovery. Do not roll back to
an older parser or remove user materials to make an old image start working.

## Acceptance and rollout evidence

Pending final source verification, immutable image publication, and live
image-only deployment. See [the user guide](../scenarios.md) for the workflow.

Initial CodeQL review flagged the filename regular expression's unbounded
repetition. Added explicit start anchoring and a repetition bound matching the
filename limit in the validator, schema, and browser. The security gate remains
enabled and the candidate must pass it before deployment.
