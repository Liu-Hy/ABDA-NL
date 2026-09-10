# ABDA-NL demo: UI design and aesthetics review, September 10, 2026

This is the consolidated review, merged with David's response of September 10
(`docs/demo-ui-design-review-response-20260910.md`). It covers the interface
of the demo as it stands after the September 10 revision, at development tip
`02c77dc`. It evaluates the browser interface
against general interaction-design practice and against the functionality
described in the extended COMMA 2026 abstract (`extended.tex`, branch
`extended-abstract` of the paper repository). It reports findings first and
then proposes a redesign. Nothing was implemented; this file is the only change
made to the repository.

Findings carry stable identifiers (U01 to U77) and the proposals carry stable
identifiers (P01 to P29) so that later work can reference them. Section 4.10
and section 6.11 are a focused review of the authoring, project, sharing, and
community-example flows, added on Haoyang's request; U47 and P15 cover the
question composer; U74, U75, and P29 cover evidence and scenarios without a
corpus; U76 is the unresponsive "Inspect derivations" button in the graph; U77 is the
Enter key sending a message during input-method composition.

## Status after consolidation

David read the review, checked the implementation, the tests, and the extended
abstract with three subagents, and wrote a response covering every finding
and proposal. He agrees with the diagnosis (task grouping, room for sentences,
quieter styling, access to background and sources) and objects to four
prescriptions: the token composer, removing formal inspection from answers,
renaming the conclusion overview, and restoring projects by clearing one
field. This section records what changed after checking each disputed point
in the code.

Every factual claim in the response was verified before it changed this
document:

- The browser test he cites (`tests/test_exploration_browser.py:140-160`)
  selects two rules, replaces the drafted prose with "How do the two selected
  rules differ?", and expects both references to be sent. The interim
  two-way sync I had proposed would have broken that workflow. Withdrawn.
- The chat prompt (`app/prompts/chat_system.md:27`) forbids identifiers in
  answers unless the user names one, so inline identifier links cannot carry
  formal navigation on their own. The formal part of the evidence area is
  retained in compact form (P29).
- Chat reads bundled PDFs through `pdftotext -layout` when available
  (`app/llm/corpus.py:38-62`), while the portable export used by conversation
  snapshots reads them with `pypdf` and different joining
  (`app/scenario/portable.py:29-35`). Offsets and even exact quotes are not
  guaranteed to locate a passage in the snapshot text. P09 and P29 now verify
  the slice and say when a location cannot be confirmed.
- Archiving a project sets `archived_at` and nothing else
  (`app/services/projects.py:252-266`); share resolution excludes archived
  projects (`app/services/projects.py:394-412`) but does not revoke their
  links. A Restore that only clears the field would revive old links. P23 now
  restores privately and revokes.
- The community-example dialog keeps its buttons in an always-visible footer
  (`index.html:707`); the consent checkbox is the control at the end of the
  scrolling body, and document text and raw JSON are collapsed by default
  (`curation.js:136-138`). U63 and U68 are restated accordingly.
- The Enter handler (`app.js:197-202`) has no `isComposing` check, so
  confirming an input-method composition sends the question. New finding U77.

Corrections accepted without reservation: the 45 percent figure in P04, the
"wins" wording in P05, the aria-label wording in U16, the "Argument graph"
name in P07, the eight-second Undo in P02, the regenerating identifiers in P17,
the "Revert to saved version" label in P16, the listbox-with-commands in P01,
the disabled downloads for signed-out users in P03, the extra confirmation in
P26, the counterfactual question template in P08, the tooltip-only fork label,
the "colorblind safe" claim in U44, and the icon remark in U46.

Positions held, with the amendments noted in the table: the token composer
(P15) remains the target because it is Haoyang's explicit request and because
one model for the draft is the root fix, but it moves behind the legibility
work and drops the interim sync; the Sources reader (P09) is built; evidence
cards lead and the formal part shrinks to one line rather than disappearing
(P29); the graph's toolbar button is removed in favor of clickable nodes
(P07); Reset needs no confirmation (P02); and the self-hosted font pair stays
a recommendation, decided at the prototype review rather than in advance.

### Disputed points and how they were resolved

| Topic | David's position | Resolution |
| --- | --- | --- |
| Scenario switcher (P01) | Commands cannot be listbox options; focus must not load a scenario | Accepted. A popover with a selection listbox and a separate row of action buttons; selection on activation only |
| Save control (P03, decision 7) | Direct Save with secondary actions; downloads and exports stay available signed out; show funding source | Accepted. A split button; Download and Export never disabled by sign-in state; the AI chip reads "Claude Sonnet 5 · funded" or "· own key" |
| Conclusions width (P04) | 45 percent is less than today; reclaim the status and action columns first | Accepted. Proportions are decided at prototype; resizing stays |
| Fonts (P11) | A font family is not a prerequisite; prototype the scale first | Held as a recommendation, decided at the prototype review with both options side by side |
| Status palette (U44, P12) | The palette is not proof of color-vision accessibility | Accepted. Verify contrast and simulate deficiencies during implementation |
| Reset Undo (P02) | Undo must not depend on a timer and must be invalidated by incompatible transitions | Accepted. Undo stays until the next state change, switch, or save |
| Dialog stacking (U76, P07) | Raising z-index alone is insufficient; the underlying dialog must be inert and focus restored | Accepted and folded into the stacking fix |
| Conflicts wording (P05) | "r1 wins" overstates a priority | Accepted. "Prefer r1 / Equal priority / Prefer rp" |
| Explain candidates (P06) | "via r1" cannot distinguish derivations sharing a top rule; auto-resolve only terminal branches; keep Inspect direct; the shared frame must scope to the right bundle | Accepted on all four points |
| Graph name (P07) | "Argument graph" weakens R13; the view is a projection by conclusion | Accepted. "Conclusion graph" on the button and the dialog; the isolated-node filter says "without displayed attacks" |
| Composer (P15) | Prose and attached context are different things; the interim sync breaks a tested workflow; click-to-detach is surprising; forks cannot be rebuilt from quotes; paste loses identity | Held with amendments. Interim sync withdrawn; the segment model is stored with each message so forks are exact; click-to-unwrap kept at Haoyang's request with a visible affordance and Undo; paste is plain text by design; phased after legibility; a "Referenced items" relabel ships first |
| Formal context in answers (P29) | Keep compact formal inspection; identifiers rarely appear in answers; there is no separate API field | Amended. Source cards lead; one compact "Referenced items" line with the selected items is retained; inline links are a supplement; wording about the API corrected |
| Evidence offsets (P09, P29) | Chat and export extract PDFs differently; offsets and quotes may not locate the passage | Accepted. Verify the slice, convert code-point offsets, accept only unambiguous matches, otherwise say the location is unconfirmed; reader and cards ship together |
| Question templates (P08, U31) | Keep "?" explanatory; a counterfactual changes the task; template changes alter model inputs | Accepted. Explanatory templates only, with an assessment of their effect on model inputs before they ship |
| Fork label (P08) | The scenario choice must be visible, not a tooltip | Accepted. "Fork with current scenario" |
| Conversations and scenarios (P08) | A conversation is not bound to one scenario | Accepted. The rationale is corrected; today's switch behavior is kept without that claim |
| Identifiers (P17) | Propose once, keep stable, preserve imported ids, do not force an always-visible field | Accepted |
| Save gate (P20) | "Check & save"; no extra approval merely because results were not viewed; never override auth, read-only, pending, conflict, or invalid states | Accepted |
| Import and documents (P21, P22) | Suggest roles, never silently decide for prose; show only known metadata | Accepted |
| Restore (P23) | Clearing `archived_at` revives share links; do not relabel Archive as Delete | Accepted. Restore privately and revoke links; the fallback is a note about the privacy request, not a relabel |
| Submission dialog (U63, U68) | The buttons are in a footer; disclosures are collapsed | Accepted. The problem is restated: the visible primary button is disabled and its enabling control is out of view |
| Direct publication (P26) | One informed affirmation is enough; do not add a confirmation for symmetry | Accepted. Both paths keep one affirmation; the native confirm is replaced by an in-dialog bar for styling only |
| Public metadata, counts, attribution (P24, P25, P28) | These change data behavior and need explicit contracts | Accepted. Specified as bounded additions with the fields named |
| Implementation order | Fix defects first, legibility before the composer, reader with the chat phase, responsive throughout, freeze from the rehearsal date | Adopted, with the composer kept as its own phase rather than deferred indefinitely |
| Storage errors (P08) | Keep storage failures visible | Accepted. Only the routine note moves to a tooltip |
| Empty-state suggestions (P10) | Must suit the current scenario | Accepted. Generated from the loaded scenario |

## 1. Verdict

The demo is functionally complete, consistent with the abstract, and already
careful about accessibility, honesty of copy, and safety of model output. Its
weaknesses are structural rather than cosmetic. The interface exposes how the
application is built (one modal per subsystem, one button per feature) instead
of how a user thinks about the work (choose a case, read it, understand a
conclusion, try a change, ask a question, keep the result). Five problems
account for most of the friction a first-time user feels:

1. **The top bar is a flat list of eleven same-weight controls that mix six
   unrelated concerns.** Scenario source, reading aids, what-if state, model
   access, account and projects, and legal links sit side by side with no
   grouping, and several labels do not match the dialog they open. It wraps to
   two rows at widths of 1100 pixels and below, which includes a 1440-pixel
   display at 125 percent zoom (U01 to U11).
2. **The most important panel gets the least room.** Conclusions are the
   dashboard the abstract describes, yet each label receives about 250 pixels
   at 1440 wide and 80 to 90 pixels at 1024 wide, where labels wrap onto four
   to six lines. A fixed 88-pixel status block and a three-button action group
   take the rest (U12, U13).
3. **Names are inconsistent across buttons, dialog titles, and states.** "New /
   Open" opens "Your scenario"; "Sources & glossary" becomes "Edit scenario";
   "View Graph" opens "Conclusion overview"; "Workspace" opens "Research
   workspace"; "Inspect" means four different things (U01, U26).
4. **Several behaviors surprise, and one is a defect.** Reset silently starts
   a new chat conversation even when nothing was changed; the only way to
   read a cited source document is to download the scenario; toasts cover the
   buttons the user just clicked; the scenario background paragraph is never
   shown in the explorer; "Inspect derivations" in the graph dialog opens its
   dialog behind the graph, so it appears not to respond; and Enter sends a
   question while an input-method composition is being confirmed (U07, U03,
   U08, U10, U76, U77).
5. **The visual system is competent but undifferentiated and too small.**
   Every list item is a bordered, shadowed card; most text is between 9 and
   13 pixels; there are seven color families in use; the type is the system
   default. It reads as a capable internal tool, not as the public face of a
   research contribution (U41 to U45).
6. **The authoring and curation flows are complete but built for small
   scenarios and patient users.** The guided editor scales badly past twenty
   statements (native selects with about 150 options, a flat list of cards,
   positional rule numbers, auto-generated ids that leak into the explorer);
   the save gate is unexplained; the community-example dialog hides its
   consent checkbox and primary button below a listing of every rule; and the
   administrator's normal-user view wraps the top bar on a 1440-pixel display
   (U48 to U73).

None of these require changing what the demo can do. Section 6 proposes a
redesign that keeps every feature and every requirement in the contract,
including the verbatim "Chat & Exploration" heading required by R14.

### Answers to Haoyang's questions

**Does "Sources & glossary" provide value, or should it be removed?** Remove it
from the top bar. For bundled and community examples the dialog shows a
read-only text box of `symbol = "meaning"` lines (information already visible
on every card and in Show ASPIC-) and a list of reference document filenames
without their text. For a private project the same button changes its label to
"Edit scenario" and opens the full editor, which is a different task. The one
thing users actually lack in this area is a way to read the documents that the
chat cites by filename and character offset. Section 6.6 specifies a Sources
reader that gives the concept real value, and decision 2 in section 7 schedules
it as the last phase; glossary editing already lives in the editor and stays
there.

**Should "Download current scenario" stay inside "New / Open"?** Move it.
Downloading is an act of keeping or sharing the current work, not of starting a
new scenario, and it currently sits in the footer of a dialog titled "Your
scenario" next to Cancel and "Save & open". Put "Download scenario (.json)" in
the scenario menu proposed in section 6.2 and in the Save menu, remove it from
the editor footer, and move the chat's "Export" into the conversation menu.
The footer placement is also misleading: the button exports the current
exploration (`scenarios.js:703-719`), not the draft being edited, while its
hint "Includes unsaved edits" reads as if it did. Section 6.2 shows the
arrangement.

**What should "Inspect evidence" show?** Corpus spans in context first. The
formal entries in that list are the items the user selected with "?",
rendered as buttons that open the derivation inspector, which is the same view
as Inspect in the Conclusions panel and the most complex screen in the
product. Their presence under an answer duplicates Explain and Inspect and
buries the source quotations, which are the evidence a reader wants. P29
makes source cards the evidence: each quotation inside its surrounding
paragraph, highlighted when the passage can be located in the saved document
text, with "Open in Sources" for the full document. The formal part shrinks
to one line, "Referenced items", showing the selected items as the same chips
the question uses; it stays because the chat prompt keeps identifiers out of
answers, so there is no other place from which a reader can reach the saved
derivation of an item the question was about.

**Does the demo work without a corpus?** Yes, and it should say so. The
schema requires only a title, conclusions, and rules; reference documents are
optional in the editor and in imports. Every deterministic feature and the
editing features are independent of documents. Chat works too: the backend
tells the model that no documents are attached and not to invent citations
(`app/llm/corpus.py`, the no-documents branch of `build_corpus_block`), and
the evidence checker then produces no source items. The interface, however,
never mentions the absence. U75 lists each feature's behavior and P29 adds
the one line the panel needs, worded as a description of what can be asked
rather than a guarantee about answers. Live model behavior without documents was not
exercised in this review; the prompt text is the evidence.

## 2. What was reviewed and how

- **Code.** `app/static/index.html`, `style.css`, `app.js`, `workspace.js`,
  `exploration.js`, `conversation-storage.js`, `scenarios.js`, `materials.js`,
  `curation.js`, and the policy pages, all at `02c77dc`.
- **Running interface.** The local demo served by the `demo` launcher on
  dt-login03 (signed-out states, all dialogs, all filters, an assumption toggle
  and reset, six viewport widths from 390 to 1440 pixels). Signed-in, trial,
  private-project, share-link, editor, and administrator-review states were
  captured on a throwaway instance started the way the browser tests start
  theirs, with a temporary database, no provider credentials, and the stub
  model backend. That instance was stopped afterwards. The demo's own database
  was not touched.
- **No model call was made.** To review the layout of a chat answer with
  evidence, a sample answer was injected into the page state; its text is not
  a claim about model behavior.
- **Measurements.** Control counts, computed font sizes, and label widths were
  read from the DOM with Playwright (Appendix A). WebKit cannot launch on this
  host, so all captures are Chromium; the CSS is not engine specific.
- **Reference for intent.** The extended abstract's sections "Using the Demo"
  and "New Features Since the Camera-Ready Version", and R01 to R16 in
  `docs/demo-revision-contract.md`.

Screenshots taken during this review live in the session scratchpad and can be
regenerated with the scripts kept there; they are not committed. Every finding
below cites the code or the measurement that supports it, so the document stands
without the images.

## 3. The user's conceptual groups and where the interface puts them

The abstract describes the demo as one working surface with a small number of
activities. The table lists those activities, in the order a newcomer meets
them, and where the current interface places the corresponding controls.

| Activity (user's view) | What the abstract promises | Where the controls are today |
| --- | --- | --- |
| Choose a case to look at | Six bundled scenarios, community examples, private projects | Top bar select; "New / Open" dialog (New, Import, "My projects" button that closes it and opens "Research workspace > Projects"); Workspace > Projects |
| Understand what the case is about | Scenario title, background, glossary, source documents | Title only (top bar). Background is never shown in the explorer. Glossary is inline on every card. Documents are listed by filename in "Sources & glossary" without their text |
| Read conclusions, facts, rules | Four panels, labels, identifiers, filters | Three left panels; filters mix type and state; category grouping controlled by "Compact" in the top bar |
| Understand why a conclusion holds | Explain (discussion game), Inspect (derivation) | Two buttons per conclusion card; Inspect also on rule cards; the graph modal has a third entry point |
| See the formal framework | View Graph, Show ASPIC- | "View Graph" in the Conclusions header; "Show ASPIC-" in the top bar |
| Try a what-if change | Suspend toggles, Conflicts preferences, modified count, Reset | Checkboxes on cards; "Conflicts" tab in Rules; count chip in the brand line; "Reset" in the top bar |
| Ask a question | Chat, "?" drafting, evidence, conversations | Right panel with two chips, a toolbar, two notes, and per-turn controls |
| Author with model help | + Fact, + Assumption, + New Rule, Modify | Blue buttons inside two panels; "Modify" on every rule card |
| Keep, share, publish, export | Save, share link, suggest example, download | "Save project" (top bar); share and suggest in Workspace > Projects; download in the editor footer; conversation export in the chat toolbar |
| Manage access | Sign in, trial credit, model choice, own key, agent tokens, admin view | "Workspace" and "AI: model" in the top bar; a chip in the chat header; "Restore administrator view" button in the top bar |

Two things stand out. First, the same activity is often split across two
places with different names (opening a project, exporting, formal views, model
access). Second, activities that belong together for the user (choose a case,
learn what it is about, export it) are separated, while unrelated ones (a view
toggle, legal links, the reset of a what-if change) share one row.

## 4. Findings

Severity: **High** blocks or misleads a first-time user; **Medium** costs time
or confidence; **Low** is polish. Code references use `file:line` at `02c77dc`.

### 4.1 Top bar and global controls

**U01. High. The top bar has no structure and wraps early.** Eleven controls
share one row (`index.html:26-46`): the scenario select (272 px wide), New /
Open, Sources & glossary, the Compact switch, Show ASPIC-, Reset, the AI chip,
Workspace, Save project, Privacy, and Terms, plus a "Restore administrator
view" button for administrators in normal-user view. All use the same outlined
button style except Save (filled) and the AI chip (tinted). Content width is
about 1290 px, so the policy links wrap at 1280, the row splits in two at 1100
and below, and in three at 780. A 1440 display at 125 percent browser zoom
behaves like 1152 px, so the wrapped state is what a projector audience will
likely see. Six concerns are interleaved with no separators: scenario source,
reading aids, what-if state, model access, account and projects, legal.

**U02. Medium. The scenario name is shown twice, and the breadcrumb is a
leftover.** The brand line shows `ABDA-NL > Popov v. Hayashi [Example]`
(`index.html:15-25`) and the select right below shows "Popov v. Hayashi"
again. In project state both repeat "Popov v. Hayashi exploration", once with a
"Private project" chip and once with a "Project:" prefix
(`app.js:297-333`, `348-378`). The ">" separator has one level and nothing to
separate.

**U03. Medium. "Sources & glossary" has almost no content for examples and
changes function for projects.** For an example the dialog shows a read-only
textarea of glossary lines and the sentence "Bundled references: <filenames>.
These stay linked to the original example." followed by "No uploaded reference
documents." (`materials.js:181-204`). The text of the bundled documents, which
are the ones every example cites, is not viewable anywhere in the interface;
only documents uploaded to a private project are shown. Chat answers cite
documents by filename and character range (`exploration.js:531`). For a private project the button is relabeled
"Edit scenario" (`materials.js:132`) and opens the editor, a different task in
the same slot.

**U04. Medium. Three exports in three places with three names.** "Download
current scenario" lives in the footer of the "Your scenario" dialog
(`index.html:558-560`) next to Cancel, Preview, and Save & open, with the hint
"Includes unsaved edits. No chat or credentials." The chat toolbar has "Export"
(`index.html:128`), and each question has "Download scenario snapshot"
(`exploration.js:364-368`). A user who wants "a file of what I have" has to
know which dialog contains it.

**U05. Medium. "Compact" is a panel view option placed in the global bar, and
its label does not say what it does.** It switches the Facts and Rules lists
between category badges on each card and category headers between groups
(`app.js:966-971`, `884-898`, `1051-1063`). It is on by default. Nothing in the
label mentions categories, and it has no effect on Conclusions or Chat.

**U06. Medium. Two chips for the same setting, and one of them breaks the chat
heading.** "AI: Claude Sonnet 5" (top bar) and "Funded: Claude Sonnet 5" (chat
header) both open Workspace > AI access (`workspace.js:148-149`, labels at
`700-715`). The chat chip is wide enough to wrap "CHAT & EXPLORATION" onto two
lines at 1440 px.

**U07. High. Reset has surprising side effects and no confirmation.** The
button is enabled even when nothing is modified (`app.js:373-374` only disables
it for shared views). Clicking it re-posts the baseline state and then calls
`resetChatConversation()` (`app.js:494`), which starts a new conversation record
whenever the current one has any message (`app.js:1328-1347`). The user's
visible thread disappears from the panel and survives only as an entry in the
conversation select. This happens even with zero changes, so an idle click on
Reset archives the conversation. Switching examples has the same effect, which
is more defensible, but Reset is a return to the same scenario.

**U08. Medium. Toasts cover the controls the user just used.** Global status
messages are fixed at the top right, 4.2 rem down, 420 px wide, for 6 seconds
(9 for errors) (`style.css:79-91`, `workspace.js:22-33`). At 1440 px that
rectangle covers the AI chip, Workspace, and Save. Clicking "Save project" while
signed out produces a toast that hides the button that was clicked; signing in
produces one that hides the same three controls.

**U09. Low. Privacy and Terms sit among action buttons at 11 px.** They belong
in the account area or a footer (`index.html:42-45`, `style.css:101-103`).

**U10. High. The scenario's background text is never shown to a reader.** Every
bundled scenario has a `description` (for Popov, a paragraph that explains the
case, the encoding, and the optional equity extension). It appears only in the
editor's collapsed "Background" details and in the "Suggest as example" review
(`scenarios.js:293`, `curation.js:133`). A newcomer opening Popov sees eight
conclusions with no context.

**U11. Low. The Save button changes its label with the view kind and, when
signed out, is a sign-in prompt.** "Save project" for examples, "Save changes"
for projects (`app.js:376`); signed out, it opens the Account tab with a toast
(`workspace.js:880-891`). Acceptable, but a primary-styled button whose most
likely first outcome is "sign in" sets the wrong expectation.

### 4.2 Explorer panels

**U12. High. Conclusions get the least space and their labels wrap badly at
common widths.** The left panel is 75 percent of the window and the top row is
split evenly between Conclusions and Facts (`style.css:175-231`). Each
conclusion card spends 88 px on the status block (`style.css:260-270`, width
5.5 rem) and about 170 px on Explain, Inspect, and "?". Measured label width
and line count of the eight key conclusions:

| Viewport | Label width | Lines per label |
| --- | --- | --- |
| 1440 x 900 | 251 px | 2 |
| 1366 x 768 | 223 px | 2 |
| 1280 x 800 | 191 px | 2 to 3 |
| 1024 x 768 | 80 to 90 px | 4 to 6 |

The top row is also only 35 percent of the height (`style.css:182-186`), so
about four of eight key conclusions are visible without scrolling at 1440 x
900. The abstract calls this panel the dashboard; the layout treats it as one
of three equal lists.

**U13. Medium. Too many controls per item.** At first load there are 125
visible interactive controls with 48 distinct button labels (Appendix A). Each
conclusion card has Explain, Inspect, and "?"; each rule card has Inspect, "?",
Modify, and a checkbox plus a category badge; each fact has an id link, "?",
and (for assumptions) a checkbox. On fact cards the bracketed id is the link
that opens the inspector (`app.js:976`), while rule cards use a separate
"Inspect" button (`app.js:1295`) and render the id as plain text. The "?" is a
requirement (R10) and must stay clickable; the rest is negotiable.

**U14. Medium. Filter groups mix kind and state.** Facts & Assumptions offers
"Facts | Assumptions | Modified | Suspended" as one exclusive group
(`index.html:79-87`), so "modified assumptions" cannot be expressed and
choosing "Modified" drops the kind distinction. Rules offers "All Rules |
Conflicts | Modified | Suspended", where Conflicts is a different view (the
preference editor, `app.js:1140-1213`) presented as a sibling filter.
Conclusions' "Key | Accepted | Rejected | Undecided | Absent | All" is sound,
but nothing explains that "All" adds intermediate propositions.

**U15. Medium. Visual noise inside lists.** Every fact, assumption, and rule is
a bordered card with a drop shadow (`style.css:310-319`, `664-673`), carrying a
9.3 px uppercase category badge in one of twelve tints (`style.css:606-617`,
`app.js:922-935`), a 10.6 px monospace id in brackets, bold uppercase
connectives "IF", "AND", "THEN NORMALLY" in every rule (`style.css:423-428`),
and for changed items a violet left bar. Thirty-eight rules of two lines each
produce a wall of identical rectangles in which the actual sentences are the
lowest-contrast element.

**U16. Medium. The active toggle has no visible label.** The right-most
checkbox on assumptions and defeasible rules means "active"; it has an
accessible name (`aria-label="Suspend assumption ..."`, `app.js:989`, `1282`)
but its visible meaning is carried only by a tooltip ("Active -- uncheck to
deactivate"). Suspended items switch to a dashed border and gray fill. The impact
preview that follows a click is excellent and should stay.

**U17. Low. "Absent" needs one more word.** The dashed card labeled ABSENT with
a disabled Explain button explains itself only through a tooltip
(`app.js:805-809`). "Not derivable" or "No argument" would read without hover.

**U18. Low. The Conflicts view is a distinctive feature filed as a filter.** The
preference radios "[r1] stronger | Same strength | [rp] stronger" use ids where
short words would do, and the view is discoverable only by trying the tab.

**U19. Medium. The two formal views are split.** "View Graph" is attached to
the Conclusions header (`index.html:61`) while "Show ASPIC-" is in the top bar
(`index.html:36`). They are the same family ("Inspect the framework" in the
abstract) and should sit together.

### 4.3 Explain dialog

**U20. Medium. The picker step is shown even when there is one candidate, and
candidates are named by internal ids.** `renderArgumentPicker` always renders a
list (`app.js:3224-3259`); for accepted conclusions in Popov this is often a
single card titled by the rule text with the caption "Derivation a5"
(`app.js:3272`). A newcomer cannot use "a5" to choose, and a one-item choice is
an extra click.

**U21. Medium. The "Continue" button is a dead end that must be pressed.** When
a claim has no challenges, the moves panel says "NO CHALLENGES AVAILABLE. This
claim has no remaining challenges. It is accepted." followed by a "Continue"
button (`app.js:3690-3694`, `3730-3734`). Pressing it only adds the Accepted
badge and switches the panel to "Exploration complete". The dialog could resolve
such leaves itself, as it already does for off-path nodes
(`app.js:3335-3353`).

**U22. Low. The game vocabulary has no legend.** "Has to be the case:", "Can be
the case that:", "Contested premises and subarguments", "Challenge this claim",
"Defend against this challenge", and "Other open branches" are faithful to the
grounded discussion game and right for the COMMA audience, but the dialog
never says which side is speaking. One line ("Blue-gray cards are the
proponent's claims, brown cards are the opponent's challenges") would carry it.
The two bar colors (`style.css:1854-1858`) are not part of the status palette,
which is fine, but it should be said.

**U23. Low. Dialog size.** 75 vw and up to 85 vh with an internal scroll and a
sticky "Back to arguments" toolbar (`style.css:1218`, `467-477`) works. On
tall trees the focused node can sit below the fold after a move; scrolling the
new focus into view would help.

### 4.4 Derivation inspector and graph

**U24. Medium. The inspector is a formal listing presented like a user dialog.**
It shows the element card twice (once at the top, again as "Applied top rule",
`exploration.js:622-629`), a select with all 77 derivations labeled "a8: ...
[r1; Rejected]" (`exploration.js:625`), and sections for premises, 31
subarguments, rules used, incoming and outgoing attacks, and "Other derivations
of this exact conclusion". This is the right content for R13 and for experts; it
should look like a formal detail view (monospace, denser, a distinct header) so
that newcomers understand it is optional.

**U25. Medium. The graph labels nodes with identifiers and handles the "All"
scope poorly.** Node text is the literal (`popov_has_poss`, `✕ rp`)
(`app.js:2184-2189`); natural language appears only in a hover tooltip. With
"All conclusions" the fit logic scales the drawing to 29 percent and draws
about thirty isolated single-node "groups" in one row under the connected part
(`app.js:2011-2024` exempts declared propositions from pruning; `2312-2329`
computes the fit). The legend has seven entries and distinguishes mutual from
preference-decided rebuts by a filled versus hollow arrowhead
(`app.js:2204-2215`), which is hard to see at 80 percent. The button says "View
Graph"; the dialog says "Conclusion overview"; "Inspect derivations" in the
toolbar opens the inspector at the first argument of the whole framework
(`app.js:2257`), an arbitrary choice.

**U26. Low. "Inspect" means four things.** A conclusion's derivation
(`app.js:819`), a rule's derivations (`app.js:1295`), the chat's evidence
disclosure "Inspect evidence (4)" (`exploration.js:519`), and the graph's
"Inspect derivations".

**U76. High (defect). "Inspect derivations" in the graph dialog opens the
inspector behind the graph.** The button calls `openDerivationInspector` for
the first argument in the framework (`app.js:2257`), which renders the
inspector and opens `#modal-derivation` (`exploration.js:592-597`) while
`#modal-af` stays open. Both backdrops are `position: fixed` with `z-index:
100` (`style.css:1204-1210`), so their paint order is document order, and the
derivation dialog is the first modal in the page (`index.html:147`) while the
graph dialog is later (`index.html:421`). The graph therefore paints on top:
the user sees only the page behind the graph darken by a second backdrop,
keyboard focus moves into the hidden dialog's select, and Escape closes the
graph first (the key handler takes the last visible backdrop in document
order, `workspace.js:61-69`) and only then reveals the inspector. Reproduced on
the running demo: after the click both dialogs report visible, the element at
the screen center belongs to the graph dialog, the active element is
`derivation-argument-select`, and one Escape leaves the inspector open alone.
The same hazard applies to any dialog opened while a later-in-document dialog
is visible; today the graph is the only such path. The button's target is also
arbitrary (argument `a1`, whatever it is), and graph nodes themselves are not
clickable (`style.css:1699-1701`), so there is no way to inspect the node the
user is looking at.

### 4.5 Chat and exploration

**U27. Medium. Three notes precede the first message.** The yellow access note
("Sign in with a verified email to use language models. Open settings"), the
storage note ("Saved automatically in this browser for your account. Delete
removes this conversation from this device.", `exploration.js:255-258`), and,
on failure, the degraded note. Together with the two-line heading and the
toolbar, about 170 px of the panel is chrome before content.

**U28. Medium. The conversation toolbar reads as commands.** A native select
whose first option is the record title "New conversation"
(`exploration.js:108`) sits next to a "New" button; a title that looks like a
command is confusing, and once a user has ten conversations a native select
shows only truncated first questions with no dates or scenario names. Export
and Delete are always visible; Export is disabled when empty, Delete is enabled
for an empty record (`exploration.js:262`, `289-292`).

**U29. Medium. Per-turn controls are heavy.** Under every question: a
"Scenario used for this question" disclosure with a sentence and a "Download
scenario snapshot" button, plus "Edit and fork with current scenario"
(`exploration.js:352-380`). In a 350 px panel these add about 60 px per turn.
The labels are precise, which R11 asks for; the presentation can be lighter.

**U30. Medium. Context chips show kind and id, not the sentence.** A chip reads
"conclusion hayashi_no_return"; the human description is only a hover title
(`exploration.js:487-489`). After a scenario change chips become
"(earlier scenario)" with a "Refresh" button, and after switching to another
example "(no longer present)". Correct behavior, opaque wording.

**U31. Low. The generated question is the same for every kind.** `Can you
explain "<description>"?` (`exploration.js:462`) for a rejected conclusion, an
assumption, and a strict rule alike. R10 requires the same generated question
to be inserted, but the template may vary by kind as long as it stays
explanatory (for example "Why is <conclusion> rejected?"); a template that
turns an explanation into a counterfactual changes the task, and any template
change alters model inputs and needs assessment before it ships.

**U32. Medium. Evidence is honest but hard to consume, and sources cannot be
opened.** Each item carries a two-sentence role statement ("Quotation matched to
this supplied source span. This verifies the wording, not the claim.") and a
range "characters 8120 to 8204" (`exploration.js:524-534`). There is no way to
open the document at that range. The honesty is right (R12); the form is for
auditors.

**U47. High. The drafted question and its context chip are two unlinked
copies of the same thing.** Clicking "?" inserts the sentence `Can you explain
"<description>"?` into the textarea and, separately, pushes a reference that
renders as a chip above it (`exploration.js:440-478`, chips at `480-511`).
Nothing links them afterwards: removing the chip leaves the sentence
(`exploration.js:507` splices the reference only), deleting the sentence leaves
the chip, and the draft record stores them as two fields (`saveConversationDraft`,
`exploration.js:116-130`). On submission the text comes from the textarea and
the identities from the chips (`app.js:1514-1555`), so a user who deletes the
sentence but not the chip sends the item as context with an unrelated question,
and a user who removes the chip but keeps the sentence sends the sentence
without the identity that R10 exists to preserve. A first-time user reads the
two copies as a display bug. The fix, and the design that should replace the
chip strip, is P15.

**U74. High. The evidence disclosure mixes corpus evidence with formal
navigation, and the formal part is the wrong tool.** "Inspect evidence (n)"
lists two kinds of items (`exploration.js:513-551`). Source items are right in
substance: a quotation matched to the supplied text or a contextual excerpt,
each with its filename and character range. Formal items are the rules,
arguments, and conclusions the user selected with "?" for that question
(`app/llm/chat_service.py:591-593`), rendered as "Inspect rule rh" buttons that
open the derivation inspector against the saved snapshot
(`exploration.js:540-545`): the element card, a select of every derivation in
the scenario (77 for Popov), the applied top rule, direct premises, all proper
subarguments, all rules used, incoming and outgoing attacks, and other
derivations of the same conclusion (`exploration.js:611-645`). That view
duplicates Inspect in the Conclusions panel and overlaps with Explain, and it
is the most complex screen in the product. Under a chat answer it reads as
"complicated lists of ASPIC- elements" and hides the quotations. Evidence for
an answer should be the source spans, shown in context; the items the question
referred to should be one compact line, not a list of inspector launchers.
The API carries these items inside the `evidence` array (kinds `rule`,
`argument`, `conclusion`), not as a separate field.

**U75. Medium. Reference documents are optional, and the interface never says
when a scenario has none.** The schema requires title, conclusions, and rules
only (`app/schemas/scenario.schema.json:7`); documents are an optional section
in the editor and an optional role in imports. Behavior without documents, from
the code:

| Feature | Without documents |
| --- | --- |
| Explorer, Explain, Inspect, graph, ASPIC- text, toggles, Conflicts, Reset | Unaffected |
| Add or modify with model help | Unaffected; documents are context only |
| Chat | The prompt states that no documents are attached and forbids invented citations (`app/llm/corpus.py`, `build_corpus_block`); answers use statements, rules, and labels |
| Evidence | No source items; the disclosure would show only the formal buttons of U74 |
| Sources & glossary dialog | Glossary only, plus "No uploaded reference documents." |
| Export, snapshot, submission | Valid files with an empty sources list; the "Reference documents" section is omitted |
| Chat placeholder | "Ask about the case, a rule, or a conclusion..." presumes a case with sources |

Nothing tells the user that answers for this scenario cannot cite anything, so
the absence of citations looks like a model failure rather than a property of
the scenario. Live model answers without documents were not exercised here.

**U77. High (defect). Enter sends the question while an input-method
composition is being confirmed.** The composer's key handler sends on Enter
without Shift (`app.js:197-202`) and never checks `event.isComposing` or
`keyCode === 229`. Users typing with a Chinese, Japanese, or Korean input
method confirm a composition with Enter, and that keystroke submits the
half-typed question and spends credit. The fix is one condition plus a
focused regression test; the same check belongs in the token composer (P15).
Raised by David.

### 4.6 Workspace, editor, and other dialogs

**U33. Medium. Workspace naming.** The dialog is "Research workspace" with tabs
Account, Projects, Examples, AI access, and "Codex and Claude"
(`index.html:162-174`). The last is named after two products rather than the
function (agent access through MCP tokens). The AI tab heading "AI access for
this browser tab" and the label "Funded model profile" use implementation
vocabulary.

**U34. High. Two dialogs own the "open a scenario" task.** "New / Open" opens
"Your scenario" with New and Import tabs and a "My projects" button that closes
this dialog and opens Workspace > Projects (`scenarios.js:113-115`). The
Projects tab then stacks, from the top, a green "Open project" card with four
buttons, the "Save current analysis as a new project" form, and finally "Your
projects" (`workspace.js:789-868`). The list a user came for is last.

**U35. Low. The editor is long but coherent.** Numbered steps, one draft for
both entry points, Guided and Rule text as views, and "Preview" before "Save &
open" are good decisions. "Rename symbol" and "Load or paste a glossary" are
advanced and sit in the main flow as collapsed sections; "Try a small example"
and "Clear draft" are small buttons on a "Start below, or" line. The disabled
"Save & open" is not explained until a preview has run.

**U36. Low. Sign-in prompts appear in four wordings.** Save ("Sign in with a
verified email to save a private project."), editor banner ("Sign in to create
or import private scenarios. No trial credit or API key is needed."), chat
note, and the Account tab lead. Each is correct; a single sentence reused
everywhere would read as one product.

**U37. Low. The edit dialogs are good.** Add Fact, Add Assumption, Add Rule,
and Edit Rule are clean, the Add Rule placeholder explains "normally" versus
"necessarily", and the footer switches to Refine and Apply after a proposal.
One detail: Edit Rule seeds the current rule as a placeholder
(`app.js:2539-2551`), which disappears on the first keystroke and cannot be
copied; a read-only line above the textarea would serve better.

**U38. Keep. The suspend-impact preview is the best dialog in the product.**
It states the change, lists every conclusion whose label would move, and asks
for Apply. It should become the model for other confirmations.

### 4.7 Narrow layouts

**U39. Medium. Phone layout.** At 390 px the top bar becomes a two-column grid
of eight buttons plus the select, about 250 px tall, before any content
(`style.css:1044-1067`). Conclusion cards keep the 88 px status block and the
three-button group, leaving roughly 100 px for the label (five lines for
"Hayashi does not have to return the baseball"). The chat panel is about four
screens down. The 780 px stacking with 55 vh list heights is otherwise sound.

**U40. Medium. Laptop widths between 780 and 1100 px.** The bar wraps to two
rows and conclusions squeeze (U12). These are the effective widths of a
projector at 125 to 150 percent zoom, which the conference playbook asks
presenters to record.

### 4.8 Visual design

**U41. Medium. No identity.** System font stack, a blue accent, a light gray
canvas, 8 px radii everywhere. The brand mark is "ABDA-NL" over "iDAKS Lab" at
9.3 px. Nothing in the visual language says "argumentation" or "research
instrument"; it could be any admin panel.

**U42. Medium. The type scale is too small.** Computed sizes at 1440 x 900: rule
text 13.1 px, fact text 12.5 px, conclusion label 13.4 px, status block 10.2
px, category badge 9.3 px, ids 10.6 px, filter pills 10.9 px, small buttons
11.2 px, storage note 11 px, lab label 9.3 px. The 15 px body size is used
almost nowhere. On a projector these sizes are unreadable from the back of a
room, and even on a laptop the interface reads as denser than its content.

**U43. Medium. Elevation without hierarchy.** List cards, panels, and dialogs
all use the same one-to-two-pixel shadows (`style.css:21-22`), and the top row
of panels has a stronger shadow than the dialogs. Hover on any card changes
its border to the accent color, so the accent appears on whatever the mouse
passes over.

**U44. Medium. Seven color families.** The status palette (blue accepted,
orange rejected, yellow undecided, gray absent) is well chosen, distinguishable
under the common color-vision deficiencies as far as a hex inspection can tell,
and used consistently on cards, badges, the impact dialog, and the graph; keep
it, and verify contrast and simulated deficiencies when the tokens are
finalized. Around it: green and red tokens for the trial meter and example
status, blue-gray and brown for the game bars, violet for "changed", twelve
category tints, yellow for notes, green for the project chip, and blue for
links and the accent. The eye cannot tell which colors carry meaning.

**U45. Low. Buttons do not signal importance.** Everything is an outlined pill;
"Explain" and "Inspect" have the same weight; "?" is a circle; "Modify" is a
gray pill; primary blue is reserved for Save and the three "+ Add" buttons,
which are the actions a newcomer should try last.

**U46. Low. No dark theme, no icons.** Reduced motion, focus rings, skip link,
and live regions are handled well. Icons are absent, which makes 48 text-only
labels harder to scan; a small set of inline SVG icons needs no change to the
content security policy.

### 4.9 What works and should be kept

- The status palette and its consistent use across cards, the impact dialog,
  the Explain badges, and the graph.
- The suspend-impact preview dialog.
- The "?" drafting flow with removable chips and the explicit stale-context
  handling (R10).
- The honesty of evidence captions and the "computed by ABDA" wording (R12,
  R01).
- The editor's numbered steps, single draft, Guided and Rule text views, and
  Preview gating.
- Keyboard resizing of dividers, focus management in dialogs, the skip link,
  the "Status changed" text under a changed conclusion, and reduced-motion
  handling.
- The empty-state hint in the chat panel and the sign-in note with an inline
  "Open settings" action.
- The violet left bar for items changed from baseline.

### 4.10 Authoring, projects, sharing, and community examples

This section reviews the flows a researcher uses to bring their own scenario
into the demo and to publish it: creating or importing a scenario, saving it
as a private project, sharing a read-only link, suggesting it as a community
example, and, for administrators, reviewing, publishing directly, and
switching to the normal user view. All states were exercised on the throwaway
instance with an ordinary account and with an account named in the test
administrator list. Screenshots of every state are in the session scratchpad.

#### Creating a scenario

**U48. Medium. A new draft starts with placeholder rows that then fail
validation.** "New scenario" opens with one empty Fact, one empty Claim, and one
empty Rule (`scenarios.js:307-314`). Preview then reports "Write a statement in
each row, or remove the empty row." and "Choose an existing statement for every
condition and conclusion in rule 3." for rows the user did not add. An empty
state ("No statements yet. Add one, or try the picnic example.") would set
expectations better than pre-filled blanks.

**U49. High. Auto-generated identifiers leak into the explorer.** Statements
are named `statement_1`, `statement_2`, and rules `rule_1` unless the user
opens "Symbol & details" or "Priority & details" and renames them
(`scenarios.js:316-321`, `353`). After "Save & open" these ids appear on every
card, in ASPIC- text, in chat context, in the derivation inspector, and in
citations. The scenario the user built in plain English is displayed with
meaningless symbols, and the fix is hidden two disclosures deep.

**U50. Medium. Editing a project reuses the "new scenario" chrome.** "Edit
scenario" on a private project opens the same dialog: the title says "Edit
private scenario" but the tab strip still shows "New scenario | Import
scenario" with New active, the line "Start below, or Try a small example / Clear
draft" remains (both replace the project's draft after a confirm), and the
Background field stays collapsed even when the project has a background
(`loadScenarioDraft` never opens the details, `scenarios.js:292-293`).

**U51. High. The statement pickers in rule cards do not scale.** Each "If",
"And", and "Conclude" field is a native select listing every statement twice
(positive and negated) plus every defeasible rule's undercut
(`scenarios.js:394-408`). For Popov that is about 150 options, unsearchable,
with the negated entries reading "Not: <sentence>". Above roughly twenty
statements the guided editor is not usable for rules, and the 100-statement
limit that switches the whole editor to Rule text is announced by a single
sentence.

**U52. Medium. Long scenarios have no structure in the editor.** Statements are
one flat list of cards, each about 110 px tall with a kind select, the
sentence, a remove button, and a "Symbol & details" disclosure; Popov produces
about 6,000 px of scrolling with no grouping by kind, no filter, and no
collapsed state. Rule cards are titled "Rule 1", "Rule 2" by position, so
removing one renumbers the rest and error messages that say "rule 3" refer to a
moving target.

**U53. Medium. Validation speaks only from the footer.** Errors such as "Give
your scenario a title." and "Choose an existing statement for every condition
and conclusion in rule 3." appear in the status line at the bottom of the
dialog in red (`#scenario-library-status`); the offending field is neither
marked nor scrolled to, and the title field may be far above the fold.

**U54. Medium. The save gate is unexplained.** "Save & open" is disabled until
Preview succeeds, and disabled again after any edit (`scenarios.js:101-106`,
`208`). Nothing near the button says why; the only explanation is the footer
message that appears after a preview ("Preview ready. Save when the scenario
looks right."). Users learn the rule by trial. The two-step check is a sound
safeguard; its presentation is not.

**U55. Low. The preview is a different rendering from the explorer.** Counts
as gray chips, key conclusions with a plain gray word ("undecided") instead of
the explorer's status pills, and rules in a collapsed numbered list phrased
"If A, usually B. Priority 1." (`scenarios.js:539-575`). The user sees three
renderings of the same knowledge base across the editor, the preview, and the
explorer.

**U56. Medium. Import infers roles from filenames and reports far from where
the user looks.** Roles are guessed by extension and by the substring
"glossary" in the name (`scenarios.js:583-585`); a plain `.txt` document gets
no role and blocks with "Choose a role for every file.", and a glossary is
recognized only if the filename says so. The file list shows no sizes. After
"Load into editor" the list clears and the confirmation ("Materials loaded
together. Review the editor, then Preview and Save & open.") appears in the
footer, about 600 px below the dropzone. A rule-text import becomes a draft
titled by the filename ("picnic"), and two more clicks (Preview, Save & open)
are needed before anything is saved.

**U57. Low. Two entry points to the same sample.** "Try a small example" on the
New tab and "Download a starter file" in the Import dropzone both use the
picnic scenario (`scenarios.js:459-472`, `181-184`).

**U58. Medium. Reference documents are reviewed in a five-row textarea.** The
section is a collapsed "0 attached documents" disclosure; each document is an
open card with a filename field, a five-row textarea holding the full extracted
text (up to about 99,000 characters for a 40-page PDF), an optional URL, and
Remove (`materials.js:37-50`). There is no size, page count, or search, and the
limits are a fine-print sentence. "Review the extracted text" is the right
instruction and the wrong tool.

#### Saving as a private project

**U59. Medium. Two ways to make a project with two vocabularies.** "Save
project" in the top bar opens Workspace > Projects with a form titled "Save
current analysis as a new project", prefilled "<title> exploration"; "Save &
open" in the editor creates a project from the draft. Both produce the same
object. In the Projects tab the form stays at the top even when a project is
open, where it means "save a copy", and the list the user came for sits below
it (`workspace.js:789-868`).

**U60. Medium. Archive is deletion without saying so.** A project card offers
Open and Archive; Archive asks a native confirm and the project disappears.
Projects are listed with `archived_at IS NULL` (`app/services/projects.py:96-100`),
there is no archived list and no restore route in the application, and only the
operator's privacy tooling can bring one back. The card also shows nothing
about share links, submissions, or the source example.

**U61. Low. The after-save state is good.** The toast says "Opened "Planning a
picnic". Saved privately, ready to explore." and the top bar switches to the
project with its chip. Keep this.

#### Sharing a read-only link

**U62. Low. Sharing works and reads clearly.** The one-time link with Copy, the
"Existing links" list with Revoke, the "Shared read-only" chip, the disabled
Reset and hidden edit controls, the chat note "Chat and edits are disabled in a
shared read-only view.", and the prefilled "copy" form after sign-in are all
right. Three gaps: the interface always creates links with no expiration
although the API records an expiry; a link has no label; and in a shared view
the primary button still says "Save project" where it means "Save a copy".

#### Suggesting a community example

**U63. High. The primary button is visible but disabled, and the control that
enables it is at the end of a listing of everything.** "Suggest as example"
opens a dialog whose footer holds "Submit for review" and "Close"
(`index.html:707`), while the scrolling body renders the background, every
fact, assumption, claim, and rule (38 rules for Popov), collapsed disclosures
for attached documents and raw JSON, and only then the consent panel with the
checkbox that enables the button (`curation.js:113-139`, `195-214`). A user
who does not scroll to the bottom sees a disabled primary button with no
explanation. Nothing summarizes what
will be published (counts, documents and sizes, background, version) before the
listing.

**U64. Medium. What becomes public cannot be shaped.** The public title is the
project name and the public description is the scenario background
(`curation.js:160`; catalog fields at
`app/services/scenario_submissions.py:235-261`). Neither is editable at
submission, and there is no note to the reviewer. The listing is a third
rendering of the knowledge base, different from the editor preview and the
explorer.

**U65. Medium. Status is only discoverable by visiting the Examples tab.**
After submission the dialog switches to Examples with one card ("Awaiting
review", "View snapshot") and the toast says "Submitted for review. Check
Examples for updates." The project card shows nothing, the tab shows no count,
and there is no notification of a decision (documented as intentional). A
declined submission's reason is visible only in that tab.

**U66. Low. Six phrasings for one object.** "Suggest as example", "Example
submissions", "Submit for review", "Awaiting review", "Submitted snapshot",
"Withdraw request". "Snapshot" is implementation vocabulary.

#### Reviewing and publishing (administrators)

**U67. Medium. The queue is a select without counts or authors.** The Examples
tab shows a native "Show" select (Awaiting review, Published community
examples, My submissions, Declined submissions, Withdrawn or removed) and cards
with title, "Snapshot of version 1 · date", and "Review snapshot"
(`curation.js:78-107`, `index.html:278-287`). A reviewer cannot see how many
items wait or who submitted them.

**U68. Medium. The review dialog separates the decision from its note and
mixes dialog styles.** The footer offers Decline, Approve & publish, and Close
at all times, while "Note to the author (required when declining or removing)"
sits at the end of the long listing. Declining without a note produces an
error in the dialog's status line and sends the reviewer scrolling to find the
field; approving opens a native `window.confirm` ("Publish this exact snapshot as a
public, downloadable example?", `curation.js:229`) on top of the styled dialog.
After approval the toast says "Published. The scenario is now in Community
examples." and the queue stays on "Awaiting review", now empty, with no link
to the published example (`curation.js:244-251`).

**U69. Medium. Direct publication is less guarded than approval.** On an
administrator's own project the card says "Publish as example" and the dialog
"Publish as example" with the same consent checkbox and a "Publish example"
button, and no second confirmation, while approving someone else's submission
asks one. Direct publication is the more consequential act.

**U70. Low. A published example is indistinguishable once opened.** It appears
in the scenario select under "Community examples" with its title only; opened,
the top bar chip says "Example". No author, date, or community marker. The
administrator's own "Remove from examples" requires a note "to the author" even
for their own example.

#### Normal user view (administrators)

**U71. High. The restore button wraps the top bar on a 1440-pixel display.**
Switching to normal user view shows a "Restore administrator view" button in
the top bar (`index.html:39`); at 1440 x 900 the "Save changes / Privacy /
Terms" cluster drops to a second row. The five named administrators are the
presenters, and demonstrating as a normal user is exactly what the view is
for, so this is the projected state.

**U72. Medium. Three indicators, and the card does not say what changes.** The
"Normal user view" chip in the brand line, the top-bar button, and the Account
card (heading, description, and button all flip, plus a status line "Normal
user view is active.") all announce the same mode. The card says what stays the
same ("Your projects and credit stay the same") but not what changes: no review
queue, no direct publish, "Publish as example" becomes "Suggest as example",
and the queue filter disappears. Entering the mode is three clicks (Workspace,
Account, button); leaving it is one.

**U73. Low. The card reads as a setting, not a mode.** "Administrator view"
with a button "Use normal user view" looks like a preference; the abstract and
the contract describe a demonstration mode. Naming it "Demonstrate as a normal
user" in the account menu (P03) says what it is for.

## 5. Principles for the redesign

1. **Group by activity, not by subsystem.** A newcomer should find "choose a
   case", "understand why", "try a change", "ask", and "keep" as distinct
   places, and should never need to know that projects, examples, and the
   editor are different modules.
2. **One name per thing, and the button says what the dialog is titled.**
3. **Conclusions first.** They get the widest column, the largest type, and the
   single most prominent action, "Explain".
4. **Reading before doing.** Text is 14 px or larger in lists, identifiers and
   badges never below 12 px, and every decoration that competes with the
   sentence is removed or muted.
5. **Progressive disclosure for expert tools.** Derivation inspection, ASPIC-
   text, symbol renaming, MCP tokens, and BYOK stay one click away but do not
   share the first screen with the reading experience.
6. **Nothing silent.** No action changes another panel's state without telling
   the user (Reset and conversations), and no message hides a control.
7. **Keep every requirement.** All of R01 to R16 remain satisfied; in
   particular the "Chat & Exploration" heading (R14), the "?" behavior (R10),
   individual derivations (R13), and the administrator view (R16).

## 6. Redesign proposal

### 6.1 Where every function goes

| Function | Today | Proposed home |
| --- | --- | --- |
| Switch between examples, community examples, projects | Select + two dialogs | One **scenario popover** on the scenario name: a selection list plus action buttons (P01) |
| New scenario, import file | "New / Open" dialog tabs | Action buttons in the scenario popover; same editor dialog, titled "New scenario" or "Import scenario" |
| Edit the current private scenario | "Sources & glossary" relabeled "Edit scenario" | Scenario menu item "Edit scenario", project only |
| Download the scenario | Editor footer | Scenario popover and the Save split button: "Download scenario (.json)", available signed out |
| Read source documents and glossary | "Sources & glossary" (filenames only) | **Sources** reader (P09), opened from the scenario menu and from every citation |
| Scenario background | Hidden | "About this scenario" strip under the top bar, collapsible (P10) |
| Category grouping | "Compact" in top bar | "Group by category" in the Facts and Rules panel menus (P04) |
| Formal views | "View Graph" (Conclusions header), "Show ASPIC-" (top bar) | A "Views" pair in the Conclusions header: **Conclusion graph** and **ASPIC- text** (P04) |
| Reset what-if changes | Top bar, always enabled | Inline with the modified-count chip: "Modified: 2 changes · Reset", visible only when modified, reversible through a bounded Undo, never touching the conversation (P02) |
| Model access | Two chips | One **AI** chip in the top bar showing model and funding source (P03); nothing in the chat header |
| Account, trial, agent tokens, admin view, legal | "Workspace" + top-bar buttons + links | One **account menu** (P03) |
| Save, share, publish | "Save project" + Workspace > Projects | One **Save** split button: direct Save, secondary actions in its menu (P03) |
| Explain, Inspect on conclusions | Two buttons + "?" | "Explain" (primary) and "?"; derivation inspector as a tab inside the Explain dialog (P06) |
| Inspect, Modify on rules | Two buttons + "?" + checkbox | Id link opens the inspector; "Modify" moves to a per-row overflow with "Ask about this rule"; "?" stays; toggle becomes a labeled switch (P05) |

### 6.2 The top bar

Recommended layout at 1440 px (one row, about 60 px tall):

```
 ABDA-NL   [ Popov v. Hayashi  ▾ ]  Example   ⓘ About        Modified: 1 change  · Reset        [ AI: Claude Sonnet 5 · funded ▾ ]  [ Save | ▾ ]  [ Account ▾ ]
```

At 1024 px the row should still fit because the middle group collapses to a
count chip and the right group keeps three controls; this is a target to test
with long project names, larger fonts, every access state, and the normal
user view, not an established fact. Wrapping into two clearly grouped rows is
acceptable where it preserves usable space. Below 780 px the bar becomes two
rows by design: name and status, then the three controls.

**P01. Scenario popover.** Opens from the scenario name. Replaces the select,
"New / Open", the "My projects" button, "Edit scenario", and the editor-footer
download. It has two parts: a selection list of scenarios and a row of action
buttons. Commands are never options in the list.

```
 ▾ Popov v. Hayashi
 ──────────────── Included examples ────────────────
 ● Popov v. Hayashi          19 facts · 38 rules · 8 conclusions
   Prescribed Burn
   PPI Therapy
   NBA Rebuild
   Fried Chicken V1
   Fried Chicken V2
 ──────────────── Community examples ───────────────   (only when any exist)
   ...
 ──────────────── Your projects ────────────────────   (signed in; "Sign in to see your projects" otherwise)
   Popov v. Hayashi exploration       v3 · Sep 10
   Manage projects...
 ───────────────────────────────────────────────────
   New scenario...
   Import scenario file...
   Download this scenario (.json)
   Sources and glossary                                (opens the Sources reader, P09)
   Edit scenario...                                    (private project only)
```

The upper part is a listbox (W3C listbox pattern): arrow keys and type-ahead
move focus, Enter or click activates, and moving focus never loads a scenario
or triggers the unsaved-change prompt. The lower part, below the rule, is a
group of ordinary buttons with their own tab stops. The current item is
marked. The one-line summary per example (counts) is cheap to compute from the
catalog and helps a newcomer choose.

**P02. Status group.** The "Example / Private project / Shared read-only" chip
stays next to the name. The modified chip appears only when there are changes
and carries the Reset action inline ("Modified: 1 change · Reset"). Reset is
disabled at zero changes, needs no confirmation, and is reversible: the status
banner (P14) shows "Reset 2 changes to the baseline. Undo", and Undo
re-applies exactly the captured operations against the captured baseline
through the same state request. The Undo stays available until an incompatible
transition (another edit, a scenario or project switch, a save, or a reload)
invalidates it; the banner may hide earlier, but the action does not depend on
a timer. Reset never starts a new conversation (P08, section 7 decision 3).

**P03. Three controls on the right.**

```
 [ AI: Claude Sonnet 5 · funded ▾ ]     [ Save | ▾ ]                        [ Account ▾ ]  (initials when signed in)
   Funded trial · $4.71 left              Save as private project...          Signed in as UI Reviewer
   ● Claude Sonnet 5 (default)            Save changes            (project)   reviewer@example.edu
     Claude Opus 5                        Create share link...    (project)   Trial credit: $4.71 of $5.00
     GPT-5.6 Terra                        Suggest as example...   (project)   ─────────────────
     GPT-5.6 Sol                          Download scenario (.json)           AI access settings...
     Gemini 3.8 Flash                     Export conversation (.json)         Agent access (Codex, Claude Code)...
     Gemini 3.1 Pro Preview                                                   Use normal user view   (administrators)
     Kimi K3                                                                  ─────────────────
   ─────────────                                                             Privacy · Terms
   Use your own API key...                                                    Sign out
```

The AI chip shows the model and the funding source ("· funded" or "· own
key"), changes the funded profile directly, and links to the full settings
for BYOK. Save is a split button: the main part acts directly (save a new
private project from an example, save changes on a project, "Save a copy" on a
shared view, and, signed out, open the account menu with one sentence), and
its chevron opens the secondary actions. "Download scenario (.json)" and
"Export conversation (.json)" are never disabled by sign-in state, because
both work for signed-out users today; only sharing and publishing need an
account. The account menu absorbs Workspace > Account, the trial card, the MCP
tab, the administrator view toggle, and the policy links. "Restore
administrator view" becomes a menu item, while the "Normal user view · Restore"
chip in the status group is the persistent indicator and one-click return that
R16 asks for.

A grouped toolbar with visible clusters (Scenario, View, Account) was
considered as an alternative and rejected: it still wraps below about 1150 px,
which is the effective width of a zoomed projector, and it leaves eight
controls on the first screen (section 7, decision 1). Every control that the
rehearsed narrative uses (Reset, Explain, the toggles, Ask, the graph) stays
outside the popover and the menus.

### 6.3 Explorer panels

**P04. Conclusions become the primary panel.** Reclaim the width first: the
88 px status block becomes a 6 px colored left stripe plus a short pill
("Rejected") under the sentence on narrow widths and to its left on wide
widths, and the three-button action group becomes one primary action plus
"?". That alone roughly doubles the sentence width at 1280 px. Then set the
default split so that Conclusions get at least as much width as Facts &
Assumptions, with a minimum of 420 px, and raise the top row to about 42
percent of the height; the exact proportions are decided at the prototype
review, and the existing draggable and keyboard-resizable dividers stay. Set
the label to 15 px. Sentences wrap; they are never truncated, and no essential
control is hover-only. Pointer targets meet the WCAG 2.2 minimum of 24 by 24
CSS pixels, larger where practical. Header:

```
 Conclusions · 8 key                     Key  Accepted  Rejected  Undecided  Absent  All        Views:  Conclusion graph   ASPIC- text
```

"Conclusion graph" and "ASPIC- text" open the two existing dialogs, retitled
to match, so that button and dialog agree. A conclusion row:

```
 ┃ Hayashi does not have to return the baseball                        [ Explain ]   ?
 ┃ Rejected                                                            hayashi_no_return
```

One primary action per row. The derivation inspector remains directly
reachable from every row, including absent conclusions: the muted identifier
is the link, and the row's "..." menu carries "Inspect derivations". The
Explain dialog additionally gains a Derivations tab (P06), so a user who is
already reading the game reaches the same inspector without closing it. R13's
requirement that derivations sharing a conclusion or top rule stay
distinguishable is unchanged.

**P05. Facts & Assumptions and Rules.** Split kind from state:

```
 Facts & Assumptions            [ Facts | Assumptions ]     Show: ( ) Changed  ( ) Suspended       ⋯   [ + Add ▾ ]

 Rules                          [ All rules | Conflicts ]    Show: ( ) Changed  ( ) Suspended   Search...   ⋯   [ + Add rule ]
```

"Changed" and "Suspended" are independent toggles that filter the current
kind. The panel menu (⋯) holds "Group by category" (replacing Compact) and,
later, density. "+ Add" is one button with Fact and Assumption items; both
stay model-assisted as today. Rows lose their border and shadow and use a 1 px
hairline separator, 14 px text, and a hover tint. The category badge becomes
an 11 px text label in its tint color without background, placed before the
id. Rule connectives render in small caps at normal weight in the muted text
color ("if ... then normally ...") so that the sentence is the strongest
element; "normally" and "necessarily" keep a dotted underline with a tooltip
that explains defeasible versus strict, which teaches the distinction the
abstract stresses. A rule row:

```
  if Popov has a qualified right to possession of the baseball then normally Hayashi has to return the baseball
  decision · rp                                                            ?   ⋯   [ Active ● ]
```

The switch shows its state word; the overflow holds "Modify with AI",
"Inspect derivations", and "Copy ASPIC- line". The "?" remains a visible
control as R10 requires. In the Conflicts view the three radios read
"Prefer r1", "Equal priority", "Prefer rp" with the rule sentences above them,
as today; "wins" would overstate a priority, since other attacks can still
defeat an argument that uses the preferred rule.

### 6.4 Explain, inspector, and graph

**P06. Explain dialog.** Auto-select when there is exactly one candidate root.
When there are several, title the cards "Argument 1 of 2, via rule r1" with the
rule sentence, keep the exact derivation id in the muted caption, and, when
two candidates share a top rule, add the premise or sub-argument that
distinguishes them, since sharing a top rule does not make derivations the
same (R13). Add two tabs at the top of the dialog: "Discussion game" (current
tree) and "Derivations" (the current inspector, opened at the same root); the
game helpers read the live bundle while the inspector accepts a saved one
(`app.js:2403`, `exploration.js:585`), so the shared frame must pass the
bundle explicitly rather than move markup. Auto-resolve only genuinely
terminal leaves (no moves, no cycle, no unresolved child) instead of showing
"Continue"; keep a "Next open branch" button when other branches remain. The
wording must not suggest that walking the moves assigns the label; the label
is computed and the game explains it. Prefix each card bar with its role, "Proponent · Has to be the case:" and
"Opponent · Can be the case that:", and add one legend line under the title:
"The proponent defends the conclusion; the opponent raises challenges. A claim
is accepted when every challenge against it is answered." Scroll the newly
focused node into view after each move.

**P07. Graph.** Label nodes with a short natural-language form (first 32
characters of the description, ellipsis, full text in the tooltip) and show the
identifier as a second, smaller line. Default the "All conclusions" scope to
hide nodes without any displayed attack edge, with a labeled checkbox (see
below). Replace the hollow-versus-filled arrowhead distinction with a
double stroke for mutual rebuts, which is visible at any zoom, and keep the
dashed line for undercuts. Name the button and the dialog the same,
"Conclusion graph": the view is a projection of arguments by conclusion, as
the paper describes, and "Argument graph" would blur the distinction R13
asks for. Keep the full set of nodes available; the isolated-node filter is
labeled "Show 30 conclusions without displayed attacks", because a node with
no projected edge can still have argument-level attacks that the projection
drops, and any filter states its count.

Fix U76 in two layers:

- **Dialog stacking (general).** `openModal` keeps a stack of open dialogs,
  assigns each newly opened backdrop a z-index above the previous one
  (`100 + depth`), marks the dialogs beneath it inert (`inert` attribute or
  `aria-hidden` plus focus exclusion) so they receive neither clicks nor
  focus, and the Escape and focus-trap handlers use the top of that stack
  instead of document order; `closeModal` pops the stack, restores the
  previous dialog's interactivity, and returns focus to the element that
  opened the closed dialog (W3C modal dialog pattern). This is a contained
  change in `workspace.js:42-144` and `app.js:2493-2499`, independent of the
  tabbed frame in P06, and it makes any future nested dialog safe.
- **Graph to derivation (specific).** Remove the "Inspect derivations"
  toolbar button. Make each node clickable and keyboard focusable
  (`tabindex="0"`, Enter activates): a click opens the inspector for that
  conclusion's preferred derivation, the same choice Inspect makes in the
  Conclusions panel, and the graph dialog is replaced rather than covered.
  The inspector then shows a "Back to graph" button that reopens the graph at
  the same scope and zoom. Nodes get a pointer cursor and a hover ring so the
  affordance is visible, and the legend line reads "Click a node to inspect
  its derivations." With P06, "Back to graph" and the Explain tab share one
  dialog frame, so the user moves between the overview, the game, and the
  derivation without stacked windows.

### 6.5 Chat and exploration

**P08. Panel structure.** Keep the heading text "Chat & Exploration" (R14).
Remove the model chip from the header; the AI chip in the top bar and the
per-answer line ("Funded, claude-sonnet-5, $0.01, 4210 ms") already state the
route.
Move the routine storage note ("Saved automatically in this browser...") into
a tooltip on the conversation menu and show it once, the first time a
conversation is saved; storage failures, the concurrent-copy notice, and the
deleted-elsewhere notice stay visible in the panel as they are today. Replace
the toolbar with:

```
 Chat & Exploration
 ┌──────────────────────────────────────────────────────────┐
 │ ▾ How did the court actually decide who gets th...   ⋯   │      [ + New ]
 └──────────────────────────────────────────────────────────┘
```

The conversation menu lists conversations with title, date, scenario name, and
an "(answer pending)" or "(new answer)" marker, and has "Export this
conversation", "Export all", and "Delete" in its ⋯ menu. Per-turn controls
collapse to one muted line under each question: "Asked about Popov v. Hayashi,
baseline · Fork with current scenario · Snapshot ▾". The fork label names the
scenario choice visibly, as R11 requires; a tooltip is not enough. Context chips show the sentence (truncated at 40 characters) with the
id in the tooltip, keep the amber stale state, and keep "Refresh" and remove.
Vary the drafted question by kind while keeping it explanatory: "Why is
<conclusion> rejected?" for a conclusion with its label, "What does this rule
contribute to the conclusions?" for a rule, "What role does <fact or
assumption> play in the conclusions?" for a fact or assumption. A
counterfactual ("What if ... did not hold?") changes the task and is not a
default; it can be offered as a second editable suggestion later. Because the
template is part of the model input, its effect is assessed on the existing
chat cases before it ships, without new paid qualification for presentation
changes alone. Evidence rendering is specified in P29.

Reset does not start a new conversation (U07, decision 3). Each question
already stores its own snapshot, so continuing after a reset is sound: the next
question records the baseline snapshot, and references added before the reset
show the existing "earlier scenario" state with Refresh. Switching to another
example or project keeps today's behavior of starting a new conversation, so
that each thread reads coherently, and the previous conversation stays in the
menu. A conversation is not bound to one scenario in the data model: selecting
a conversation does not load its scenario, and every turn keeps its own
snapshot.

**P15. Inline reference tokens in the composer (replaces the chip strip).** The
draft becomes one model, a sequence of text segments and reference tokens, and
the textarea becomes a composer that renders tokens inline as colored chips
inside the text, the pattern used by Cursor's chat composer for file and symbol
mentions. Specification:

- **Insertion.** "?" inserts the kind-specific question with the token embedded
  at the caret, for example `Why is [Hayashi does not have to return the
  baseball] rejected?` or `What does [rp] contribute?`, preserving existing
  text, focusing and revealing the composer exactly as today. The token shows
  the description (truncated at about 40 characters, full text and identifier
  on hover) and takes its color from the item kind: the conclusion's status
  color for conclusions, the accent for rules, a neutral tint for facts and
  assumptions.
- **One unit.** A token is atomic for caret movement and selection. Backspace
  or Delete removes the whole token and its reference, and nothing else; the
  surrounding prose is never touched by a removal. Clicking a token, or
  pressing Enter or Space while it has keyboard focus, converts it into plain
  text (the description in quotes) and drops the reference, so the user can
  reword it. This is Haoyang's requested behavior; because it is easy to
  trigger by accident, the token shows "Click to edit as text" on hover and
  focus, and the status banner offers Undo until the next edit. Paste inserts
  plain text only: a reference copied from elsewhere arrives as words and can
  be re-attached with "?"; that is a deliberate limit, not a defect.
- **Prose and references stay independent.** A user may delete every
  generated word and type "How do these two rules differ?" while keeping both
  tokens in the text, which is the workflow the existing browser test
  protects (`tests/test_exploration_browser.py:150-156`). The only constraint
  the token model adds is that a reference the question keeps must appear
  somewhere in the question, which is what a reference means.
- **Stale state.** A token whose scenario no longer matches turns amber with a
  dotted underline and the tooltip "From an earlier scenario. Refresh or remove
  before asking"; a small refresh control appears on hover and on focus. The
  submission rule is unchanged: Ask is blocked while any token is stale, with
  the existing message. The 24-reference cap is enforced at insertion with the
  existing message.
- **Submission.** The message text sent to the model is the serialization with
  each token replaced by its quoted description, which is exactly what the
  backend receives today; `context_refs` are the tokens in document order. No
  API change.
- **Persistence and forks.** The conversation record stores the segment model
  as the draft, and every sent user message stores its segments alongside the
  plain `content` that the API receives, so a fork rebuilds the exact tokens
  from the record without any text matching. Old string drafts load as one
  text segment with old `context_refs` appended as tokens; old messages that
  have only `content` and `context_refs` fork the same way. Quoted-description
  matching is not used for reconstruction.
- **Accessibility and input methods.** The composer is a `contenteditable`
  region with `role="textbox"` and `aria-multiline`; tokens are non-editable
  spans with an `aria-label` naming the kind and description; a hidden live
  region announces "Reference added", "Reference converted to text", and
  "Reference removed"; the keyboard behavior is listed in the composer's
  description. Enter sends only when `event.isComposing` is false (U77);
  Shift+Enter inserts a line break. Clean axe scans are necessary, not
  sufficient: the acceptance list includes caret movement across tokens,
  selection that spans a token, undo and redo, IME composition, mobile
  virtual keyboards, and draft migration.
- **Removal.** The chip strip above the composer (`#chat-context-items`) and its
  styles go away. R10 remains satisfied: the same generated question is
  inserted, existing text is preserved, identity is retained, references are
  removable, several items are supported, nothing is sent on click.
- **Later.** Typing `@` in the composer can open a picker of scenario items,
  which is the natural extension of the same model; not needed for the
  conference.

Implementation is a self-contained composer module of a few hundred lines
replacing the textarea, with the existing signature and reference helpers
reused; the exploration browser tests that fill `#chat-input` need updating.
It is its own phase (section 8, phase 4), after the top bar and legibility
work. Until it ships, the current chip strip is relabeled "Referenced items"
with a one-line explanation, "Removing an item detaches its context; your
question text is unchanged", and the existing removal, refresh, and stale
controls stay. No automatic synchronization between chips and text is
introduced at any point: an earlier idea of removing a chip when its quoted
sentence disappears would have broken the tested workflow of keeping
references while rewriting the question, and is withdrawn.

**P29. Evidence as corpus spans in context; formal references as links.**

- **Source cards lead.** The evidence section under an answer becomes
  "Sources (n)" and lists one card per verified source item: the document
  name, a "Quotation" or "Context" tag whose tooltip carries the current
  two-sentence explanation (locating text does not establish that the claim
  is supported), and the surrounding paragraph of the document with the span
  highlighted. The paragraph comes from the document text that the
  conversation snapshot already embeds (`captureConversationSnapshot` stores
  the version 3 export with full source text), so no backend change is needed
  for the card itself. Locating the span needs care: chat reads bundled PDFs
  with `pdftotext -layout` when it is installed while the export reads them
  with `pypdf` (`app/llm/corpus.py:38-62`, `app/scenario/portable.py:29-35`),
  so the two texts differ for PDFs, and offsets are code points on the server
  and UTF-16 units in the browser. The card therefore verifies that the
  slice at the offsets equals the supplied quote after converting the
  offsets, falls back to an exact-quote search only when it finds exactly one
  match, and otherwise shows the supplied excerpt with "Location in the saved
  document could not be confirmed." It never highlights an arbitrary
  duplicate and never consults the current project for an old answer.
  Aligning the two extraction paths would change model inputs and is a
  separate decision with its own qualification consideration. "Open in
  Sources" opens the reader (P09) at that position; the reader and the cards
  ship together. The card is expanded by default when there are at most two
  items, collapsed to the quotation otherwise.
- **Formal context becomes one line.** The "Inspect rule rh" and "Inspect
  conclusion ..." buttons go, and in their place a single muted line under the
  answer, "Referenced items:", shows the items the question selected as the
  same chips the composer uses (P15), each opening the derivation inspector
  against the answer's saved snapshot, exactly as the buttons do today. This is
  retained rather than removed because the chat prompt keeps identifiers out
  of answers (`app/prompts/chat_system.md:27`), so an ordinary answer offers
  no other way back to the saved derivation of an item the question was about;
  and because R12 asks that formal references identify the relevant rules,
  arguments, and labels. The line is absent when the question selected
  nothing. The API is unchanged: these items already travel inside the
  `evidence` array with kinds `rule`, `argument`, and `conclusion`
  (`app/llm/chat_service.py:591-593`, merged at `622` and `671`).
- **Identifiers in the answer become links, as a supplement.** When an answer
  does contain a bracketed identifier that matches a rule, fact, assumption,
  or conclusion of its snapshot, wrap it in a small chip that opens the same
  inspector against that snapshot, resolving kind and literal polarity
  unambiguously. Because the prompt discourages identifiers, this fires
  rarely and never replaces the referenced-items line.
- **Without documents.** When the scenario has neither bundled references nor
  attached sources, the panel shows one line above the composer, "No reference
  documents attached. You can ask about this scenario's statements, rules, and
  computed labels.", and answers show no Sources section; the referenced-items
  line still appears when the question selected items. The wording describes
  what can be asked rather than guaranteeing how answers are grounded, which
  a prompt cannot promise. The chat placeholder becomes "Ask about this
  scenario, a rule, or a conclusion...". The Sources reader (P09) shows the
  same sentence in place of the document list and keeps the Glossary tab.
- **Consistency check for the editor and reader.** The documents table (P22)
  and the reader (P09) treat "no documents" as a normal state with an empty
  state, not an error, and the submission summary (P24) says "No reference
  documents" explicitly.

### 6.6 Sources reader

**P09. A reader for the corpus.** Reachable from the scenario menu ("Sources and
glossary") and from every evidence card (P29). A right-side sheet (or a full dialog on
narrow screens) with a document list on the left (bundled corpus and uploaded
sources, with sizes) and the document text on the right, plain and searchable,
with the cited range highlighted when opened from a citation and the same
verification rule as the cards (P29): highlight only a confirmed location,
otherwise show the excerpt and say the location is unconfirmed. A "Glossary"
tab in the same sheet shows the symbol table in a real table (symbol, meaning,
negated meaning) instead of a textarea, with "Edit in scenario editor" for
projects. This turns a button nobody needs into the place where the demo's
claim of corpus-grounded answers becomes visible. The export already embeds
full document text, so the data is available; reuse the authorized export or
snapshot paths rather than a new unauthenticated route, clear any reader state
on account changes, and treat source URLs as citation metadata that is never
fetched. The reader ships in the same phase as the evidence cards so that
"Open in Sources" never points at a future feature.

### 6.7 First-run guidance

**P10. An "About this scenario" strip.** Under the top bar, a collapsible line
with the scenario description (the Popov paragraph), remembered per browser.
Newcomers get the story; presenters can collapse it. Add three quiet
suggestions to the chat empty state, generated from the loaded scenario rather
than written for Popov: "Explain <first accepted key conclusion>", "Try
activating <first inactive assumption> and preview the change" when one
exists, and "Ask which sources support <a key conclusion>" only when the
scenario has documents. Each is a real action. No tour, no overlay.

### 6.8 Visual system

**P11. Typography.** The substantive change is the scale, and it applies with
the system stack. Build the scale first, then evaluate a self-hosted pair at
the prototype review with both options side by side: IBM Plex Sans (weights
400, 500, 600) for interface text and IBM Plex Mono (400, 500) for identifiers
and ASPIC- text, as Latin-subset woff2 files under `app/static/vendor/fonts`
with the OFL text beside them, following the convention used for dagre,
marked, and DOMPurify. The deployed policy already allows this (`font-src
'self'` in `app/api/main.py:299`), the offline conference capture is
unaffected, and the system stack remains the fallback with `font-display:
swap`. The recommendation stands; the decision is taken on the rendered
prototype, not on this document. The size floor below is a design choice for
projected legibility, not an accessibility rule. Scale: 15 px reading
text in lists and dialogs, 14 px controls, 13 px captions, 12 px minimum for
badges and ids, 17 px panel titles in title case with a muted count, 20 px
dialog titles. Line height 1.5 for sentences, 1.3 for controls.

**P12. Color.** Keep the accent and the status palette exactly. Define tokens
for three surfaces (canvas, panel, raised), two borders (hairline, strong), and
three text levels. Remove the twelve category tints in favor of one muted text
color for category labels (they are metadata, not status). Reserve green and
red for the trial meter and example status only. Keep violet for "changed" and
amber for stale chips and notes. Keep the two game-bar colors and name them in
the legend (P06). Verify contrast for every text-on-tint pair and simulate the
common color-vision deficiencies when the tokens are finalized; the current
palette is a good starting point, not proof. Provide a dark theme later
through the same tokens; it is not needed for the conference.

**P13. Elevation and shape.** Shadows only on menus and dialogs. Lists use
hairlines and hover tints. Radii: 6 px for controls, 10 px for dialogs and
menus. Primary button: filled accent, one per view. Secondary: outlined.
Tertiary: text only, used for per-row actions. The "?" keeps its circle but
adopts the tertiary color until hover. A small set of inline SVG icons (menu
chevron, overflow, refresh, close, external) is reasonable and needs no policy
change; icons always accompany a text label or an accessible name.

**P14. Toasts and status.** Status messages appear as a slim banner directly
under the top bar, full width and sized to its content, pushing content down
so they never cover a control, and they announce through the existing live
region. Errors persist until dismissed; successes fade after 5 seconds; an
action inside a banner (Undo, Open example) is never timer-only, and errors
that belong to a form stay beside the form.

### 6.9 Responsive behavior

Two rows for the top bar below 780 px (name and status; then the three menus).
Conclusion rows stack (stripe and pill above the sentence, actions below) below
1100 px. On phones, keep the current 780 px stacking; the stacked conclusion row
removes the worst of U39, and the "?" reveal behavior required by R10 is
unchanged. A bottom tab bar (Conclusions, Facts, Rules, Chat) is deferred
(section 7, decision 6). Laptop zoom (1152 and 1024 effective widths) and the
780 px stacking are checked in every phase, not at the end.

### 6.10 Naming table

| Current | Proposed | Note |
| --- | --- | --- |
| New / Open | Scenario menu: New scenario, Import scenario file | Dialog titled the same as the item |
| Your scenario / Edit private scenario (dialog) | New scenario / Import scenario / Edit scenario | |
| Sources & glossary / Edit scenario (button) | Sources and glossary (reader), Edit scenario (menu item) | U03 |
| Download current scenario | Download scenario (.json) | Scenario popover and Save menu; available signed out; removed from the editor footer |
| Compact (switch) | Group by category (panel menu) | Default off |
| Show ASPIC- / ASPIC- Rules | ASPIC- text (button and dialog) | |
| View Graph / Conclusion overview | Conclusion graph (button and dialog) | R13 |
| Reset | Reset (inline with "Modified: n changes") | Disabled at zero |
| AI: Claude Sonnet 5 and Funded: Claude Sonnet 5 | AI: Claude Sonnet 5 (one chip) | |
| Workspace / Research workspace | Account menu; Manage projects dialog | |
| Codex and Claude (tab) | Agent access (Codex, Claude Code) | |
| AI access for this browser tab | AI access | Keep the tab-only note as a sentence |
| Funded model profile | Model | |
| Save project / Save changes | Save (split button; "Save a copy" on shared views) | |
| Restore administrator view (button) | Account menu item; "Normal user view" chip stays | R16 |
| Inspect (conclusion) | Derivations tab in Explain; id link | R13 |
| Inspect (rule) | Id link; "Inspect derivations" in row menu | |
| Inspect evidence (n) | Sources (n), plus one "Referenced items" line | P29 |
| [r1] stronger / Same strength / [rp] stronger | Prefer r1 / Equal priority / Prefer rp | P05 |
| Inspect derivations (graph) | removed; nodes are clickable | P07, U76 |
| Modify | Modify with AI (row menu) | |
| + Fact, + Assumption, + New Rule | + Add (Fact, Assumption), + Add rule | |
| Explain (dialog title "Explain: ...") | unchanged | Abstract vocabulary |
| Has to be the case / Can be the case that | unchanged, with legend | Abstract vocabulary |
| Continue (Explain) | removed; Next open branch when needed | U21 |
| New conversation (record title) | Untitled conversation | Until the first question |
| Edit and fork with current scenario | Fork with current scenario | R11 |
| Scenario used for this question | Asked about <scenario>, <n> pending changes | |
| Chat & Exploration | unchanged | R14 |
| Suggest as example / Example submissions / Submit for review / Submitted snapshot / Withdraw request | Suggest as a community example / Community examples / Submit / Suggestion / Withdraw | P24 |
| Review snapshot / Approve & publish / Remove from examples | Review / Publish / Unpublish | P25 |
| Administrator view / Use normal user view | Demonstrate as a normal user; chip "Normal user view · Restore" | P27, R16 |
| Archive (project) | Archive, with an Archived filter and Restore | P23 |
| Your scenario / Edit private scenario | New scenario / Import scenario / Edit: <project name> | P16 |
| Rule 1, Rule 2 (editor legends) | rule id and rendered sentence | P19 |

### 6.11 Authoring, projects, and community examples

**P16. Editor entry states.** "New scenario" opens an empty draft with an empty
state in the Statements section ("No statements yet. + Statement, or Try the
picnic example") and no placeholder rows; "Import scenario file" opens the same
dialog with the dropzone first; "Edit scenario" opens with the title "Edit:
<project name>", no New/Import tabs, no starter or clear line, a "Discard
editor changes" action in the footer (projects have no browsable version
history to revert to), and the Background expanded whenever it has text. The dialog subtitle names the outcome: "Saves as a private project"
or "Updates this project (version 4)".

**P17. Readable identifiers by default.** Propose an id once, when a statement
or rule row is first completed (first four words of the description,
lowercase, underscores, unique suffix when needed: `forecast_sunny`,
`hold_picnic_outside`, `rule_forecast_sunny`), then keep it stable: an id that
rules may already reference is never regenerated while the user keeps typing.
Imported ids are preserved. Show the id as muted text on the row with a
Rename action beside it rather than an always-visible field, and route every
later change through the existing atomic rename, which rewrites negative
literals and undercuts. The explorer, ASPIC- text, chat tokens, and citations
then read sensibly for every user scenario.

**P18. A searchable statement picker.** Replace the native selects in rule
cards with a combobox: type to filter, results grouped "Statements", "Negated",
"Rule does not apply", keyboard navigable, and the chosen statement shown as a
chip with a "not" toggle instead of separate negated entries. Show the rule's
rendered sentence live above its fields ("If the forecast is sunny then usually
we should hold the picnic outside"), using the explorer's rule rendering, so
the user reads what they built.

**P19. Structure for long scenarios.** Group statements under collapsible
headers with counts (Facts 19, Assumptions 20, Claims 24), add a filter box,
collapse each row to one line (kind, sentence, id) that expands on click, title
rule cards by id and rendered sentence instead of "Rule N", and announce the
Rule text switch for very large scenarios with a banner that says what still
works. The guided limit can stay.

**P20. Inline validation and a self-explaining save.** Show each error beside
its field with a red outline and a "Go to problem" link, and a count in the
footer ("2 problems"); collapsed rows that contain an error expand. Replace
the disabled "Save & open" with an actionable "Check & save" while the draft
is unchecked: it runs the deterministic validation; a valid manually authored
draft with no warnings saves at once, without a further approval merely
because its results were not viewed; a draft with warnings shows the preview
and asks for the final save decision; errors never permit saving. The button
still respects authentication, read-only views, pending saves, version
conflicts, and invalid input, which are the reasons it may be disabled, and
each of those states says so beside the button. Keep "Preview" as a separate
action for users who want to look first. Model proposals keep their explicit
preview-and-apply step. Render preview results with the explorer's status
pills and rule rendering through display-only helpers, not the live explorer
controls, so nothing in the preview toggles the open scenario.

**P21. Import by content, not filename.** Suggest the role of each file from
its content (YAML or JSON envelope, ASPIC- arrows, "symbol = meaning" lines,
otherwise a document), show the suggestion in the role select, and require
the user to confirm ambiguous text files rather than silently treating prose
that happens to contain arrows as rules. Server validation and capacity limits
are unchanged. Show size and, for PDFs, the page count reported by the upload
preview; keep the file list after loading with a check mark per file; place
the status message beside the dropzone. For a complete scenario
file, offer "Open as project" directly and run the check invisibly, showing
the preview only when there are warnings.

**P22. Documents as a table.** List documents as rows showing what the system
actually retains (name, type, characters and kilobytes of extracted text, and
the page count only while the upload preview reports it, since original PDFs
are not stored) with Open (in the Sources reader, P09, for review), Replace,
and Remove; make paste a small form; show capacity as a bar of retained text
("112 KB of 750 KB of reference text"), distinct from upload size.

**P23. Projects tab.** List first. A compact "Open project" strip at the top
with Save changes and a "..." menu; the "save as new" form becomes a "Save a
copy..." action. Project cards show the source example, the last saved time,
and status chips ("Shared · 1 link", "Suggested · awaiting review",
"Published"), with a "..." menu (Open, Rename, Share, Suggest or Publish,
Download, Archive). Add an "Archived" filter with Restore (section 7, decision 10). Restore is
not a one-field update: archiving leaves share links in place and only the
resolution check excludes archived projects, so clearing `archived_at` would
revive every old link. The route restores privately, revokes the project's
share links, requires new links to be created explicitly, and preserves
ownership, the active-account check, the version increment, concurrent-update
protection, and the active-project limit.

**P24. Submission dialog, for users and administrators.** Three parts, top to
bottom: a summary header (public title, editable, prefilled with the project
name; one-line public summary, editable, prefilled from the first sentence of
the background and shown next to the full background so that shortening the
summary never implies the background was redacted; counts; documents with
sizes and the statement that they are published in full; "Saved version 3,
8:10 PM"; an optional note to the reviewer), then the consent checkbox and the
primary button together in the sticky footer so the enabling control and the
action are never apart, then a collapsed "Everything that will be published"
section rendered with the explorer's components and the exact public payload
still inspectable. The editable title and summary are a bounded data
addition: both belong to the immutable published snapshot at submission time,
the private project description stays private, reviewer notes stay private,
and the existing one-submission-per-project-version rule applies to metadata
edits as it does to content. Names: "Suggest as a community example" (button), "Community
examples" (tab), "Submit" (primary), statuses "Awaiting review", "Published",
"Declined", "Withdrawn". Show the status chip on the project card and a count
on the tab.

**P25. Review queue.** A segmented filter with counts ("Awaiting review 1 ·
Published 3 · Declined · Withdrawn · Mine") and cards with the submitter's
display name and the submission date; both the counts and the name are an
authorized summary added to the queue response for administrators only. The
review dialog keeps the note field and the three actions together in a sticky
footer; Decline marks the empty note inline ("Add a short reason for the
author"); Approve keeps its single affirmation but renders it as an in-dialog
bar ("Publish this exact snapshot as a public example? Publish · Cancel")
instead of `window.confirm`; after approval the toast carries "Open example"
and the list stays on the queue for the next item. Publication dates and
statuses come from the submission record and are tied to the submitted
version, so publishing an earlier snapshot never labels newer private edits as
public.

**P26. Direct publication.** Both paths already have exactly one informed
affirmation: the administrator's own publication has the consent checkbox and
the Publish button, and approval of someone else's submission has the Approve
button and its confirmation. Keep one affirmation on each path; do not add a
second one for symmetry. Removing one's own example does not require a note
to oneself, but the removal is still recorded in the submission history.

**P27. Normal user view without a top-bar button.** Remove the
"Restore administrator view" button from the bar. The status group (P02)
shows a persistent chip "Normal user view · Restore" while the mode is active,
which is the one-click return R16 requires, and the account menu (P03) carries
"Demonstrate as a normal user" and "Restore administrator view". The Account
card keeps the toggle and lists what changes: "You will not see the review
queue or Publish as example, and your own suggestions go through review like
anyone else's. Projects, credit, and conversations are unchanged." Cross-tab
sync, refresh persistence, and the sign-out reset stay as they are.

**P28. Community examples in the switcher.** Show a "Community" tag and the
publication month; show the submitter's display name only when they opted in
at submission, never an email address; an opened community example shows
"Community example" in the status chip instead of "Example". Attribution is an
explicit, optional field of the published snapshot (P24).

## 7. Requirement constraints and decisions

Constraints the proposal respects:

- **R14** preserves the visible "Chat & Exploration" heading, the modified
  count and Reset, changed-label highlighting, and the "Premises and
  subarguments" wording; all stay. If the heading were ever renamed (for
  example "Ask & explore"), that is a change to R14, not a design choice.
- **R10** requires the "?" control on every item and the insert-into-composer
  behavior; the proposal keeps the control visible and only varies the
  generated sentence by kind, which is compatible with "the same generated
  question" as long as the same item always yields the same sentence.
- **R13** requires distinguishable individual derivations; moving the
  inspector into a tab of the Explain dialog keeps it one click from every
  conclusion and rule.
- **R16** requires a visible way to restore the administrator view; the
  persistent chip plus the account menu item satisfy it.
- **R01** requires the four-panel explorer, the game, glossary, graph, ASPIC-
  view, and bundled examples to remain usable; nothing is removed.
- The extended abstract names "New / Open", "View Graph", "Show ASPIC-",
  "Inspect", "+ Fact", "+ Assumption", "+ New Rule", "Modify", and
  "Workspace > Account / AI access". If the naming table is adopted, the
  abstract's "Using the Demo" and "New Features" sections need the matching
  wording before the camera-ready extended version is frozen.

Decisions

Haoyang asked for recommendations rather than open questions, so this review
takes the following decisions. They incorporate David's response where the
code supported it (see "Status after consolidation"). Each can be reversed,
but the plan in section 8 assumes them.

1. **Top bar: a scenario popover and three controls, not a grouped toolbar.**
   A grouped toolbar still wraps below about 1150 px, the effective width of
   a projector at 125 percent zoom, and keeps eight controls on the first
   screen. The popover is a selection listbox plus a separate row of action
   buttons (commands are never list options, and focus never loads a
   scenario); the AI chip, the Save split button, and the account menu are
   ARIA menus reusing the focus management the dialogs already have. No
   control used during the rehearsed narrative sits inside them. The one-row
   fit at 1024 px is a target verified with long names, larger fonts, every
   access state, and the normal user view; two clearly grouped rows are
   acceptable where they preserve usable space.
2. **Sources reader: build it, in the same phase as the evidence cards.** The
   span-in-context cards (P29) and the reader (P09) ship together so that
   "Open in Sources" never points at a future feature. Both highlight only a
   verified location and say when a location cannot be confirmed, because chat
   and export extract PDFs differently. Aligning the two extraction paths is
   a separate decision with its own qualification consideration.
3. **Reset: no confirmation, a bounded Undo, and no effect on the
   conversation.** A reversible action should not ask permission. Undo
   restores exactly the captured operations against the captured baseline and
   stays available until an incompatible transition (another edit, a switch,
   a save, a reload) invalidates it; it does not depend on a timer. Reset is
   disabled at zero changes. Switching to another example or project keeps
   starting a new conversation, and the previous conversation stays in the
   menu.
4. **Explain vocabulary: keep the game terms, add the role.** The card bars
   read "Proponent · Has to be the case:" and "Opponent · Can be the case
   that:", with one legend line. Candidates that share a top rule are
   distinguished by a premise, not only by "via r1". Auto-resolution touches
   only terminal leaves.
5. **Fonts: the scale first, the family at the prototype review.** The type
   scale in P11 is the substantive legibility change and applies with the
   system stack. Self-hosted IBM Plex Sans and Plex Mono remain the
   recommendation (the policy already permits them, the vendor directory
   already carries license texts, and the subset files are about 200 KB), and
   the decision is taken with both options rendered side by side rather than
   in advance.
6. **Phone layout: defer the bottom tab bar.** The conference demo runs on a
   laptop, and the stacked conclusion row that laptop widths need already
   removes the worst phone problem. Laptop zoom and the 780 px stacking are
   checked in every phase.
7. **Save is a direct action with a secondary menu.** The button reads "Save"
   and acts at once in every state (signed out it opens the account menu with
   one sentence; on an example it saves a new private project; on a project it
   saves changes and is disabled when clean; on a shared view it is "Save a
   copy"). Share, Suggest, Download, and Export live under its chevron, and
   Download and Export stay available signed out.
8. **Conference freeze from the rehearsal date.** Take the freeze date from
   the actual rehearsal schedule. The minimum before the freeze is phases 1
   to 3 (defects, top bar and naming, legibility), followed by both
   rehearsals and a fresh offline capture; everything after that is scheduled
   from the remaining time, with phases 4 and 5 next.
9. **Composer: build the token composer (P15), after legibility, with no
   interim synchronization.** The two-copy draft is the root cause of U47 and
   the token model is what the "?" flow needs on stage: one visible object per
   referenced item, inside the question. It is Haoyang's explicit request.
   David's objections change its shape, not its place: the segment model is
   stored with each message so forks are exact; click-to-unwrap keeps a
   visible affordance and Undo; paste is plain text by design; Enter never
   sends during composition. The interim idea of removing a chip when its
   sentence disappears is withdrawn because it breaks the tested workflow of
   keeping references while rewriting the question. Until P15 ships, the
   chip strip is relabeled "Referenced items" with a one-line explanation.
10. **Archive: add Restore with share-link revocation.** Restore is a small
    owner-scoped route, but it must revoke the project's share links and
    require new ones, because archiving does not revoke them today and only
    the resolution check keeps archived projects hidden. "Archive" is not
    relabeled "Delete", since the data is retained; if the route is refused,
    the archive confirmation says that restoring requires a privacy request.
11. **Save gate: "Check & save", not a disabled button.** The deterministic
    check before saving is a genuine safeguard for a public service, so it
    stays; the button runs it, saves a valid warning-free manual draft at
    once, shows the preview only when there is something to decide, and
    states its reason whenever it is genuinely unavailable (P20).
12. **Submission dialog: summary and consent first, listing last.** The
    listing exists for diligence and should be available, not mandatory
    scrolling. The consent checkbox and the primary button sit together in the
    sticky footer (P24). Editable public title and summary, queue counts,
    submitter names, and attribution are bounded data additions with the
    fields specified in P24, P25, and P28; they are not prerequisites for the
    visual work.
13. **Evidence leads with corpus text; formal context shrinks to one line.**
    Source cards are the evidence; the selected items appear once as a
    "Referenced items" line that opens the saved derivation, because the chat
    prompt keeps identifiers out of answers and R12 asks that formal
    references stay identifiable; inline identifier links are a supplement
    (P29). Explain and Inspect remain the formal entry points in the explorer.
14. **Scenarios without documents are a normal state.** Every feature already
    works without a corpus; the interface says so in one sentence in the chat
    panel, the reader, the editor, and the submission summary (P29, P22, P24),
    worded as what can be asked rather than as a guarantee about answers.
15. **Dialogs never stack visibly; navigation replaces.** The graph defect
    (U76) gets the general stacking fix (ordered z-index, inert lower
    dialogs, focus restoration) in phase 1, because the playbook demonstrates
    the graph, and the clickable nodes with "Back to graph" in the dialog
    phase (P07).
16. **Fix the input-method defect first.** The Enter handler gains an
    `isComposing` guard and a regression test in phase 1 (U77), and the token
    composer inherits the same rule.
17. **Presentation changes do not trigger paid model evaluation.** Where a
    change alters model inputs (question templates, source extraction), its
    effect is assessed on the existing chat cases before it ships; prompts
    stay unchanged unless behavior warrants tuning. Paper wording and the
    offline demonstration captures are updated after the interface settles.

## 8. Suggested order of work

The order follows decision 8 and David's sequencing: defects first, legibility
before the composer, the reader with the chat phase, and responsive checks in
every phase. The authoring and curation flows follow the chat work because
they are the demo's most important new features and the least reviewed by the
browser tests for design.

1. **Defects and quick clarity fixes** (U76 stacking fix with inert lower
   dialogs and focus restoration, U77 `isComposing` guard, Reset without a new
   conversation plus bounded Undo, the "Referenced items" relabel and its
   one-line explanation for U47, the no-documents line for U75). Targeted
   regressions for each; no design change.
2. **Naming and the top bar** (P01 to P03, P10, P14, P27, U01 to U11, U71 to
   U73): the scenario popover, the three controls, the status banner, the
   "About this scenario" strip, the normal-user-view chip. Mostly
   `index.html`, `style.css`, and the wiring in `workspace.js` and
   `scenarios.js`; update the browser tests that click "New / Open", "Sources
   & glossary", "Workspace", "Save project", and the compact switch.
3. **Legibility** (P04, P05, P11 to P13, U12 to U19, U41 to U45): CSS tokens,
   the type scale with the system stack, the conclusion row, the split
   filters, the row overflow, contrast verification; the font pair evaluated
   at this phase's prototype review; laptop zoom and 780 px checked here and
   in every later phase.
4. **Composer tokens** (P15, U47): the self-contained module replacing the
   textarea and the chip strip, message-level segment storage, and the
   exploration browser tests, including keyboard, selection, undo, IME, and
   mobile cases.
5. **Chat presentation, evidence, and the Sources reader** (P08, P09, P29,
   U27 to U32, U74, U75): conversation menu, per-turn line, source cards with
   verified locations, the referenced-items line, identifier links, the
   reader, explanatory question templates with their model-input assessment.
6. **Authoring editor** (P16 to P22, U48 to U58): entry states, identifiers
   proposed once, the statement combobox, grouping, inline validation, "Check
   & save", import suggestions, and the documents table.
7. **Projects and community examples** (P23 to P26, P28, U59 to U70): the
   Projects tab, Restore with share-link revocation, the submission dialog
   with its bounded metadata contract, the review queue with authorized
   summaries, and direct publication.
8. **Game and graph interactions** (P06, P07, U20 to U26): Explain
   auto-selection with distinguishing premises, terminal-only auto-resolution,
   the role legend, graph labels and the labeled isolated-node filter,
   clickable nodes with "Back to graph", and the shared Explain and
   Derivations frame with explicit bundle scoping.
9. **Responsive refinements beyond the per-phase checks** (U39, U40): the
   phone tab bar, if wanted, after the conference.

Each phase re-runs the browser suite in Chromium, Firefox, and WebKit where
available with `ABDA_BROWSER_TESTS=1` and the axe scans; the acceptance list
adds long labels, zoom, keyboard focus, IME, historical answers, no-documents
scenarios, offline fonts, and both account views. The conference offline
capture script is regenerated after phase 3, since its six screenshots will
change, and again after any later phase that ships before the freeze.

## Appendix A. Measurements

Taken with Chromium against the local demo at `02c77dc`, Popov v. Hayashi,
signed out, default filters.

| Measurement | Value |
| --- | --- |
| Visible interactive controls at first load, 1440 x 900 | 125 (140 with the "All" conclusion filter) |
| Distinct visible button labels | 48 |
| Controls in the top bar | 11 visible, 12 including the hidden administrator button |
| Controls in the Conclusions panel (Key filter) | 30 |
| Controls in Facts & Assumptions | 36 |
| Controls in Rules | 36 |
| Controls in Chat | 8 |
| Root font size / body font size | 16 px / 15 px |
| Rule text / fact text / conclusion label | 13.1 / 12.5 / 13.4 px |
| Status block / category badge / inline id | 10.2 / 9.3 / 10.6 px |
| Filter pills / small buttons / storage note / lab label | 10.9 / 11.2 / 11.0 / 9.3 px |
| Conclusion label width at 1440, 1366, 1280, 1024 | 251, 223, 191, 80 to 90 px |
| Lines per conclusion label at those widths | 2, 2, 2 to 3, 4 to 6 |
| Status block width | 88 px (5.5 rem) |
| Top bar wrapping | policy links wrap at 1280; two rows at 1100 and 900; three rows at 780 |
| Toast position and duration | fixed, top 4.2 rem, right 1 rem, 420 px, 6 s (9 s errors) |

## Appendix B. Code pointers

| Topic | Location |
| --- | --- |
| Top bar markup | `app/static/index.html:14-47` |
| Chat header and toolbar | `app/static/index.html:119-134` |
| Workspace tabs | `app/static/index.html:168-174` |
| Editor footer with download | `app/static/index.html:558-566` |
| Scenario select and view context | `app/static/app.js:297-333`, `348-378` |
| Reset and conversation reset | `app/static/app.js:485-505`, `1328-1347` |
| Conclusion cards | `app/static/app.js:774-835` |
| Fact and rule cards, category palette | `app/static/app.js:973-999`, `1262-1301`, `922-964` |
| Compact toggle | `app/static/app.js:966-971` |
| Conflicts view | `app/static/app.js:1096-1258` |
| Chat rendering and send | `app/static/app.js:1399-1613` |
| Error banner | `app/static/app.js:1630-1642` |
| Graph | `app/static/app.js:1875-2370`; inspect button `2257`; node cursor `style.css:1699-1701` |
| Dialog open, close, stacking, Escape | `app/static/workspace.js:42-144`, `app/static/app.js:2493-2499`, `style.css:1204-1210` |
| Explain dialog, picker, tree, moves | `app/static/app.js:2455-2491`, `3224-3285`, `3392-3507`, `3604-3747` |
| Edit dialogs | `app/static/app.js:2512-2822` |
| Workspace wiring, chips, toasts, access | `app/static/workspace.js:22-33`, `146-196`, `681-742` |
| Projects tab | `app/static/workspace.js:789-868` |
| Conversation controls and storage note | `app/static/exploration.js:243-268` |
| Per-turn controls and fork | `app/static/exploration.js:352-405` |
| Question drafting and chips | `app/static/exploration.js:440-511` |
| Evidence rendering | `app/static/exploration.js:513-551` |
| Formal evidence assembly, empty-corpus prompt | `app/llm/chat_service.py:584-593`, `622`, `671`; `app/llm/corpus.py` (`build_corpus_block`) |
| Chat prompt rule on identifiers | `app/prompts/chat_system.md:27` |
| PDF extraction, chat versus export | `app/llm/corpus.py:38-62`, `app/scenario/portable.py:29-35` |
| Share-link resolution and archive | `app/services/projects.py:252-266`, `394-412` |
| Enter handler without composition guard | `app/static/app.js:197-202` |
| Two-references-one-question browser test | `tests/test_exploration_browser.py:140-160` |
| Derivation inspector | `app/static/exploration.js:585-663` |
| Sources & glossary dialog | `app/static/materials.js:131-204` |
| Document editor (SourceEditor) | `app/static/materials.js:6-102` |
| Editor draft defaults, ids, statement rows, rule cards | `app/static/scenarios.js:307-321`, `323-371`, `385-457` |
| Editor validation, preview, import roles | `app/static/scenarios.js:474-494`, `510-575`, `577-642` |
| Community submission, review, publication | `app/static/curation.js:113-139`, `141-214`, `216-257` |
| Administrator view toggle and indicators | `app/static/workspace.js:296-385`, `app/static/index.html:24`, `39`, `203-212` |
| Project archive query | `app/services/projects.py:96-100`, `255-266` |
| Community catalog entry | `app/services/scenario_submissions.py:235-261` |
| Editor entry points and download | `app/static/scenarios.js:108-195`, `703-719` |
| Tokens, body, top bar, buttons | `app/static/style.css:4-30`, `93-152` |
| Panels, cards, badges, keywords | `app/static/style.css:160-335`, `423-428`, `545-730` |
| Chat panel | `app/static/style.css:732-826` |
| Workspace and editor dialogs | `app/static/style.css:827-1011`, `1229-1343` |
| Breakpoints | `app/static/style.css:1012-1067`, `1326-1343` |
| Explain and graph styles | `app/static/style.css:1562-2023` |
