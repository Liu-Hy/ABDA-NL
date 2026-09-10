# Comments on Tim's independent review

September 10, 2026. Response to [Tim's review](demo-revision-independent-review-20260910.md), against the [requirements](demo-revision-contract.md) and [review guide](demo-revision-review-guide.md).

I agree with the core of both High findings and most Medium findings. They justify corrective work despite the earlier passing acceptance checks. My main pushbacks concern overstated claims, incomplete proposed fixes, and policy choices presented as defects. I would also raise the Anthropic BYOK endpoint issue above Low. These comments propose changes; no implementation, deployment, credentials, or budget was changed for this response.

The inspected checkout is `94febed`; its changes after Tim's `026fde9` snapshot are three documentation files. I traced the numbered findings and the grouped Low items, ran isolated probes with fake inputs, in-memory SQLite, and JavaScript in a Node VM, and checked current OpenRouter documentation. The probes made no network or paid model calls. I did not repeat Tim's full suite, browser matrix, or live acceptance. Source locations below refer to this snapshot.

## Numbered findings

**1. Named-credit failures block sign-in: agree, High, with a narrower description.**

[Identity upsert](../app/services/accounts.py#L182) lets an allocation failure escape after committing the identity. My service-level probe confirmed two successive failures after actual privacy deletion, and two failures for a new beneficiary while the program was paused. However, an administrator already holding the full $50 could still sign in while paused, and resuming the program restored the new beneficiary's login. Pausing does not permanently lock out every administrator.

Separate successful authentication from unavailable automatic credit. Catch the expected allocation-unavailable condition, roll back that allocation transaction, and record a sanitized operational reason. Do not swallow identity/security failures or accounting corruption. Preserve explicit claim errors and retired-entitlement protection. Ordinary-credit eligibility after deletion is the separate policy question in finding 13.

**2. Missing configuration can sustain OpenRouter-first operation: agree, High. Refine the remedy.**

The [synthetic configuration failure](../app/llm/routing.py#L950) and [401 handling](../app/llm/routing.py#L795) allow repeated fallback without a real CloudBank attempt. The circuit does log an error, so this is not literally silent, but logs and the emergency cap do not provide adequate operator notification. The [startup check](../app/api/main.py#L95) also checks only the default profile and can return before checking its backup. Vertex token-refresh errors occur inside the metered request; the claim of no failed usage event should be confined to construction placeholders.

Validate required configuration for every public primary and enabled backup before accepting a new deployment. Missing local configuration should produce a route-unavailable condition, not a synthetic provider 401 that authorizes spending. Keep actual provider/authentication-service outages distinct from absent settings. An already running demo must retain its manual features when providers fail; do not make transient provider reachability a condition for the whole website to run. Add route-health/fallback-spend alerting. A configuration-health event is appropriate; inventing a paid-attempt event for an undispatched call is unnecessary.

**3. Fallback source passages receive the quotation caption: agree with the UX issue, qualify the verification claim.**

My probe confirmed that [source evidence](../app/llm/evidence.py#L238) can attach a genuine passage to a paraphrase that the passage does not support. Its bytes and offsets really do identify supplied text. Thus “exact excerpt” is literally correct, but the [shared caption](../app/static/exploration.js#L303) fails to distinguish a matched quotation from suggested reading context. It does not establish entailment.

Represent these as different evidence roles and explain the distinction in the UI. Keep source-span integrity separate from quotation matching and claim support. Simply setting `verified: false` would hide the passage under the current UI filter, losing useful inspectable evidence. I would fix the labeling without claiming the current code verifies fabricated quotations as genuine.

**4. Metadata preservation reverses requested edits: agree, Medium.**

I reproduced all three classes with the real [preservation helper](../app/llm/edit_service.py#L564): “Turn off” restored `active=true`, “much more important” restored block 1, and “comes from the 2025 roster memo” restored the old source. The application can undo a correct model proposal. More keyword synonyms would perpetuate the problem.

Preserve omitted fields, retain explicit proposed values, and expose the complete change for review. Any exclusive-field protection must have an unambiguous scope, rather than guessing arbitrary natural language. Add deterministic regressions for ordinary alternative phrasings and unrelated-field preservation. This is primarily a postprocessing fix, not evidence that all prompts need further tuning.

**5. Reviewer failure loses a validated proposal: agree, Medium.**

The [unguarded advisory call](../app/llm/edit_service.py#L787) should degrade to an explicit “review unavailable” result while retaining the validated operation for user inspection. Handle expected provider, deadline, and response-validation failures narrowly. Do not turn unknown programming errors or unresolved accounting failures into success. Preserve all settled proposer/reviewer costs, including failed attempts, using the metered client's totals rather than only successful response objects. Never apply the proposal automatically.

**6. Inspector initially selects the wrong polarity: agree, Medium.**

The [first-in-serialization-order selection](../app/static/exploration.js#L357) does not respect the clicked claim. Prefer the exact selected literal and an appropriate argument label, with explicit fallback when no such derivation exists. Apply the same rule to formal-reference navigation. Test the initial inspector state before interacting with its selector. The existing ability to choose the correct argument does not excuse the misleading initial view.

**7. Concurrent tabs lose history: agree, Medium; the suggested merge alone is insufficient.**

[Persistence](../app/static/exploration.js#L89) overwrites the entire store from one tab's stale memory. A `storage` listener or last-write timestamp merge helps but does not make simultaneous read/modify/write atomic. Merging only surviving records can also resurrect deleted conversations.

Use transactional per-conversation storage, or another design with explicit conflict and deletion handling. Cover concurrent creation, edits to the same conversation, deletion, reload, and account isolation. Browser-local storage itself was an intentional scope choice; cross-tab data loss was not.

**8. Scenario switching discards a paid answer: agree, Medium.**

The [response guard](../app/static/app.js#L1549) drops the answer when a different conversation becomes active. A changed scenario can also replace it with a notice. Prefer storing the answer on its original conversation and snapshot, with a clear earlier-state label, while leaving the current view alone. Keep checks for account changes and deleted records: a late response must not restore deleted content or persist another account's conversation after sign-out. Blocking all scenario interaction would unnecessarily constrain non-LLM exploration.

**9. Storage capacity and write amplification: agree with the problem, push back on “twenty questions.”**

[Submission already deduplicates identical snapshots](../app/static/app.js#L1535), ignoring capture time. Using the actual submission/snapshot functions with the Popov bundle and mocked DOM, storage, export, and model responses, I completed 39 questions with **one snapshot** and a 254,045-byte serialized store. This was a Node VM probe, not a browser quota test. The review's threshold therefore cannot be generalized to ordinary questions on an unchanged default scenario.

Different scenario states, forks, large answers, and different conversations can still duplicate substantial data and exhaust storage. Every keystroke still serializes the whole store. Deduplicate shared immutable source content, debounce writes, and provide useful capacity/recovery controls. Transactional storage can address this together with finding 7. A compact internal representation must still reconstruct complete portable exports without the original catalog; a bare external base-scenario reference would violate R15.

**10. BYOK lacks the shared deadline and provider-slot bound: agree, Medium.**

[BYOK construction](../app/llm/routing.py#L1075) omits the deadline, and [invocation](../app/llm/client.py#L94) bypasses the semaphore when no deadline is supplied. Give BYOK the same overall wall-time and concurrency protections as funded requests, including retries and advisory review. A shorter HTTP inactivity timeout alone is insufficient. Keep BYOK charging and credentials separate. Fake slow transports can verify this without paid calls.

**11. OpenRouter verification overstates the evidence: agree with the gap, qualify the proposed admission rule.**

The [catalog gate](../app/llm/catalog.py#L349) uses one `verified` flag for different kinds of evidence. Configuration and published availability do not prove successful live inference under our precise tools, decoding, and privacy filters. The guide already states that live backup conformance is unverified; repeating that caveat alone would not fix the flag's ambiguity.

Separate metadata/configuration confirmation, funded feature qualification, and live backup testing. This does not establish that the backups are broken. Requiring fresh paid OpenRouter inference before admission would introduce a condition incompatible with the existing CloudBank-only testing authorization unless Haoyang changes that authorization or accepts a different release boundary. Public metadata and mock request-contract checks can reduce uncertainty without spending, but cannot replace live evidence. Do not silently disable the qualified pool or declare unperformed tests successful.

**12. Gemini decoding differs across routes: agree, Medium. This includes a code correction.**

The [native payload](../app/llm/providers.py#L1025) explicitly sets temperature 0; the [OpenRouter payload](../app/llm/providers.py#L449) omits it. Preserve the already qualified setting in the backup, subject to the provider's supported parameter contract, and test both payloads. Do not remove the primary setting merely to obtain superficial symmetry and invalidate its qualification. Different thinking-field names are expected across adapters; equivalent intent needs checking, not identical JSON or identical answers. Tim's closing categorization of findings 11 through 13 as documentation/policy only is too broad for this item.

**13. Public credit can be granted again after deletion: agree with the behavior; the remedy is a policy choice.**

[Deletion removes the grant](../app/services/privacy_requests.py#L498), while [activation](../app/services/trials.py#L315) checks the current account and cumulative program counters. This weakens a one-lifetime-grant-per-person interpretation. It does not bypass the 100-grant/$500 public ceiling, and deletion is operator-mediated.

My preferred policy is no automatic repeat introductory grant, while allowing sign-in and self-funded use. Make that rule and any retained eligibility marker explicit. The existing unsalted, truncated email fingerprint is not automatically an adequate private anti-abuse identifier; known email addresses are guessable. Decide the identifier, retention, and eligibility semantics together. Named-entitlement retirement must remain intact regardless of this decision.

## Grouped Low findings

The positions below cover the individual concerns in Tim's six Low sections. An existing design choice can deserve improvement without being a newly introduced regression.

| Area | Position and recommended treatment |
| --- | --- |
| Stale context | Agree that reselecting must refresh the matching stale chip rather than leave a blocking duplicate. Whole-scenario invalidation is defensible because remote changes can alter an item's grounded status. Fix the recovery action and wording; do not silently keep outdated context. |
| Reference limit and forks | Agree on enforcing the 24-reference limit before submission. Preserve a forked question's reference identities, but revalidate them against the explicitly current scenario; missing or changed references need visible treatment. Blindly carrying old references forward is unsafe. |
| Empty conversations | Agree on avoiding repeated durable empty records. Reuse an unused draft or defer persistence until it contains something. This is small UX/storage cleanup. |
| Label highlighting and announcements | Agree that a non-motion changed-state cue and meaningful regression coverage would improve accessibility. Keep reduced-motion support. Full `aria-live` rebuilding is a plausible announcement problem, but actual screen-reader behavior was not demonstrated by this review; use incremental announcements and verify them with assistive technology. |
| Explain variant grouping | The union of variant attacks and the exact-edge-only renderer can misrepresent which derivation is attacked. The separate inspector does not automatically repair the discussion game. Build a custom-case reproduction before choosing the change. If it demonstrates a wrong causal explanation or label, I would treat that as Medium, despite being pre-existing, rather than mere presentation cleanup. |
| Explain premises and ID history | Agree on qualifying the contested-only premises list, or offering the complete derivation. Also agree that the 24-character limit predates this revision: R14 is satisfied by existing behavior, not a new change in this diff. No further limit increase follows from that observation. |
| MCP `llm:use` scope | Push back on treating this as an established authorization bypass. [ADR 0004](decisions/0004-authenticated-mcp-access.md#L77) explicitly grants `ask_project` and `propose_project_edit` to `llm:use`; these tools inherently use the owner's project content. Ownership is still checked. Clarify this read implication when issuing tokens, or deliberately change the scope dependency. Do not claim cross-owner disclosure. |
| MCP throttling | Agree on early throttling for unauthenticated transport requests and on sharing an account-wide LLM limit across HTTP/MCP, with per-tool limits if useful. Separate channel buckets do not violate the financial hard caps, but can exceed the intended aggregate request rate. Authentication, revocation, and trusted client-address handling must remain correct. |
| MCP/HTTP error text and conflict wording | Agree on typed safe user errors and generic messages for unexpected `ValueError`s. Returning every exception string is not a sound boundary, but a sensitive-data disclosure has not been demonstrated here. “Another editor or connected tool” would describe browser/MCP conflicts accurately. |
| Uncited quotations and prose labels | Agree that these remain semantic assurance limits. An uncited quotation may also be a legitimate rule description or heading, so rejecting every such quotation would create false failures. The engine still owns actual labels. I would not add a general natural-language truth checker or another LLM judge merely to eliminate tolerated minor imprecision. Keep provenance distinctions clear and target demonstrated material errors. |
| Reproducible evaluation cases | Agree: commit the two additional sensitivity case definitions, with any required sanitized fixtures, and explain how the 45-case release assessment relates to the committed 43-case suite. Preserve the original reports and hashes. Reproducibility does not require publishing raw transcripts or private operational receipts. |
| Model-specific context and guidance | Agree that the guide should say the extra accepted-defeater detail is supplied selectively, not uniformly. Require a concrete case reference for GLM's provenance override; the summary's field-omission evidence alone does not fully explain every added clause. Do not broaden all passing prompts solely for uniformity. DeepSeek guidance is not necessarily dead code: the internal evaluation route still supports withheld candidates. An empty directory is optional cleanup. |
| Evaluation environment | Agree on an explicit funded-variable allowlist and removal of personal API-key variables from inherited environment as well as `.env` copying. The current transport restriction limits the risk; the review has not shown personal-project spending. Preserve the ADC/Vertex variables actually required. |
| Stale holds and fixed-allocation mismatch | Agree that reconciliation only at startup creates an operational recovery gap. A periodic or operator-triggered sweep must preserve uncertain liabilities rather than release them blindly. Conversely, refusing a mismatched fixed allocation at boot protects the ledger. Keep that invariant and provide a controlled policy-migration path and clear diagnostic instead of silently changing allocations. |
| Charges for uncertain failures | The full conservative charge is an existing E06 budget-protection choice, not proof of incorrect arithmetic. Agree that users should see when an amount is provisional or conservatively assessed. Reconcile or credit verified differences later; simply assuming every failed call was free would make the funding caps unreliable. Any policy shifting uncertain costs away from the user needs explicit accounting for who bears them. |
| OpenRouter reported cost | **Disagree with “inert because no payload asks for cost.”** Current [OpenRouter usage-accounting documentation](https://openrouter.ai/docs/cookbook/administration/usage-accounting) says usage and cost are returned automatically; the old inclusion flags are deprecated. The adapter reads `usage.cost`, and the metering tests exercise provider-cost settlement. My parser probe also converted a supplied cost correctly. Live route-specific behavior remains unverified, but adding the deprecated flag is not the fix. |
| Circuit cleanup, provider names, accounting errors, metrics | Agree on releasing half-open probe state even when a `BaseException` escapes, without swallowing it; consistent provider identifiers; and the existing sanitized accounting-unavailable response instead of a bare 500. Metrics should retain useful visibility into known routes with outstanding/historical liabilities. None of these changes should weaken reservations or permit fallback after an accounting failure. |
| Anthropic BYOK endpoint | **Agree and raise to Medium.** With a dummy key and an `.invalid` environment URL, constructing the actual client inherited that URL. No request was sent. Pin the native Anthropic endpoint in the SDK branch itself; passing a router argument that the branch ignores is insufficient. This is a concrete violation of the fixed-endpoint contract and a credential-routing risk, not a demonstrated real-key leak. |
| Development compatibility and model metadata | The legacy direct-key path is a development-only exception, not a public admission bypass. Make that boundary explicit and prevent it from silently governing the shared service demo. Record/pin resolved GCP versions where supported; an alias alone does not prove the wrong model was served. A hidden duplicate profile should say the profile is unavailable rather than imply its qualified model failed evaluation. |
| Public operational identifiers and email lists | Agree on centralizing eligibility data and parameterizing unnecessary deployment-specific identifiers while preserving exact-target checks. These identifiers are not credentials. Hashing five guessable institutional emails is not substantial privacy protection by itself; publishing less unnecessary data is more useful. This does not justify secret rotation or rewriting historical receipts. |
| Base64 job payloads and writer draining | Base64 transports a reviewed script through job arguments; it is not itself a correctness defect or a secrecy mechanism. Keep readable source and payload hashes available for audit, as the release records already attempt to do. Agree that the drain prerequisite would be stronger as a machine-checked deployment gate, covering old replicas and jobs before activating transfers. A runbook requirement with receipts is evidence, but not automatic enforcement. |

## Evidence language and priorities

I agree that “manual review” was ambiguous. The accurate description is **answer-by-answer assessment by AI agents**, with explicit adjudications and preserved failures. This was not a human audit. Haoyang did request agent-driven evaluation, so the absence of a human reading all 1,080 answers is not a newly discovered unmet requirement. Clear attribution is necessary; a new human-review gate is not implied.

I push back on the statement that browser readback used “restored copies” of the MCP projects. The [restoration record](operations/hosted-native-verification-restoration-20260910.json) identifies zero new projects and the original two IDs. The inspected restoration code updates only `archived_at` on those project rows and checks that all other fields remain identical, including scenario content and version 3. The [browser receipt](operations/hosted-native-browser-readback-20260910.json) verifies those original IDs. These were the original persisted projects after unarchiving, not reconstructed replacements. The fair limitation is that this was a later verification phase after archival, not an uninterrupted native-edit-to-browser journey. The failed combined verifier and its uncertain cause remain unchanged.

I agree with the remaining evidence boundaries: private artifacts are unavailable from a fresh public clone; live OpenRouter conformance, the real administrator's OIDC sign-in, and the unperformed device/accessibility checks remain unverified. Tim's SQLite probes do not establish PostgreSQL locking behavior, though the earlier PostgreSQL CI evidence remains separate and valid within its documented scope.

For subsequent authorized correction work, I would prioritize:

1. Sign-in/credit separation and missing-configuration routing, followed closely by BYOK endpoint and deadline protections.
2. Wrong edit preservation, advisory-review degradation, inspector selection, and retaining paid answers on their original snapshots.
3. Conversation concurrency/capacity, evidence-role labeling, Gemini payload parity, and the concrete scope/throttling/error-boundary issues.
4. Verification terminology, committed sensitivity fixtures, precise AI-review attribution, and the public-credit deletion policy.

Most corrections can be established with deterministic or mocked-provider regressions. Prompt or model-input changes would still need the affected feature qualification under the original CloudBank budget; they should not trigger indiscriminate tuning or paid OpenRouter testing. The two-document brief should eventually incorporate accepted clarifications, while Tim's review and this response remain dated review records.
