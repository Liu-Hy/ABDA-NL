# Proposal: reconstructed knowledge bases for three preloaded scenarios

Consolidated version, September 10, 2026. Author: Tim (Claude), for Haoyang
Liu. Incorporates David's response
(`docs/scenario-reconstruction-response-20260910.md`). Reviewed
implementation: development branch at commit `ee3cb37`. This is a proposal;
nothing has been changed under `examples/`.

**Scope requirement (Haoyang).** The revisions proposed here replace only the
content of the three scenarios: their facts, assumptions, propositions, key
conclusions, and rules, plus, optionally, the text of existing corpus files.
They do not change the engine, any feature, the interface, the scenario
format, or anything that would make these three scenarios behave differently
from the other bundled scenarios under the same infrastructure. Every
mechanism used below (strict and defeasible rules, negation, undercuts,
blocks, inactive assumptions, categories, free-text `source` fields) is already
used by the current bundled scenarios. Where one of David's comments would
need something more than content, this document says so and stops there.

## Status after consolidation

David agreed with reconstructing the three scenarios, reproduced every table
of the first version, and raised seven points. I accepted six of them in full
and one in part; the knowledge bases below are revised accordingly and every
table was recomputed with the engine.

| David's point | Resolution | What changed |
| --- | --- | --- |
| 1. Repair the source material; do not cite guidelines as the source of patient facts; drop the unverified Wikipedia claim. | Accepted in part. | Patient, site, and team facts now cite the fictional brief they come from (the scenario description, the local news article, the front-office memo), not a guideline. The two corpus sentences that say COGENT tested pantoprazole (it tested omeprazole) are listed in section 5 as text corrections; they are content, and the knowledge bases work with or without them. The claim that every rule has equivalent Wikipedia support is removed. Replacing the corpora with real documents stays outside this proposal. |
| 2. PPI Therapy conflates continuing acid suppression with continuing the current drug; specify the drug; reassessment is not discontinuation. | Accepted. | The current drug is omeprazole (a fact). The decision splits into three exclusive-where-needed conclusions: stay on acid suppression, keep omeprazole unchanged, substitute pantoprazole. The interaction rule is omeprazole-specific. The bone line now concludes periodic reassessment at the lowest effective dose and attacks nothing, so the exception rule is gone. The pantoprazole toggle, which contradicted the new fact, is replaced by "pantoprazole is contraindicated". |
| 3. Prescribed Burn mixes "this cycle" with "today"; permission should be a prerequisite of an executable recommendation; the categorical rule is not a universal EPA prohibition. | Accepted. | Two decisions: treat the unit this cycle, and go ahead on the planned burn day. Permission is a premise of the second, so an exceedance day withholds the permit and rejects the day's burn without touching the treatment question. David's case (permit off, ecology preferred) now gives treatment accepted and both permission and the day's burn absent. The strict rule is attributed to a stipulated condition of a fictional state Smoke Management Program. |
| 4. NBA Rebuild never relates tanking to competing; the lottery undercut targets the wrong concept and omits the bottom-three qualification; the apron needs transaction context. | Accepted. | Tank and compete are exclusive through two strict rules; stacking is not tied to competing. The flattening now undercuts the extra-losses inference, the fact carries the bottom-three qualification, and expansion revives tanking through scarcity of cornerstone talent rather than through odds. The apron is an applicability prerequisite of the stacking plan: an assumption "the acquisition can be structured under the second apron", off by default because the memo says it cannot. The strict apron rule and the block 4 device are gone. |
| 5. Relax "every toggle must change a headline decision"; findings can be key conclusions. | Accepted. | The design rule now reads "every toggle changes a visible label, and the changes are the ones the description promises". The two findings that a toggle disputes (`eco_benefit`, `cardiac_interaction`) are key conclusions. David's teaching sequence (prefer ecology, then a recent burn) is in the tables. |
| 6. State categorical constraints as bounded modelling choices. | Accepted. | Section 3 states exactly what the guarantees cover. In Prescribed Burn the guarantee for the day's burn now depends only on the permit rule's block, because permission is a premise; in NBA Rebuild the prerequisite form makes stacking simply unavailable without the assumption. Unconditional applicability would need engine support and is out of scope under the requirement above. |
| 7. Write behavioural assertions before snapshots; do not rewrite historical records; preserve projects; rerun evaluations within budget. | Accepted. | Section 6 is rewritten. |

Held: the baseline of PPI Therapy leaves both "keep omeprazole" and
"substitute pantoprazole" undecided. That is the intended teaching state (the
guidance and the continuity default are in equal-strength conflict until the
committee sets a preference), not a defect; the tables show that either
preference, or either toggle, resolves it. Key conclusions remain mostly
decisions, with the two disputed findings added as David suggested.

## 1 What is proposed

Replace the ASPIC- knowledge bases of **PPI Therapy**, **Prescribed Burn**, and
**NBA Rebuild** with the three files in section 4. Each keeps its title,
corpus list, and decision story, with fewer rules than today and key
conclusions that are decisions or disputed findings. Each file was loaded
through the production loader and exercised with the embedded engine; the
behaviour tables in section 4 are computed, not predicted.

| Scenario | Current | Proposed |
| --- | --- | --- |
| PPI Therapy | 6 facts, 2 assumptions, 2 propositions, 7 key conclusions, 16 rules (20 arguments, 7 attacks) | 4 facts, 2 assumptions, 2 propositions, 6 key conclusions, 13 rules (15 arguments, 9 attacks) |
| Prescribed Burn | 7 facts, 3 assumptions, 2 propositions, 6 key conclusions, 15 rules (23 arguments, 8 attacks) | 6 facts, 3 assumptions, 3 propositions, 4 key conclusions, 11 rules (17 arguments, 6 attacks) |
| NBA Rebuild | 8 facts, 2 assumptions, 0 propositions, 8 key conclusions, 15 rules (21 arguments, 10 attacks) | 6 facts, 2 assumptions, 4 propositions, 3 key conclusions, 15 rules (19 arguments, 15 attacks) |

Popov v. Hayashi is not part of this proposal: its knowledge base transcribes
Prakken's published reconstruction of the case. The two Fried Chicken
scenarios are not part of it either: they are the group's own four-argument
teaching example.

## 2 Why these three

The three scenarios and their corpora entered the repository together in commit
`7452f26` (June 30, 2026) and were built with LLM help rather than curated by
domain experts or extracted from real documents. The evidence is in the files:
every corpus document is labelled "paraphrased excerpts", "illustrative
composite", or "not a real article"; two corpus files explain how their content
should be modelled ("for formal modeling, this is captured as a strict rule");
and the scenario descriptions discuss the interface ("the three-way radio in
the Conflicts view genuinely flips crispy's outcome"). The corpus was written
to justify the rules, not the other way round, and it carries factual errors
that the chat model can repeat (section 5).

| Scenario | Specific problems in the current knowledge base |
| --- | --- |
| PPI Therapy | A strict rule that only renames a fact. A rule saying that being on long-term therapy denies that Barrett's is an indication, a non sequitur that exists to be defeated. A pharmacological fact derived from the patient's stent. The bone line neutralised twice. Three findings among the key conclusions. Paraphrased guideline citations carried as exact authorities. The scenario never names the drug, although the interaction guidance is drug-specific. |
| Prescribed Burn | The "categorical" PM2.5 strict rule never wins (its assumption sits at block 1, the permit argument at block 2), so the exceedance toggle changes nothing. A community request that exposure be "a material factor" encoded as burning being illegal. A manufactured pair on re-treatment intervals derived from being in the wildland-urban interface. `postpone_burn` accepted beside `conduct_burn` undecided with no relation between them. |
| NBA Rebuild | The second-apron toggle changes nothing because stacking is already rejected. `lottery_math` and its negation derived from the same fact at the same block, purely to show an undecided label. Five of eight key conclusions are intermediate findings. Tanking and competing are never related. |

## 3 Engine facts, bounded guarantees, and design rules

Two engine behaviours shape the files. Both were confirmed by running the
engine; neither is proposed for change.

**Strength is the strongest rule.** ABDA-NL fixes the engine to weakest-link
comparison with democratic ordering. With totally ordered blocks, that set
comparison reduces to comparing the maximum block of each argument: an attacker
wins a rebut when its strongest defeasible rule is at least as strong as the
strongest rule of the sub-argument it attacks. Raising one rule's block in the
Conflicts view strengthens every argument that uses that rule anywhere.

**A strict rule is only as strong as its premises, and a rebut is judged
against the attacked sub-argument.** A strict rule cannot be undercut and adds
no defeasible link, but the argument it tops can be rebutted by an argument
that is not weaker. A categorical constraint switched on by an assumption is
therefore only as strong as that assumption's block. This is why the current
Prescribed Burn exceedance rule loses. Conversely, when a conclusion needs a
premise, an attack on the argument for that premise is judged against that
premise's own argument, whatever else the conclusion rests on.

What the proposed files guarantee, and what they do not:

- Prescribed Burn keeps a strict exceedance rule with the assumption at
  block 3. The permit argument sits at block 1, and permission is a premise of
  the day's burn. So an exceedance day rejects permission and the day's burn
  no matter how the treatment rules are preferred, including a manual raise
  of the ecology rule to block 4 (tested). The guarantee fails only if the
  permit rule or assumption itself is raised to block 3 or above, which the
  Conflicts view cannot do from baseline (it moves a pair one step above its
  baseline maximum) and which only a deliberate block edit can do.
- NBA Rebuild does not use a categorical rule at all. Stacking veterans is
  only derivable when the assumption "the acquisition can be structured under
  the second apron" is active, so with the assumption off (the memo's own
  finding) no preference can make stacking accepted. This is David's
  "applicability condition" form.
- Unconditional applicability, immune to any block edit, is not expressible
  in the current engine. Providing it would be an engine change and is out of
  scope under the requirement stated at the top.

Design rules used throughout: key conclusions are decisions, plus findings that
a toggle or a preference disputes; every fact is an observation with a named
source, and observations about the fictional patient, unit, or team cite the
fictional brief they come from; every assumption is a what-if whose toggle
changes a visible label in the way the description says; one rule per distinct
consideration, no pairs manufactured to display a label; undercuts for "this
consideration does not apply here", preferences for "this consideration
outweighs that one", strict rules only for exclusivity between options and for
a stipulated categorical condition; identifiers that read as English.

## 4 The three knowledge bases

Each file replaces the corresponding `examples/<dir>/scenario.yaml`. The
corpus lists are unchanged. Expected-label snapshots are regenerated with
`python -m app.cli.validate_scenario <dir> --update-snapshot` after the
behavioural assertions of section 6 are written.

### 4.1 PPI Therapy

Computed: 15 arguments, 9 attacks; the two strict rules are each other's
transposition. `be_indication` and `fracture_risk` are accepted in every state
below. Preferences are the Conflicts-view choice on the pair `keep_current`
versus `avoid_interaction`.

| State | continue acid suppression | cardiac interaction | keep omeprazole | substitute pantoprazole | reassess dose | escalate |
| --- | --- | --- | --- | --- | --- | --- |
| Baseline | accepted | accepted | undecided | undecided | accepted | accepted |
| `cogent_decisive` on | accepted | rejected | accepted | rejected | accepted | accepted |
| `pantoprazole_contraindicated` on | accepted | accepted | undecided | rejected | accepted | accepted |
| Prefer `avoid_interaction` | accepted | accepted | rejected | accepted | accepted | accepted |
| Prefer `keep_current` | accepted | accepted | accepted | rejected | accepted | accepted |
| `pantoprazole_contraindicated` on, then prefer `avoid_interaction` | accepted | accepted | rejected | rejected | accepted | accepted |

The last row is the committee's hard case: acid suppression must continue,
omeprazole should not, and pantoprazole is unavailable. Nothing in the file
resolves it, which is correct; the evaluation case that adds an H2 blocker
assumption ("propose-medical-alternative-assumption") is exactly the move that
would.

```yaml
title: "PPI Therapy"
description: >
  A hospital Pharmacy and Therapeutics committee reviews a fictional patient
  who has taken omeprazole long term for biopsy-confirmed Barrett's
  esophagus, takes clopidogrel after a recent coronary stent, and has low bone
  density on a recent DEXA scan. Acid suppression should continue because of
  Barrett's. Whether the omeprazole itself continues unchanged is undecided at
  baseline: the continuity default says keep it, the clopidogrel interaction
  says avoid omeprazole, and the pharmacy protocol says substitute
  pantoprazole instead. The bone finding calls for periodic reassessment at
  the lowest effective dose, not for stopping. Treating COGENT as decisive
  removes the interaction argument; a contraindication to pantoprazole
  removes the switch.

facts:
  barretts:
    description: the patient has biopsy-confirmed Barrett's esophagus
    category: GI
    source: fictional case brief in the scenario description
  on_omeprazole:
    description: the patient has taken omeprazole long term for acid suppression
    category: GI
    source: fictional case brief in the scenario description
  clopidogrel_post_pci:
    description: the patient takes clopidogrel after a recent coronary intervention
    category: cardiac
    source: fictional case brief in the scenario description
  low_bmd_postmenopausal:
    description: the patient is postmenopausal with low bone mineral density on a recent DEXA scan
    category: bone
    source: fictional case brief in the scenario description

assumptions:
  cogent_decisive:
    description: the COGENT trial is treated as showing that the omeprazole-clopidogrel interaction is not clinically meaningful
    negated_description: the COGENT trial is not treated as decisive
    category: cardiac
    source: cogent_trial.txt; a minority reading, off by default
    active: false
    block: 1
  pantoprazole_contraindicated:
    description: pantoprazole is contraindicated for this patient
    negated_description: pantoprazole is not contraindicated for this patient
    category: GI
    source: formulary_committee_protocol.txt ("switch to pantoprazole unless contraindicated"); off by default
    active: false
    block: 1

propositions:
  be_indication:
    description: Barrett's esophagus is a compelling indication for ongoing acid suppression
    negated_description: Barrett's esophagus is not a compelling indication for ongoing acid suppression
    category: GI
  fracture_risk:
    description: long-term proton pump inhibitor use materially raises this patient's fracture risk
    negated_description: long-term proton pump inhibitor use does not materially raise this patient's fracture risk
    category: bone

conclusions:
  continue_acid_suppression:
    description: the patient should stay on long-term acid suppression
    negated_description: the patient should not stay on long-term acid suppression
    category: decision
  cardiac_interaction:
    description: omeprazole clinically reduces the effect of clopidogrel in this patient
    negated_description: omeprazole does not clinically reduce the effect of clopidogrel in this patient
    category: cardiac
  keep_omeprazole:
    description: the current omeprazole should continue unchanged
    negated_description: the current omeprazole should not continue unchanged
    category: decision
  switch_to_pantoprazole:
    description: the committee should substitute pantoprazole for omeprazole
    negated_description: the committee should not substitute pantoprazole for omeprazole
    category: decision
  reassess_dose:
    description: the indication and dose should be reassessed periodically, using the lowest effective dose
    negated_description: the indication and dose do not need periodic reassessment
    category: bone
  escalate:
    description: the case should be escalated to the full committee
    negated_description: the case does not need escalation to the full committee
    category: procedural

rules:
  be_is_indication:
    type: defeasible
    premises: [barretts]
    conclusion: be_indication
    category: GI
    source: "aga_barretts_guideline.txt: patients with Barrett's esophagus should be maintained on long-term PPI therapy"
    block: 2
  continue_for_be:
    type: defeasible
    premises: [be_indication]
    conclusion: continue_acid_suppression
    category: GI
    source: "aga_barretts_guideline.txt: discontinuation is not routinely advised solely on the basis of long-term use"
    block: 2
  keep_current:
    type: defeasible
    premises: [continue_acid_suppression, on_omeprazole]
    conclusion: keep_omeprazole
    category: GI
    source: "formulary_committee_protocol.txt: confirm the indication; only without one proceed to deprescribing consultation (continuity default)"
    block: 2
  omeprazole_blocks_clopidogrel:
    type: defeasible
    premises: [clopidogrel_post_pci, on_omeprazole]
    conclusion: cardiac_interaction
    category: cardiac
    negated_description: the omeprazole-clopidogrel interaction is not clinically meaningful for this patient
    source: "acc_aha_antiplatelet.txt: omeprazole and esomeprazole are potent CYP2C19 inhibitors and may reduce the conversion of clopidogrel to its active metabolite"
    block: 2
  avoid_interaction:
    type: defeasible
    premises: [cardiac_interaction]
    conclusion: -keep_omeprazole
    category: cardiac
    source: "acc_aha_antiplatelet.txt: concomitant use of omeprazole or esomeprazole should be avoided when feasible"
    block: 2
  switch_for_interaction:
    type: defeasible
    premises: [cardiac_interaction, continue_acid_suppression]
    conclusion: switch_to_pantoprazole
    category: cardiac
    negated_description: the substitution of pantoprazole is not available for this patient
    source: "acc_aha_antiplatelet.txt: if acid suppression is clinically necessary, pantoprazole or an H2-receptor antagonist is preferred; formulary_committee_protocol.txt: a recommendation to switch to pantoprazole unless contraindicated"
    block: 2
  cogent_reading:
    type: defeasible
    premises: [cogent_decisive]
    conclusion: -omeprazole_blocks_clopidogrel
    category: cardiac
    source: "cogent_trial.txt: frequently cited as evidence that the PPI-clopidogrel interaction is not clinically meaningful"
    block: 2
  contraindication:
    type: defeasible
    premises: [pantoprazole_contraindicated]
    conclusion: -switch_for_interaction
    category: GI
    source: "formulary_committee_protocol.txt: switch to pantoprazole unless contraindicated"
    block: 2
  bone_risk:
    type: defeasible
    premises: [low_bmd_postmenopausal, on_omeprazole]
    conclusion: fracture_risk
    category: bone
    source: "endocrine_ppi_bone.txt: modest increases in hip, wrist, and spine fracture risk among chronic PPI users"
    block: 2
  reassess_for_bone:
    type: defeasible
    premises: [fracture_risk]
    conclusion: reassess_dose
    category: bone
    source: "endocrine_ppi_bone.txt: clinicians should periodically reassess the indication for long-term PPI therapy; continuation remains appropriate where a clear gastrointestinal indication exists"
    block: 2
  complex_case:
    type: defeasible
    premises: [barretts, clopidogrel_post_pci, low_bmd_postmenopausal]
    conclusion: escalate
    category: procedural
    source: "formulary_committee_protocol.txt: cases involving all three triggers are escalated"
    block: 2
  keep_excludes_switch:
    type: strict
    premises: [keep_omeprazole]
    conclusion: -switch_to_pantoprazole
    category: decision
    source: keeping omeprazole unchanged and substituting pantoprazole are exclusive options
  switch_excludes_keep:
    type: strict
    premises: [switch_to_pantoprazole]
    conclusion: -keep_omeprazole
    category: decision
    source: keeping omeprazole unchanged and substituting pantoprazole are exclusive options

corpus:
  - wikipedia_ppi.txt
  - aga_barretts_guideline.txt
  - acc_aha_antiplatelet.txt
  - endocrine_ppi_bone.txt
  - cogent_trial.txt
  - barretts_surveillance_review.txt
  - formulary_committee_protocol.txt
```

### 4.2 Prescribed Burn

Computed: 17 arguments, 6 attacks. `elevated_risk`, `good_fire`, and
`smoke_harm` are accepted in every state below. Preferences are Conflicts-view
choices on the pairs `treat_for_ecology` or `treat_for_culture` versus
`no_treatment_for_smoke`.

| State | treat unit this cycle | ecological benefit | permitted on burn day | go ahead on burn day |
| --- | --- | --- | --- | --- |
| Baseline | undecided | accepted | accepted | undecided |
| `forecast_exceedance` on | undecided | accepted | rejected | rejected |
| `recent_burn` on | undecided | rejected | accepted | undecided |
| `permit_window_open` off | undecided | accepted | absent | absent |
| Prefer `treat_for_ecology` or `treat_for_culture` | accepted | accepted | accepted | accepted |
| Prefer `no_treatment_for_smoke` | rejected | accepted | accepted | rejected |
| Ecology preferred, then `recent_burn` on | undecided | rejected | accepted | undecided |
| Ecology preferred, then `forecast_exceedance` on | accepted | accepted | rejected | rejected |
| Ecology preferred, then `permit_window_open` off | accepted | accepted | absent | absent |
| Ecology rule raised to block 4 by a manual edit, `forecast_exceedance` on | accepted | accepted | rejected | rejected |

The third-from-last row is David's teaching sequence: the recent burn removes
the ecological argument while the cultural one remains, and the recommendation
falls back from accepted to undecided. The last two rows show the permission
prerequisite doing its work independently of the treatment question.

```yaml
title: "Prescribed Burn"
description: >
  A district fire-management team plans a prescribed burn on an overdue,
  fuel-loaded 1,800-acre unit next to a rural community with vulnerable
  residents. Two questions are kept apart: whether the unit should be treated
  with fire this cycle, and whether the burn can go ahead on the planned burn
  day. Two reasons favor treatment (ecological benefit, cultural stewardship)
  and one opposes it (smoke exposure), all at equal strength, so treatment is
  undecided until a preference is set. Going ahead on the day requires a
  favorable treatment decision and an open permit. Under the stipulated
  condition of the fictional state Smoke Management Program, a forecast PM2.5
  exceedance withholds the permit for that day, which postpones the burn
  without settling the treatment question. A recent burn removes the
  ecological benefit.

facts:
  heavy_fuels:
    description: surface and ladder fuels on the unit exceed the historical range
    category: ecology
    source: local_news_burn_coverage.txt ("fuel loading is well above what this forest evolved with"); nifc_situation_report.txt
  drought:
    description: the unit is drought-stressed with low fuel moisture
    category: ecology
    source: nifc_situation_report.txt (fictional site brief)
  wui_unit:
    description: the unit lies in the wildland-urban interface, bordering a rural community
    category: ecology
    source: local_news_burn_coverage.txt; nifc_situation_report.txt
  cultural_regime:
    description: the unit is a cultural-use area burned for generations before federal fire exclusion
    category: cultural
    source: local_news_burn_coverage.txt; tribal_fire_stewardship.txt
  tribal_agreement:
    description: a co-stewardship agreement with the affiliated Tribal Nation governs fire on the unit
    category: cultural
    source: nifc_situation_report.txt (fictional site brief); tribal_fire_stewardship.txt
  community_downwind:
    description: a community with an aging population, elevated asthma rates, and a school in the predicted smoke-drift corridor lies downwind
    category: community
    source: local_news_burn_coverage.txt; community_airshed_letter.txt

assumptions:
  permit_window_open:
    description: the state Smoke Management Program permit window is open on the planned burn day
    negated_description: the permit window is not open on the planned burn day
    category: regulatory
    source: epa_pm25_standards.txt (fictional state program)
    active: true
    block: 1
  forecast_exceedance:
    description: the burn-day forecast predicts a 24-hour PM2.5 exceedance at the community monitor
    negated_description: the forecast does not predict a PM2.5 exceedance
    category: regulatory
    source: epa_pm25_standards.txt; toggle to test an exceedance day. Block 3 keeps the permit condition above a single Conflicts-view preference step
    active: false
    block: 3
  recent_burn:
    description: the unit was burned within the last five-year fuel-recovery window
    negated_description: the unit has not been burned within the last five years
    category: treatment-history
    source: fire_ecology_synthesis.txt; toggle to test a recently treated unit
    active: false
    block: 1

propositions:
  elevated_risk:
    description: the unit carries an elevated probability of high-severity wildfire
    negated_description: the unit does not carry an elevated probability of high-severity wildfire
    category: ecology
  good_fire:
    description: burning the unit is warranted as cultural stewardship
    negated_description: burning the unit is not warranted as cultural stewardship
    category: cultural
  smoke_harm:
    description: a burn would cause non-trivial short-term air-quality harm to the downwind community
    negated_description: a burn would not cause non-trivial short-term air-quality harm
    category: community

conclusions:
  treat_unit:
    description: the unit should be treated with prescribed fire this cycle
    negated_description: the unit should not be treated with prescribed fire this cycle
    category: decision
  eco_benefit:
    description: burning the unit now delivers meaningful ecological benefit
    negated_description: burning the unit now delivers no meaningful ecological benefit
    category: ecology
  burn_permitted:
    description: burning is permitted on the planned burn day under the Smoke Management Program
    negated_description: burning is not permitted on the planned burn day under the Smoke Management Program
    category: regulatory
  burn_today:
    description: the burn should go ahead on the planned burn day
    negated_description: the burn should not go ahead on the planned burn day
    category: decision

rules:
  risk_from_fuels:
    type: defeasible
    premises: [heavy_fuels, drought]
    conclusion: elevated_risk
    category: ecology
    source: "fire_ecology_synthesis.txt: heavy surface and ladder fuel loads produce high-severity crown fire"
    block: 1
  benefit_from_treatment:
    type: defeasible
    premises: [elevated_risk, wui_unit]
    conclusion: eco_benefit
    category: ecology
    negated_description: within the fuel-recovery window, re-treating the unit adds no ecological benefit
    source: "fire_ecology_synthesis.txt: for units with heavy fuel loading and no recent treatment the case is strong"
    block: 1
  treat_for_ecology:
    type: defeasible
    premises: [eco_benefit]
    conclusion: treat_unit
    category: ecology
    source: "nifc_situation_report.txt: accelerate treatment where feasible"
    block: 1
  cultural_stewardship:
    type: defeasible
    premises: [cultural_regime, tribal_agreement]
    conclusion: good_fire
    category: cultural
    source: "tribal_fire_stewardship.txt: a documented cultural fire regime is substantive justification for burning"
    block: 1
  treat_for_culture:
    type: defeasible
    premises: [good_fire]
    conclusion: treat_unit
    category: cultural
    source: "tribal_fire_stewardship.txt"
    block: 1
  smoke_exposure:
    type: defeasible
    premises: [community_downwind]
    conclusion: smoke_harm
    category: community
    source: "community_airshed_letter.txt: previous burns produced multi-day PM2.5 excursions"
    block: 1
  no_treatment_for_smoke:
    type: defeasible
    premises: [smoke_harm]
    conclusion: -treat_unit
    category: community
    source: "community_airshed_letter.txt: treat air-quality impacts as a material factor"
    block: 1
  permit_allows_burn:
    type: defeasible
    premises: [permit_window_open]
    conclusion: burn_permitted
    category: regulatory
    source: "epa_pm25_standards.txt: burn-day go/no-go criteria under the state Smoke Management Program"
    block: 1
  exceedance_withholds_permit:
    type: strict
    premises: [forecast_exceedance]
    conclusion: -burn_permitted
    category: regulatory
    source: "epa_pm25_standards.txt: under the state Smoke Management Program the permit is withheld for that day regardless of justification; stipulated condition of the fictional state program"
  go_ahead:
    type: defeasible
    premises: [treat_unit, burn_permitted]
    conclusion: burn_today
    category: decision
    source: "epa_pm25_standards.txt: burn-day go/no-go determination"
    block: 1
  recent_burn_no_benefit:
    type: defeasible
    premises: [recent_burn]
    conclusion: -benefit_from_treatment
    category: treatment-history
    source: "fire_ecology_synthesis.txt: units treated within the past five years are poor candidates for re-treatment"
    block: 1

corpus:
  - wikipedia_prescribed_burn.txt
  - fire_ecology_synthesis.txt
  - epa_pm25_standards.txt
  - tribal_fire_stewardship.txt
  - community_airshed_letter.txt
  - nifc_situation_report.txt
  - local_news_burn_coverage.txt
```

### 4.3 NBA Rebuild

Computed: 19 arguments, 15 attacks; the two strict rules are each other's
transposition. `classic_fit` is rejected, `high_pick_valuable` and `dev_first`
are accepted, and `talent_dilution` is absent in every state below except
where expansion is on (then `talent_dilution` is accepted).

| State | tank | stack veterans | compete |
| --- | --- | --- | --- |
| Baseline | rejected | rejected | accepted |
| `expansion_pending` on | undecided | rejected | undecided |
| `expansion_pending` on, then prefer `tank_for_scarcity` over `no_tank_for_development` | accepted | rejected | rejected |
| `expansion_pending` on, then prefer `no_tank_for_development` | rejected | rejected | accepted |
| `deal_fits_under_apron` on | rejected | rejected | accepted |
| `deal_fits_under_apron` on, then prefer `stack_for_window` over `preserve_flexibility` | rejected | accepted | accepted |
| Prefer `stack_for_window` with the deal assumption off | rejected | rejected | accepted |
| Prefer `tank_for_odds` over `no_tank_for_development` at baseline | rejected | rejected | accepted |

With expansion on, tank and compete are both undecided: the scarcity argument
for tanking and the development argument against it have equal strength, and
because the two postures are exclusive, competing cannot be accepted while
tanking is open. Either preference settles both. Stacking can coexist with
competing (row six), as David asked. The last row is expected: the
extra-losses argument is undercut by the flattened lottery, so preferring it
changes nothing.

```yaml
title: "NBA Rebuild"
description: >
  A fictional non-contending front office with a promising young core weighs
  three postures for the season: tank, stack veteran stars, or compete while
  developing the core. Tanking and competing are exclusive; stacking veterans
  is a separate roster question. The classic rebuild argument is undercut by
  the Process retrospective and the extra-losses argument by the flattened
  lottery odds, so the development priority carries the season: compete is
  accepted and tank rejected. Stacking is rejected by the memo's
  recommendation to preserve first-round flexibility, and it is only on the
  table if the acquisition can be structured under the second apron, which
  the memo says it cannot. Pending league expansion makes cornerstone talent
  scarcer and revives the case for tanking to a tie.

facts:
  non_contender:
    description: the team projects to a 25 to 35 win season and is not a realistic contender
    category: team-status
    source: front_office_memo.txt
  young_core:
    description: the team has a top-tier under-25 core in rotation roles
    category: team-status
    source: front_office_memo.txt
  strong_draft:
    description: the upcoming draft has consensus top-5 talent
    category: draft
    source: front_office_memo.txt
  tradeable_firsts:
    description: the team controls two future first-round picks it could trade
    category: assets
    source: front_office_memo.txt
  lottery_flattened:
    description: since 2019 the three worst records share the same 14 percent odds at the first pick, so losses beyond the bottom three do not improve them
    category: league-rule
    source: lottery_reform_2019.txt; wikipedia_draft_lottery.txt
  process_cautionary:
    description: the Process retrospective concludes that the classic tanking rebuild is not replicable under current rules
    category: historical-analysis
    source: the_process_retrospective.txt

assumptions:
  deal_fits_under_apron:
    description: the proposed veteran acquisition can be structured so that the payroll stays under the second apron
    negated_description: the proposed veteran acquisition would leave the payroll above the second apron
    category: league-rule
    source: front_office_memo.txt ("would move us over the second apron"); cba_second_apron.txt; off by default, toggle on to test a deal that fits under the apron
    active: false
    block: 1
  expansion_pending:
    description: expansion to two new franchises is under serious discussion
    negated_description: expansion is not under serious discussion
    category: league-landscape
    source: nba_expansion_analysis.txt; toggle to test the expansion case
    active: false
    block: 2

propositions:
  classic_fit:
    description: the team fits the classic rebuild pattern
    negated_description: the team does not fit the classic rebuild pattern
    category: rebuild-logic
  high_pick_valuable:
    description: a top pick in this draft is worth much more than a middle first
    negated_description: a top pick in this draft is not worth much more than a middle first
    category: pick-value
  talent_dilution:
    description: league expansion would make cornerstone talent scarcer
    negated_description: league expansion would not make cornerstone talent materially scarcer
    category: league-landscape
  dev_first:
    description: protecting the young core's development is the governing priority
    negated_description: protecting the young core's development is not the governing priority
    category: development

conclusions:
  tank:
    description: the team should tank this season
    negated_description: the team should not tank this season
    category: strategy
  stack_vets:
    description: the team should trade picks and aggregate salary for veteran stars
    negated_description: the team should not trade picks and aggregate salary for veteran stars
    category: strategy
  compete:
    description: the team should compete now and develop the young core
    negated_description: the team should not compete now and develop the young core
    category: strategy

rules:
  classic_pattern:
    type: defeasible
    premises: [non_contender, strong_draft]
    conclusion: classic_fit
    category: rebuild-logic
    negated_description: the classic rebuild pattern does not apply under current rules
    source: "the_process_retrospective.txt: the expected value of a draft-heavy rebuild"
    block: 1
  tank_for_pattern:
    type: defeasible
    premises: [classic_fit]
    conclusion: tank
    category: rebuild-logic
    source: "the_process_retrospective.txt"
    block: 1
  process_undercut:
    type: defeasible
    premises: [process_cautionary]
    conclusion: -classic_pattern
    category: historical-analysis
    source: "the_process_retrospective.txt: teams that invoke the Process framing today are reasoning from a rule set that no longer exists"
    block: 1
  pick_value:
    type: defeasible
    premises: [strong_draft]
    conclusion: high_pick_valuable
    category: pick-value
    source: "front_office_memo.txt: the upcoming draft is consensus-strong, with clear top-5 talent"
    block: 1
  tank_for_odds:
    type: defeasible
    premises: [high_pick_valuable, non_contender]
    conclusion: tank
    category: pick-value
    negated_description: for a team already bound for the lottery, the extra losses of a tank barely change its expected pick
    source: "analyst_tanking_piece.txt: if you were running a rebuild, getting to the bottom of the standings was worth something"
    block: 1
  flattening_undercut:
    type: defeasible
    premises: [lottery_flattened]
    conclusion: -tank_for_odds
    category: league-rule
    source: "analyst_tanking_piece.txt: once you're in the bottom-3 band, the marginal value of your last ten or fifteen losses is effectively zero; front_office_memo.txt: the last 10 losses of a tank are close to pick-neutral"
    block: 1
  dilution:
    type: defeasible
    premises: [expansion_pending]
    conclusion: talent_dilution
    category: league-landscape
    source: "nba_expansion_analysis.txt: concern about the dilution of talent if two more teams are added"
    block: 2
  tank_for_scarcity:
    type: defeasible
    premises: [talent_dilution, high_pick_valuable, non_contender]
    conclusion: tank
    category: league-landscape
    source: "nba_expansion_analysis.txt: are there enough stars to support two additional competitive teams; the current evidence suggests no. analyst_tanking_piece.txt: that choice still favors the lottery"
    block: 2
  development_priority:
    type: defeasible
    premises: [young_core, non_contender]
    conclusion: dev_first
    category: development
    source: "young_core_development.txt: the strongest predictor of multi-year improvement is playoff exposure before age 25"
    block: 2
  no_tank_for_development:
    type: defeasible
    premises: [dev_first]
    conclusion: -tank
    category: development
    source: "analyst_tanking_piece.txt: you might give back years of development"
    block: 2
  compete_for_development:
    type: defeasible
    premises: [dev_first]
    conclusion: compete
    category: development
    source: "front_office_memo.txt: play the young core meaningful minutes"
    block: 2
  stack_for_window:
    type: defeasible
    premises: [tradeable_firsts, young_core, non_contender, deal_fits_under_apron]
    conclusion: stack_vets
    category: strategy
    source: "front_office_memo.txt: use future firsts plus salary aggregation to acquire one or two veteran stars; cba_second_apron.txt: no salary aggregation in trades over the second apron"
    block: 1
  preserve_flexibility:
    type: defeasible
    premises: [dev_first, tradeable_firsts]
    conclusion: -stack_vets
    category: strategy
    source: "front_office_memo.txt: preserve future first-round flexibility"
    block: 2
  tank_excludes_compete:
    type: strict
    premises: [tank]
    conclusion: -compete
    category: strategy
    source: tanking and competing to win are exclusive season postures
  compete_excludes_tank:
    type: strict
    premises: [compete]
    conclusion: -tank
    category: strategy
    source: tanking and competing to win are exclusive season postures

corpus:
  - wikipedia_draft_lottery.txt
  - lottery_reform_2019.txt
  - cba_second_apron.txt
  - young_core_development.txt
  - analyst_tanking_piece.txt
  - the_process_retrospective.txt
  - front_office_memo.txt
  - nba_expansion_analysis.txt
```

## 5 Companion corpus corrections (content only, optional)

These are text edits to existing corpus files. The knowledge bases above do not
depend on them, but without them the chat model can restate the errors.

- `examples/medical_ppi/corpus/acc_aha_antiplatelet.txt`, the COGENT
  sentence: COGENT randomised omeprazole, not pantoprazole. Replace "did not
  show an excess of ischemic events with pantoprazole + clopidogrel" with
  "did not show an excess of ischemic events with omeprazole + clopidogrel,
  but was underpowered for rare events".
- `examples/medical_ppi/corpus/wikipedia_ppi.txt`, the clopidogrel bullet:
  replace "did not detect excess ischemic events with pantoprazole" with
  "did not detect excess ischemic events with omeprazole".
- `examples/medical_ppi/corpus/cogent_trial.txt`: the design section is
  right (omeprazole); leave it, and keep its statement that the trial was
  underpowered.
- The synthetic protocol, memo, letter, situation report, and news files
  already carry "illustrative", "composite", or "not a real document" notes.
  The proposed scenario descriptions call the patient, unit, and team
  fictional, so the attribution is consistent end to end. Renaming files
  that borrow institutional names is a further option and is not required by
  this proposal.

## 6 Adoption

1. Write the behavioural assertions first: turn the tables in section 4 into
   test expectations (baseline labels, each toggle, each listed preference and
   sequence), so that the regenerated snapshots are checked against intended
   behaviour rather than merely reproduced.
2. Replace the three `scenario.yaml` files and regenerate
   `expected_labels.yaml` for each.
3. Update current tests, evaluation cases, and user-facing instructions that
   name a changed identifier: in `evals/llm_suite.yaml` the pantoprazole
   toggle case becomes a `cogent_decisive` case, `legal_today` becomes
   `burn_permitted`, and the NBA baseline case's expectation moves from
   `preserve_flex` to `compete` (a conceptual change, not a rename; rewrite
   the expected concepts accordingly); the tests `tests/test_api.py`,
   `tests/test_chat_validator.py`, `tests/test_integration.py`,
   `tests/test_loader.py`, `tests/test_mcp.py`, and
   `tests/test_rule_argument_context.py` reference identifiers from the
   current files. Do not edit historical operations or evaluation records;
   add a dated reconstruction record under `docs/operations/` instead.
4. Existing private projects, share snapshots, and published community
   examples keep their own snapshots (version 3 exports embed the scenario
   and its text), so nothing saved changes. State this in the reconstruction
   record.
5. Apply the section 5 corpus corrections if adopted, then rerun the affected
   scenario cases across the admitted models and features within the existing
   evaluation budget, and tune a prompt only if a recorded failure shows the
   need.
