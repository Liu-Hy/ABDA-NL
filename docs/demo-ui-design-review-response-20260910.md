**Response to Tim's UI design review, September 10, 2026**

This is the historical response before consolidation. The implemented decisions
and validation boundary are in the [contract](demo-revision-contract.md) and
[review guide](demo-revision-review-guide.md); the consolidated review supersedes
the earlier proposals discussed here.

I agree with the main diagnosis: the demo needs clearer task grouping, more
space for readable sentences, quieter visual styling, and easier access to
background and source material. Functional completeness does not resolve those
problems. I would implement a substantial portion of the review after
consolidation, with the amendments below.

My strongest pushbacks concern the proposed composer rewrite, removing formal
inspection from answers, calling the conclusion overview an argument graph,
and treating project restoration as a single-field update. These proposals can
change useful behavior or introduce correctness problems. They are not needed
to achieve the review's principal design goals.

This response covers [Tim's review](demo-ui-design-review-20260910.md) against
development commit `02c77dc`. I checked the implementation, relevant tests,
existing browser screenshots, and the extended abstract's “Using the Demo” and
“New Features” sections at paper commit `43f8bbb`. Three subagents independently
examined the explorer, chat/evidence, and authoring/account workflows. This was
source review with existing visual evidence, not a new browser acceptance run
or a measurement on the conference projector. Tim's viewport measurements
remain his observations.

The [requirements contract](demo-revision-contract.md) and
[review guide](demo-revision-review-guide.md) remain the acceptance entry
points. This file records review recommendations, not implemented changes.
Source line references below refer to the inspected commit.

The following table covers all 29 proposals and all 76 findings. “Amend” means
I accept the problem or direction but recommend changing the prescription.

| Proposal | Findings | Position and recommended disposition |
| --- | --- | --- |
| P01, scenario navigation | U01, U02, U03, U34 | **Amend.** Group examples and projects under the scenario name, with separate New, Import, Download, Sources, and Edit actions. Do not represent commands as listbox options. |
| P02, modified state and Reset | U07 | **Agree, with bounded Undo.** Disable Reset at baseline, retain the modified count, and leave the conversation intact. |
| P03, global actions | U04, U06, U09, U11, U33, U36 | **Amend.** Consolidate AI and account controls, keep Save directly actionable, and keep downloads available without sign-in. |
| P04, conclusion layout | U12, U13, U17, U19, U24 | **Amend.** Give sentences more space and group formal views. Preserve direct Inspect access, including absent conclusions. Choose panel proportions after prototyping. |
| P05, facts and rules | U05, U13, U14, U15, U16, U18 | **Amend.** Separate kind/state filters, label suspension visibly, reduce card decoration, and retain priority terminology rather than “wins.” |
| P06, explanation and derivations | U20, U21, U22, U23, U24, U26 | **Amend.** Skip unnecessary choices, explain the game roles, and improve focus/scrolling. Preserve distinct derivations and historical context. |
| P07, graph and dialogs | U25, U76 | **Amend; fix U76 promptly.** Improve labels and navigation, retain “Conclusion overview,” and make any filtering explicit. |
| P08, chat presentation | U27, U28, U29, U30, U31, U32 | **Amend.** Reduce routine chrome and show sentence-based references. Keep important storage errors and the fork's scenario choice visible. |
| P09, Sources reader | U03, U32, U58 | **Agree, with a source-integrity condition.** Make documents searchable and inspectable; verify that highlighted passages match the saved text. |
| P10, background and guidance | U10 | **Agree.** Show the scenario background with progressive disclosure. Suggestions must suit the current scenario. |
| P11, typography | U41, U42 | **Agree on legibility.** Increase reading sizes and establish a consistent scale. A particular font family is optional. |
| P12, colors | U44 | **Agree.** Reduce decorative category colors and preserve meaningful status labels. Verify contrast in the resulting design. |
| P13, surfaces and actions | U15, U43, U45, U46 | **Agree.** Use fewer shadows and clearer action hierarchy. Keep essential actions discoverable on touch and keyboard. |
| P14, status messages | U08 | **Amend.** Prevent overlays from covering controls. Use content-sized status regions and local errors, without timer-only recovery. |
| P15, inline token composer | U47 | **Push back for this redesign.** Improve explicit reference attachments while retaining free text. Reject the proposed automatic text/reference synchronization. |
| P16, editor entry states | U35, U48, U50, U57 | **Agree.** Distinguish creating, importing, and editing; avoid starting with unexplained validation errors. A sample and an importable starter can serve different purposes. |
| P17, readable identifiers | U49 | **Amend.** Suggest stable readable IDs once, and retain deliberate atomic renaming. Do not regenerate referenced IDs while typing. |
| P18, statement picker | U51 | **Agree, with precise semantics.** Add search and keyboard navigation; distinguish negative statements from rule undercuts. |
| P19, long scenarios | U52 | **Agree.** Filter and collapse rows, use meaningful rule summaries, and reveal rows containing validation errors. |
| P20, validation and saving | U37, U38, U53, U54, U55 | **Amend.** Put errors beside fields and explain the next action. Keep deterministic validation and explicit approval of model proposals. Show current rule wording during modification. |
| P21, import | U56 | **Amend.** Use content to suggest a file role, retain explicit overrides, and expose progress. Ambiguous prose must not silently become formal input. |
| P22, documents | U58 | **Agree.** Replace large textareas with a document list and reader. Report actual retained-text capacity; show only metadata the system knows. |
| P23, projects and sharing | U34, U59, U60, U61, U62 | **Amend.** List projects first, clarify Save a copy and share expiry, and add Restore with version, capacity, ownership, and sharing safeguards. |
| P24, submissions | U63, U64, U65, U66 | **Agree on the flow.** Put the public snapshot summary and consent together. Editable public metadata needs an explicit data contract. |
| P25, review queue | U67, U68 | **Agree.** Improve status visibility, review notes, and access to the published result. Counts and submitter information need authorized summaries. |
| P26, direct publication | U69, U70 | **Amend.** Use one clear, affirmative publication decision after consent. Do not add a second confirmation solely for symmetry. |
| P27, normal user view | U71, U72, U73 | **Agree.** Keep a compact persistent indicator with a real Restore button and an account-menu entry. Preserve the existing permission behavior. |
| P28, community provenance | U70 | **Agree.** Distinguish community examples and support explicitly optional public attribution. |
| P29, answer evidence | U32, U74, U75 | **Amend substantially.** Add source passages in context and a normal no-documents state; retain compact formal-context inspection independently of identifiers in prose. |
| Responsive design across proposals | U39, U40 | **Agree, but move earlier.** Design for laptop zoom and narrow widths throughout implementation. A phone tab bar can wait. |

**The main navigation should become simpler without hiding frequent tasks.**
For P01/P03, I recommend a scenario popover containing a selection area and
separate action buttons, an AI access control, a direct Save action with
secondary project actions, and an account menu. P03 currently specifies a Save
menu while decision 7 specifies a direct Save button; the consolidated design
should choose the latter. Exporting a scenario or conversation must remain
possible when signed out. Use “Save a copy” for shared read-only material.
Keep funded versus BYOK access apparent rather than displaying only a model
name.

A listbox selects values; its options cannot accessibly contain interactive
buttons or links. The scenario popover therefore needs distinct controls with
appropriate keyboard behavior. Moving focus through scenarios should not load
them or trigger the unsaved-change prompt. This follows the
[W3C listbox interaction guidance](https://www.w3.org/WAI/ARIA/apg/patterns/listbox/).
Nor is a one-row fit at 1024 px established by the mockup: test long project
names, larger fonts, access states, and normal user view. Wrapping itself is
acceptable when it preserves usable space and clear grouping.

**The visual direction is sound; the exact dimensions are hypotheses.**
P04 gives Conclusions 45% of the upper area, less than the current equal split,
so that number does not itself solve the width problem
([layout](../app/static/style.css#L192)). Reclaim the large status/action
columns first, allow controls below the sentence where needed, and preserve
the existing panel resizing. Larger text should not be paid for by hiding
sentences behind truncation or putting essential controls on hover only.
Keep `?`, Explain, and suspension easy to find. Pointer targets should meet
the applicable [WCAG target-size requirements](https://www.w3.org/WAI/WCAG22/Understanding/target-size-minimum.html),
with larger targets where practical.

I support fewer decorative colors, shadows, and repeated cards. “No identity”
is a subjective assessment, however, and switching to IBM Plex is not a
prerequisite for an elegant research demo. Prototype the hierarchy and type
scale first; add self-hosted fonts if they improve the actual result. The
proposed font size floor is a design preference, not a WCAG rule. Do not treat
the current hex palette as proof of color-vision accessibility, or freeze
exact colors if contrast testing identifies a problem. Local SVG icons do not
inherently require weakening CSP; a small, consistent set is reasonable.

**Reset and the dialog defect deserve early fixes independent of redesign.**
Reset currently invokes `resetChatConversation()`, which preserves the old
record but can create another conversation even for a nonempty draft
([Reset](../app/static/app.js#L485),
[conversation handling](../app/static/app.js#L1328)).
I agree that resetting scenario changes should preserve the active
conversation. Undo must restore only the captured scenario/baseline and remain
available until an incompatible transition, rather than depend solely on an
eight-second banner. Switching, saving, or making another edit must invalidate
an obsolete Undo instead of applying it to unrelated state.

U76 is a real defect: the graph opens the first global argument's inspector
while remaining visible; the equal backdrop z-index and DOM-based modal
selection leave visual and keyboard focus out of agreement
([graph action](../app/static/app.js#L2257),
[inspector](../app/static/exploration.js#L592),
[focus management](../app/static/workspace.js#L61)).
Use replacement navigation with a return to the previous graph view. Fix
modal ownership and focus handling without requiring a broad tabbed-dialog
rewrite first. Raising z-index alone is insufficient: underlying content
must be inert and closing the active dialog must restore appropriate focus,
as described by the [W3C modal pattern](https://www.w3.org/WAI/ARIA/apg/patterns/dialog-modal/).

**Formal explanations must retain their precise meaning while becoming easier
to read.** P05's “r1 wins” overstates a priority setting. Other attacks can
still defeat arguments using that rule. Keep “Prefer r1 / Equal priority /
Prefer rp,” alongside the rendered rule meanings
([priority controls](../app/static/app.js#L1175)). U16 concerns missing visible
explanation, not missing accessible names: the checkboxes already have
`aria-label` values. A visible “Active” label may be enough.

P06's single-candidate shortcut and role legend are useful. Different
derivations can share a top rule, so “via r1” alone cannot distinguish them;
retain the exact derivation identity and a concise distinguishing premise or
path. Auto-resolve only genuinely terminal branches, preserving cycle and
unresolved-child handling. The game explains a selected derivation; its
interface must not imply that clicking through moves assigns the conclusion's
computed label.

I support a more focused inspector and an optional shared Explain/Derivations
frame, provided Inspect remains directly reachable and absent conclusions
remain inspectable. Historical inspection already accepts a saved bundle,
whereas game helpers use the live global state
([inspector](../app/static/exploration.js#L585),
[game context](../app/static/app.js#L2403)). Combining these views requires
preserving that distinction, not merely moving markup.

P07 should use “Conclusion overview” or “Conclusion graph.” The graph merges
individual arguments by conclusion
([projection](../app/static/app.js#L1934)), as the paper explicitly describes.
Renaming it simply “Argument graph” weakens R13. Natural-language node labels
and navigation to that node's derivations are worthwhile. Keep the full set
available, and label any isolated-node filter and resulting counts. “No
displayed edge” is not equivalent to “unattacked”; projected edges and their
styles must not imply stronger formal claims than the underlying data.

**P15 should not replace the composer in the initial redesign.** The confusing
presentation in U47 is worth fixing, but editable prose and explicitly attached
context are different things. A user can select two rules and replace both
generated questions with “How do the two selected rules differ?” while keeping
both references. That is intentional behavior covered by an
[existing browser test](../tests/test_exploration_browser.py#L150).
Removing a reference because its quoted description disappears would break
this useful workflow. Removing an attachment should not silently delete the
user's prose either.

My recommendation is to keep the textarea and show a clearly labeled
“Referenced items” area with readable descriptions, explicit removal, and the
existing stale-state controls. Explain briefly that removing a reference
detaches its context and leaves the question editable. This is a concrete
solution, not an interim two-way synchronization mechanism.

An inline-token editor could be explored later, but the proposed click-to-
detach behavior is surprising, quoted-description matching cannot reliably
reconstruct historical tokens, and plain-text paste can lose reference
identity. It introduces selection, undo, composition, mobile, and persisted
draft migration work. Clean axe results would not establish correct editing
behavior. Independently, the current Enter-to-send handler has no
`isComposing` check
([handler](../app/static/app.js#L197)); add a focused IME regression and prevent
composition confirmation from submitting a question.

**P29 should separate source evidence from formal context, while preserving
both.** Tim correctly observes that selected formal references are not proof
that an answer is supported. Rename and simplify that area as “Formal context”
or “Referenced scenario items,” keeping access to the saved derivation and
computed labels. Make source passages the principal evidence cards, with the
quotation/context distinction and an accessible explanation that locating text
does not establish semantic support.

Do not rely on bracketed identifiers to replace formal inspection. The
qualified [chat prompt](../app/prompts/chat_system.md#L27) explicitly asks
models to avoid internal IDs unless the user names one. Good ordinary answers
therefore need not contain linkable IDs. Validated inline links can supplement
the retained controls, using the correct saved snapshot and unambiguous kind,
literal polarity, and argument identity. P08's retained formal buttons and
P29's removal also need reconciliation. There is no separate API
`formal_evidence` field: that is a local variable merged into `evidence`
([assembly](../app/llm/chat_service.py#L592)).

No-documents scenarios deserve a simple normal state. Prefer “No reference
documents attached. You can ask about this scenario's statements, rules, and
computed labels.” “Answers are grounded ... only” promises more than a
prompt can guarantee. Lack of a corpus should not remove useful formal
context; check both bundled references and attached sources. Likewise, keep
“Fork with current scenario” visible, not just in a
tooltip. A conversation is not guaranteed to concern one scenario:
[switching conversations](../app/static/exploration.js#L278) does not load their
scenario, and each turn intentionally preserves its own snapshot.

For U31, keep the default `?` question explanatory. Status-aware wording can
help, but replacing an assumption's explanation with a counterfactual changes
the task. Offer that as a separate editable suggestion, without sending or
applying anything automatically.

**The source reader is valuable, but P09/P29 overstate offset compatibility.**
Bundled PDF text for chat can come from `pdftotext -layout`; portable snapshots
use `pypdf` with different joining and normalization
([chat extraction](../app/llm/corpus.py#L38),
[export extraction](../app/scenario/portable.py#L29)).
Consequently, neither offsets nor an exact-quote fallback are guaranteed to
locate a supplied passage in the exported text.

Verify the slice against the saved document, convert code-point offsets for
JavaScript/DOM indexing, and accept a fallback match only when unambiguous.
Otherwise show the supplied excerpt and say that its location in the saved
document could not be confirmed. Never highlight an arbitrary duplicate or silently consult
the current project for an old answer. Reuse authorized snapshot/export paths
where possible, and clear private reader state on account changes. Source URLs
are citation metadata, not instructions to fetch arbitrary pages.
Aligning extraction would affect model inputs and deserves
separate qualification consideration. The reader and evidence navigation
should ship together as a usable feature, rather than leave “Open in Sources”
pointing to a future phase.

**Authoring should become clearer without making symbols a beginner's task.**
P16/P18/P19/P20 address real friction: empty drafts should explain the next
step, long lists need search, errors need field locations, and disabled Save
needs a reason. P17 should propose an ID once when creating an item and keep
it stable thereafter; preserve imported IDs. Later changes should use the
existing atomic rename, including negative literals and undercuts. Do not make an always-visible ID
field mandatory just to reduce `statement_1` labels elsewhere.
For reverting an editor draft, prefer “Discard editor changes”; projects do
not currently offer a browsable history of saved versions.

For P20, use an actionable “Check & save” while an unchecked draft exists:
run deterministic validation, save a valid manually authored draft when there
are no warnings, and show the preview with a final save decision when warnings
need acknowledgement. Errors never permit saving. Keep “Preview” available
separately. This is preferable to unexplained disabling, but “always enabled”
must not override authentication, read-only state, pending saves, version
conflicts, or invalid input. Resolve P20's inconsistency in favor of that flow,
without requiring another approval merely because a valid manual draft's
results have not been viewed. Preserve explicit preview/apply for model
proposals. Reuse the good impact-preview presentation through display-only
helpers, not live explorer controls bound to the open scenario.

Content-based import should suggest roles with a visible override; prose
containing arrows or equations is not necessarily a rule file. Retain server
validation and capacity limits. Document tables should distinguish extracted
text capacity from original upload size, and not invent unavailable page or
file-type metadata.

**Project restoration and public presentation need explicit data semantics.**
For P23, I agree that Archive should have a Restore path. However,
[archiving](../app/services/projects.py#L252) does not revoke share tokens, and
[share resolution](../app/services/projects.py#L394) excludes archived
projects. Merely clearing `archived_at` could revive old links. I recommend
restoring privately, invalidating the old share links, and requiring explicit
creation of new links. Preserve ownership, active-account checks, version
increments, concurrent-update protection, and the active-project limit.
Do not rename Archive to Delete while retaining the same stored-data behavior.

U63/U68 need a factual correction: the action buttons already occupy a separate
footer; consent and review notes are the controls below the long listing
([dialog](../app/static/index.html#L687)). Document text and raw JSON already
use collapsed disclosures by default
([rendering](../app/static/curation.js#L136)). Move the summary, consent, and
relevant note together near the decision, keeping the exact public payload
inspectable. For P26, one explicit Publish action after informed consent is
sufficient; an extra confirmation is not automatically safer. Keep an audit
record when removing one's own example without requiring a note to oneself.

P24/P25/P28 add more than styling: public title/description fields, queue
summaries, and attribution affect API/data behavior. Specify which fields
belong to the immutable published snapshot, keep private project metadata
private, and show the final public title and full-source disclosure before
consent. Shortening a catalog summary must not imply that the full downloadable
background was redacted. Preserve private reviewer notes, and account for the
existing one-submission-per-project-version rule when allowing metadata edits.
Attribution must be optional and must not expose an email by default.
Use actual publication dates and statuses tied to the submitted version;
publishing an earlier snapshot must not label newer private edits as public.
These additions can
be useful without becoming prerequisites for the core visual improvements.

For P27, the persistent “Normal user view · Restore” treatment is appropriate,
with Restore implemented as a keyboard-accessible button. Keep the account
entry and concise explanation of both removed privileges and preserved data.
Retain server-enforced normal permissions for both administrator groups.
Entering the mode need not alter credit, projects, history, or other browsers.

I recommend this implementation order after consolidation:

1. Fix U76, baseline Reset behavior, and the IME send risk. Preserve navigation,
   history, permission, and unsaved-work guarantees.
2. Improve typography, conclusion rows, toolbar organization, background
   visibility, status placement, and the administrator-mode indicator. Test
   laptop zoom and narrow layouts while choosing the design.
3. Deliver chat presentation and the Sources reader together, retaining formal
   context and the free-text composer.
4. Improve authoring, project discovery, consent, and review workflows. Include
   Restore with its sharing policy. Treat new public metadata as explicit,
   bounded functionality.
5. Refine the game and graph interactions. Consider a shared explanation frame,
   optional fonts, and richer editor experiments only when the simpler
   improvements have been assessed.

This reverses the review's emphasis on building the token composer before
legibility and deferring responsive behavior to the end. Set the conference
freeze from the actual rehearsal date, not an assumed three-week window.
Preserve the existing
[Chromium, Firefox, and WebKit acceptance matrix](../.github/workflows/ci.yml#L376).
Use targeted regressions during implementation and full browser/accessibility
checks at integration. Exercise long labels, zoom, keyboard focus, IME,
historical answers, no-documents scenarios, offline fonts, and both account
views. Automated checks complement the laptop/projector rehearsal.

Pure presentation changes do not justify new paid model evaluations. If
generated question templates or source extraction change, assess their actual
effect on model inputs rather than inheriting old qualification claims
automatically. Keep useful prompts unchanged unless behavior warrants tuning.
Update affected paper wording and demonstration captures after the final UI
settles.
