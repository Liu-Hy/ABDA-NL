# Demo revision requirements

This document and the [review guide](demo-revision-review-guide.md) are the two
entry points for an independent review of the September 2026 demo improvements.
Read this document for intent and constraints, then the guide for implementation
choices, evidence, and unresolved review questions. An implementation or a
passing test does not, by itself, establish that a requirement was satisfied.

## Authority and scope

The sources are Haoyang's `Requirements.docx`, the colleague suggestions preserved
in the [September 9 investigation](demo-revision-review-20260909.md), his six
supplemental requests, and his later messages in this conversation. Later explicit
instructions take precedence. The initial instruction to investigate without
implementation was superseded by authorization to implement using subagents.

Below, **O** refers to the original product questions in `Requirements.docx`;
**G** refers to the colleague's Demo or More radical ideas indices; **U1-U6**
refer to Haoyang's six supplemental requests. The two different G Demo 3 entries
retain their original Agent A / Agent C labels. The original document's opening
research motivation and closing collaboration request also apply.

This is a demo release, preserving paper fidelity and improving live use. Paper
bibliography edits, expanded paper descriptions, and new research experiments
were suggestions, not implemented deliverables. Passing automated checks does
not establish readiness on the actual conference laptop, network, or projector.

## Product requirements

| ID | Required behavior | Origin |
| --- | --- | --- |
| R01 | Preserve the paper's separation of natural-language assistance from deterministic ABDA reasoning. The engine computes arguments, attacks, preferences, and grounded labels. Model text cannot assign labels or silently apply edits. Keep the existing four-panel explorer, Explain discussion game, glossary, graph, raw ASPIC- view, and bundled examples usable. | O: paper consistency and live readiness |
| R02 | Provide a stable public website and convenient local/Delta operation. Keep the current paper demo available while developing improvements incrementally. Consider correctness, intuitive interaction, visual quality, keyboard access, and narrow layouts together. | O: hosting and collaboration |
| R03 | Offer the first 100 eligible registered public users $5 each. Give the five named institutional identities below $50 each. Preserve prior spending and reservations, prevent repeat introductory grants for the same known verified email or sign-in identity (including after deletion), support later registration, and keep ordinary users' policy intact. Eligibility must not grant unrelated curator privileges. | O: trial credit; U1 |
| R04 | Eligible funded requests use the selected model through CloudBank-funded Azure or GCP. OpenRouter is Haoyang's paid safety net after a CloudBank API failure, using the same model. A CloudBank retry was explicitly left to engineering judgment. Neither AWS nor an unfunded Google project may supply the subsidized primary. When AI is unavailable, retain the scenario, draft, deterministic reasoning, manual edits, saving, and export. | O: funding; U2 |
| R05 | Use one qualified selection pool across quota use and BYOK, with appropriate provider subsets, and keep MCP model admission consistent. Each choice requires actual access through `(CloudBank Azure OR CloudBank GCP) AND OpenRouter`, compatible model identity/version, and application qualification. Listing in Azure's catalog alone is insufficient; identify undeployed candidates to the owner. | G Demo 6; U3 and later deployment clarification |
| R06 | Select strong, economical models using public LiveBench and Artificial Analysis results and provider prices. Preserve family preference rather than eliminating Claude solely because Gemini has a better aggregate score. Prefer direct successors such as Gemini 3.8 over 3.7 and Sonnet 5 over 4.6 without commissioning a new general benchmark. Exclude Claude Haiku, GPT-5.6 Luna, and Gemini 3.5 Flash-Lite. Investigate two or three additional strong, economical choices, and include Gemini 3.1 Pro. Stay within the GPT-5.6 Sol / Claude Opus 5 price class; exclude GPT-6 Astra and Claude Fable 5.1. | O: model value; U3 and subsequent messages |
| R07 | Carefully test every admitted model on every LLM feature; separate MCP integration checks are covered by R09, consistent with U4's permitted exception. Tune prompts when and only when demonstrated behavior requires it. Prefer short, generalizable rules; tolerate minor imprecision, but address wrong outcomes, causes, polarity, or edits. Passing existing prompts need no cosmetic rewrite. Public benchmark scores do not replace these application checks. | U4 and repeated clarification |
| R08 | All paid evaluation, diagnostics, retries, tuning, and resumed runs together must stay within the original $100 CloudBank allowance, with no paid OpenRouter testing. Use public benchmarks for general quality/cost/speed comparison; measured application duration is for operational limits and diagnostics. Preserve original failures and actual answers rather than selecting only favorable outputs. | U4 and benchmark clarification |
| R09 | A user with a valid Codex or Claude Code subscription can inspect a scenario, perform an authorized versioned edit, and verify the recomputed project through MCP. Subscription-backed client reasoning must work with zero ABDA model credit. Separately expose optional server-model tools with explicit scope and quota charging. Test both real clients, successful writes/readback, isolation, stale and invalid operations, revocation, and browser agreement. | O: subscribed agents; U5 |
| R10 | Clicking `?` inserts the same generated question into the bottom-right composer for editing. Preserve existing text, focus/reveal the composer, and retain the selected item's identity. Support removable references and several selected items. Clicking must not send an LLM request, append a chat turn, or spend credit; only explicit submission does so. Handle stale context, unavailable access, pending requests, mouse, keyboard, and narrow layouts. | G Demo 3 Agent C; U6 |
| R11 | Provide New, switching, deletion, automatic conversation saving, export, and editing a prior question to create a separate conversation. Preserve the original conversation and each turn's scenario context, including pending edits and source material. Make the scenario used for a new fork explicit. The original suggestion mentioned tabs; see the guide's storage/navigation decisions. | G Demo 3 Agent C |
| R12 | Permit fluent paraphrases while exposing inspectable evidence. Verified quotations must match supplied source spans and attribution. Formal references must identify the relevant rules, arguments, and computed labels. A real filename does not validate an invented quotation, and quotation existence alone does not prove a paraphrase is supported. | G More radical ideas 1 |
| R13 | Connect natural-language claims, formal rules, and individual argument derivations. Distinguish derivations sharing a conclusion or top rule; expose premises, subarguments, rules, labels, and attacks. Clearly distinguish the compact conclusion overview from individual arguments and support from attack. | G More radical ideas 2 and 3 |
| R14 | Preserve the visible “Chat & Exploration” heading, modified-state count and Reset, changed-label highlighting, and accurate “Premises and subarguments” wording. Explain accepted conclusions even when no attacker remains. Increase the old 15-character generated edit-ID limit and preserve existing longer IDs. Remove unused minimap code if a useful minimap is not implemented. | G Demo 1, 2, 3 Agent A, 4, 5, 7, 8 |
| R15 | Preserve easy scenario creation/import/editing and portable export. Ordinary use should not require YAML or ASPIC- expertise. Exported scenarios and conversation snapshots must contain facts/rules, glossary, and actual corpus text, and work without the original source catalog. Uploaded reference text does not automatically become logical facts. | Existing scenario/workspace requirements supporting O and G |

The R03 identity list is exact, using the sign-in system's email normalization:

| Administrator | Institutional email |
| --- | --- |
| Haoyang | `hl57@illinois.edu` |
| Bertram | `ludaesch@illinois.edu` |
| Shawn | `bowers@gonzaga.edu` |
| Martin Caminada | `CaminadaM@cardiff.ac.uk` |
| Timothy McPhillips | `tmcphill@illinois.edu` |

## Engineering constraints to preserve

These are existing service and repository constraints, not additional claims
about what Haoyang explicitly specified in the six requests.

| ID | Constraint |
| --- | --- |
| E01 | Keep the stable paper artifact on iDAKS `main` separate from service development. Preserve local work, incremental commits, and a usable demo. `Requirements.docx` and `camera-ready.pdf` are intentionally untracked; their publication is a separate decision. |
| E02 | Use the shared `demo` launcher and tracked `.demo.json`, retaining `{host}` / `{port}` and a foreground child process. Preserve relay to `dt-login03` and loopback `127.0.0.1:8765`. Laptop access needs `ssh delta-demo`. No tmux or server owned only by an agent session. Heavy or long work belongs in Slurm/Open OnDemand. |
| E03 | Enforce authenticated, verified, active account eligibility, project ownership, optimistic versions, revocable scoped tokens, and read-only shares on every relevant path. Keep privacy/export/deletion, abuse limits, origin checks, TLS, CSP, escaped rendering, bounded input/computation, and accessible controls intact. Do not weaken security to make acceptance scripts pass. |
| E04 | BYOK is self-funded and has no ABDA trial deduction. Restrict endpoints/models; keep application-managed provider keys in tab/request memory, out of persistent history, exports, logs, and MCP arguments. Never print or commit credentials. Root `.env` stays gitignored with mode 600. Sanitize provider errors. Preserve OpenRouter zero data retention, denied data collection, required parameter support, price caps, and AWS backend exclusions. |
| E05 | Verify Azure subscription/resource/deployment and GCP project, billing/quota project, authentication, and permissions against the owner's CloudBank setup. Personal `gen-lang-client-0957296946` is not the CloudBank project. A working API key or ADC refresh alone is insufficient funding proof. Deployment aliases, model versions, privacy settings, and price assumptions must be explicit. |
| E06 | Reserve conservatively before every physical paid attempt and reconcile success, failure, retry, cache/reasoning usage, timeout uncertainty, and crash recovery. Keep user credit, administrator allocation, OpenRouter emergency exposure, and evaluation budget separate and concurrency-safe. Preserve ledger conservation, cumulative public grant limits, and protection against repeat introductory credit claims, including after account deletion. Retain only program-lifetime keyed eligibility markers with a stable secret; do not claim this identifies one unique human. |
| E07 | Deploy verified immutable images with license/provenance checks, matching database schema, private PostgreSQL access, restricted application roles, and bounded connection pools. Drain incompatible writers before transferring credit; recovery after schema 0007 must understand both the accounting and retained eligibility markers, using the same stable key. Preserve cloud settings, secrets, quotas, and recovery controls. Use disposable fixtures for acceptance, then archive/revoke/retire them and verify cleanup. Keep raw evidence private and retain failed verdicts. |

The [review guide](demo-revision-review-guide.md) records the concrete choices
under these requirements. Challenge those choices where they do not adequately
serve the user intent; do not reinterpret them as new user instructions.
