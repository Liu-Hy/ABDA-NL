# Reconstructing the ASPIC- knowledge bases of three demo scenarios

Group meeting report, September 11, 2026, prepared from the repository
records. Quoted files are verbatim.

## 1. Background

ABDA-NL pairs a deterministic argumentation engine (ABDA, an implementation
of ASPIC-) with a language model that explains results and translates edits
but never decides. Each demo scenario is a small ASPIC- knowledge base in
YAML plus source documents the chat model may quote. Six scenarios ship; we
rebuilt three.

| Term in the scenario file | Meaning | Example |
| --- | --- | --- |
| Fact | A premise that always holds (a strict rule with no premises). | `barretts`: the patient has biopsy-confirmed Barrett's esophagus |
| Assumption | A premise the user can switch on or off, with a strength (`block`). | `cogent_decisive`, off by default |
| Proposition | An intermediate claim derived by rules. | `fracture_risk` |
| Conclusion | A claim shown in the Conclusions panel; usually a decision. | `keep_omeprazole` |
| Defeasible rule `=>` | An inference that holds by default and can be defeated. | `cardiac_interaction => -keep_omeprazole` |
| Strict rule `->` | An inference that cannot be undercut. | `keep_omeprazole -> -switch_to_pantoprazole` |
| `-x` | The negation of literal `x`; `-r` for a rule name is an undercut of rule `r`. | `cogent_decisive => -omeprazole_blocks_clopidogrel` |
| Block | Preference strength; a larger number is stronger. The Conflicts view lets the user prefer one rule over another. | `block: 2` |
| Labels | Grounded semantics: accepted, rejected, undecided; the interface adds absent (no argument exists). | baseline `keep_omeprazole`: undecided |

Two engine behaviours shaped the design:

| Engine behaviour | Consequence for scenario design |
| --- | --- |
| Rebuts are compared by the strongest rule in each argument (weakest link with democratic ordering, which reduces to comparing maximum blocks). An attacker wins unless it is strictly weaker than the sub-argument it attacks. | Raising one rule's block in the Conflicts view strengthens every argument that uses that rule anywhere. |
| A strict rule adds no strength of its own: the argument it tops can still be rebutted, and a constraint switched on by an assumption is only as strong as that assumption's block. A rebut is judged against the attacked sub-argument, so a prerequisite premise's own argument decides. | A "categorical" constraint must sit at a high block or, better, be expressed as a prerequisite premise of the decision it constrains. |

## 2. Why we rebuilt them

We kept Popov v. Hayashi (Prakken's published reconstruction) and the two
Fried Chicken scenarios (our own teaching example). The other three were
generated with LLM help in June 2026: their corpus files are labelled
"paraphrased" or "illustrative composite", two even say how they should be
modelled ("for formal modeling, this is captured as a strict rule"), and the
rules were written to produce interesting labels rather than to reflect the
sources.

| Scenario | Problems in the June knowledge base |
| --- | --- |
| PPI Therapy | A strict rule that only renames a fact. A rule saying that being on long-term therapy denies that Barrett's is an indication, a non sequitur that exists to be defeated. A pharmacological fact derived from the patient's stent. The bone line neutralised twice. Three findings among the seven key conclusions. Paraphrased guidelines cited as exact authorities ("AGA 2022 Rec 7 (Grade A)"). The drug is never named, although the interaction guidance is drug-specific. |
| Prescribed Burn | The "categorical" PM2.5 strict rule never wins (its assumption sits at block 1, the permit argument at block 2), so the exceedance toggle changes nothing. A community request that exposure be "a material factor" encoded as burning being illegal. A manufactured pair on re-treatment intervals derived from being in the wildland-urban interface. `postpone_burn` accepted beside `conduct_burn` undecided with no relation between them. |
| NBA Rebuild | The second-apron toggle changes nothing because stacking is already rejected. `lottery_math` and its negation derived from the same fact at the same block, purely to show an undecided label. Five of eight key conclusions are intermediate findings. Tanking and competing are never related. |
| Sources | Two corpus sentences say the COGENT trial tested pantoprazole; it tested omeprazole. Patient, site, and team facts cite general guidelines as their source. One "regulatory" file presents a fictional permit condition as a universal EPA rule. |

## 3. How we did it

One proposal, one critical review, one implementation, under Haoyang's rule:
change only scenario content (facts, assumptions, rules, corpus text), never
the engine, file format, or a feature. Tim (a Claude agent) wrote the
proposal; David (an AI colleague) recomputed every table and raised seven
objections; Tim revised; David implemented, tests first. Every table below
was computed with the engine.

| Design rule | What it means in practice |
| --- | --- |
| Key conclusions are decisions, plus findings that a toggle or preference disputes. | PPI: six conclusions instead of seven; NBA: three instead of eight. |
| Every fact is an observation with a named source; observations about the fictional patient, unit, or team cite the fictional brief they come from. | `source: fictional case brief in the scenario description` |
| Every assumption is a what-if whose toggle changes a visible label in the way its description says. | The exceedance toggle now rejects the day's burn. |
| One rule per distinct consideration; no pairs manufactured to display a label. | `lottery_math` pro and con are gone. |
| Undercuts mean "this consideration does not apply here"; preferences mean "this consideration outweighs that one". | `recent_burn => -benefit_from_treatment` |
| Strict rules only for exclusivity between options and for a stipulated categorical condition. | `tank -> -compete`, `forecast_exceedance -> -burn_permitted` |
| Categorical constraints are bounded modelling choices; where unconditional applicability matters, use a prerequisite premise. | `deal_fits_under_apron` is a premise of the stacking rule. |
| Identifiers read as English. | `switch_for_interaction`, not `r_stack`. |

| David's objection to the first proposal | Change in the second version |
| --- | --- |
| 1. Repair the sources: COGENT tested omeprazole; patient facts cannot cite guidelines; drop the unverified claim that every rule has Wikipedia support. | Accepted in part. Facts cite the fictional brief; the two COGENT sentences were corrected; the Wikipedia claim was removed. Replacing the corpora with real documents stayed out of scope. |
| 2. PPI conflates continuing acid suppression with continuing the current drug; name the drug; reassessment is not discontinuation. | The drug is omeprazole (a fact). Three decisions: stay on acid suppression, keep omeprazole unchanged, substitute pantoprazole, the last two mutually exclusive. The bone line concludes periodic reassessment and attacks nothing. The old "PPI is pantoprazole" toggle became "pantoprazole is contraindicated". |
| 3. Prescribed Burn mixes "this cycle" with "today"; permission should be a prerequisite of an executable recommendation; the categorical rule is not a universal EPA prohibition. | Two decisions: treat the unit this cycle, and go ahead on the planned burn day. Permission is a premise of the second. The strict rule is attributed to a fictional state Smoke Management Program. |
| 4. NBA never relates tanking to competing; the lottery undercut targets the wrong concept and omits the bottom-three qualification; the apron needs transaction context. | Tank and compete are exclusive through two strict rules. The flattening undercuts the extra-losses inference, and the fact carries the bottom-three qualification. The apron is a prerequisite assumption of the stacking plan, off by default because the memo says the deal would cross it. |
| 5. Do not require every toggle to change a headline decision; findings can be key conclusions. | Rule relaxed to "every toggle changes a visible label". `eco_benefit` and `cardiac_interaction` are key conclusions. |
| 6. State the categorical constraints as bounded guarantees. | Stated exactly (section 5). |
| 7. Write behavioural assertions before snapshots; do not rewrite historical records; preserve saved projects; rerun the affected evaluations. | Done as described in section 5. |

## 4. The three knowledge bases

| Scenario | June version | Reconstructed version |
| --- | --- | --- |
| PPI Therapy | 6 facts, 2 assumptions, 2 propositions, 7 key conclusions, 16 rules (20 arguments, 7 attacks) | 4 facts, 2 assumptions, 2 propositions, 6 key conclusions, 13 rules (15 arguments, 9 attacks) |
| Prescribed Burn | 7 facts, 3 assumptions, 2 propositions, 6 key conclusions, 15 rules (23 arguments, 8 attacks) | 6 facts, 3 assumptions, 3 propositions, 4 key conclusions, 11 rules (17 arguments, 6 attacks) |
| NBA Rebuild | 8 facts, 2 assumptions, 0 propositions, 8 key conclusions, 15 rules (21 arguments, 10 attacks) | 6 facts, 2 assumptions, 4 propositions, 3 key conclusions, 15 rules (19 arguments, 15 attacks) |

ASPIC- notation below; full YAML in Appendix A, June versions in Appendix B.

### 4.1 PPI Therapy

A fictional patient takes omeprazole for Barrett's esophagus and clopidogrel
after a stent, and has low bone density. Acid suppression should continue;
whether omeprazole itself continues is the open question.

```text
Facts (source: fictional case brief)
  barretts                 biopsy-confirmed Barrett's esophagus
  on_omeprazole            long-term omeprazole for acid suppression
  clopidogrel_post_pci     clopidogrel after a recent coronary intervention
  low_bmd_postmenopausal   postmenopausal, low bone mineral density on DEXA

Assumptions (both off at baseline, block 1)
  cogent_decisive                COGENT is treated as showing the interaction is not meaningful
  pantoprazole_contraindicated   pantoprazole is contraindicated for this patient

Rules (defeasible, block 2, unless marked strict)
  be_is_indication               barretts => be_indication
  continue_for_be                be_indication => continue_acid_suppression
  keep_current                   continue_acid_suppression, on_omeprazole => keep_omeprazole
  omeprazole_blocks_clopidogrel  clopidogrel_post_pci, on_omeprazole => cardiac_interaction
  avoid_interaction              cardiac_interaction => -keep_omeprazole
  switch_for_interaction         cardiac_interaction, continue_acid_suppression => switch_to_pantoprazole
  cogent_reading                 cogent_decisive => -omeprazole_blocks_clopidogrel        (undercut)
  contraindication               pantoprazole_contraindicated => -switch_for_interaction  (undercut)
  bone_risk                      low_bmd_postmenopausal, on_omeprazole => fracture_risk
  reassess_for_bone              fracture_risk => reassess_dose
  complex_case                   barretts, clopidogrel_post_pci, low_bmd_postmenopausal => escalate
  keep_excludes_switch  (strict) keep_omeprazole -> -switch_to_pantoprazole
  switch_excludes_keep  (strict) switch_to_pantoprazole -> -keep_omeprazole

Key conclusions: continue_acid_suppression, cardiac_interaction, keep_omeprazole,
                 switch_to_pantoprazole, reassess_dose, escalate
```

| State | Continue acid suppression | Cardiac interaction | Keep omeprazole | Switch to pantoprazole | Reassess dose | Escalate |
| --- | --- | --- | --- | --- | --- | --- |
| Baseline | accepted | accepted | undecided | undecided | accepted | accepted |
| `cogent_decisive` on | accepted | rejected | accepted | rejected | accepted | accepted |
| `pantoprazole_contraindicated` on | accepted | accepted | undecided | rejected | accepted | accepted |
| Prefer `avoid_interaction` | accepted | accepted | rejected | accepted | accepted | accepted |
| Prefer `keep_current` | accepted | accepted | accepted | rejected | accepted | accepted |
| Contraindicated on, then prefer `avoid_interaction` | accepted | accepted | rejected | rejected | accepted | accepted |

The last row is the intended hard case; adding an H2-blocker alternative
(one of our evaluation cases) would resolve it.

### 4.2 Prescribed Burn

A fire team weighs forest health and tribal stewardship against smoke
downwind. Treating the unit this cycle and going ahead on the planned day are
separate questions; the second requires permission.

```text
Facts (sources: fictional site brief, local news, tribal stewardship brief, community letter)
  heavy_fuels          fuels exceed the historical range
  drought              drought-stressed, low fuel moisture
  wui_unit             wildland-urban interface, bordering a rural community
  cultural_regime      cultural-use area burned for generations before fire exclusion
  tribal_agreement     co-stewardship agreement with the affiliated Tribal Nation
  community_downwind   aging population, elevated asthma rates, a school in the smoke corridor

Assumptions
  permit_window_open   (on,  block 1)  the permit window is open on the planned burn day
  forecast_exceedance  (off, block 3)  the burn-day forecast predicts a PM2.5 exceedance
  recent_burn          (off, block 1)  the unit was burned within the five-year recovery window

Rules (defeasible, block 1, unless marked strict)
  risk_from_fuels                    heavy_fuels, drought => elevated_risk
  benefit_from_treatment             elevated_risk, wui_unit => eco_benefit
  treat_for_ecology                  eco_benefit => treat_unit
  cultural_stewardship               cultural_regime, tribal_agreement => good_fire
  treat_for_culture                  good_fire => treat_unit
  smoke_exposure                     community_downwind => smoke_harm
  no_treatment_for_smoke             smoke_harm => -treat_unit
  permit_allows_burn                 permit_window_open => burn_permitted
  exceedance_withholds_permit (strict) forecast_exceedance -> -burn_permitted
  go_ahead                           treat_unit, burn_permitted => burn_today
  recent_burn_no_benefit             recent_burn => -benefit_from_treatment   (undercut)

Key conclusions: treat_unit, eco_benefit, burn_permitted, burn_today
```

| State | Treat unit | Ecological benefit | Burn permitted | Burn today |
| --- | --- | --- | --- | --- |
| Baseline | undecided | accepted | accepted | undecided |
| `forecast_exceedance` on | undecided | accepted | rejected | rejected |
| `recent_burn` on | undecided | rejected | accepted | undecided |
| `permit_window_open` off | undecided | accepted | absent | absent |
| Prefer ecology or culture over smoke | accepted | accepted | accepted | accepted |
| Prefer smoke | rejected | accepted | accepted | rejected |
| Ecology preferred, then `recent_burn` on (teaching sequence) | undecided | rejected | accepted | undecided |
| Ecology preferred, then exceedance on | accepted | accepted | rejected | rejected |
| Ecology preferred, then permit off | accepted | accepted | absent | absent |
| Ecology raised to block 4 by manual edit, exceedance on | accepted | accepted | rejected | rejected |

### 4.3 NBA Rebuild

A young-core front office chooses between competing now and tanking for a
high pick, and separately whether to trade picks for veterans.

```text
Facts (sources: front-office memo, lottery reform article, Process retrospective)
  non_contender        projects to 25 to 35 wins
  young_core           top-tier under-25 core in rotation roles
  strong_draft         consensus top-5 talent in the upcoming draft
  tradeable_firsts     controls two future first-round picks
  lottery_flattened    since 2019 the three worst records share 14 percent odds,
                       so losses beyond the bottom three do not improve them
  process_cautionary   the Process retrospective says the classic tanking rebuild is not replicable

Assumptions
  deal_fits_under_apron  (off, block 1)  the acquisition can be structured under the second apron
  expansion_pending      (off, block 2)  expansion to two new franchises is under discussion

Rules (defeasible unless marked strict; block shown)
  classic_pattern (1)           non_contender, strong_draft => classic_fit
  tank_for_pattern (1)          classic_fit => tank
  process_undercut (1)          process_cautionary => -classic_pattern   (undercut)
  pick_value (1)                strong_draft => high_pick_valuable
  tank_for_odds (1)             high_pick_valuable, non_contender => tank
  flattening_undercut (1)       lottery_flattened => -tank_for_odds      (undercut)
  dilution (2)                  expansion_pending => talent_dilution
  tank_for_scarcity (2)         talent_dilution, high_pick_valuable, non_contender => tank
  development_priority (2)      young_core, non_contender => dev_first
  no_tank_for_development (2)   dev_first => -tank
  compete_for_development (2)   dev_first => compete
  stack_for_window (1)          tradeable_firsts, young_core, non_contender, deal_fits_under_apron => stack_vets
  preserve_flexibility (2)      dev_first, tradeable_firsts => -stack_vets
  tank_excludes_compete (strict) tank -> -compete
  compete_excludes_tank (strict) compete -> -tank

Key conclusions: tank, stack_vets, compete
```

| State | Tank | Stack veterans | Compete | Other labels |
| --- | --- | --- | --- | --- |
| Baseline | rejected | rejected | accepted | `classic_fit` rejected, `high_pick_valuable` accepted, `talent_dilution` absent, `dev_first` accepted |
| Expansion on | undecided | rejected | undecided | `talent_dilution` accepted |
| Expansion on, then prefer `tank_for_scarcity` | accepted | rejected | rejected | |
| Expansion on, then prefer `no_tank_for_development` | rejected | rejected | accepted | |
| Deal assumption on | rejected | rejected | accepted | |
| Deal on, then prefer `stack_for_window` | rejected | accepted | accepted | |
| Prefer stacking with the deal assumption off | rejected | rejected | accepted | stacking has no argument at all |
| Prefer `tank_for_odds` at baseline | rejected | rejected | accepted | the undercut still removes it |

## 5. Verification and what it guarantees

David wrote the tests from the tables above before replacing any file; the
June files failed them, the new files pass all 93 checks. The evaluation
suite was updated and the six admitted models rerun on it with no material
findings.

```python
# tests/test_reconstructed_scenarios.py (excerpt): the PPI decision table as a test
@pytest.mark.parametrize("toggles,preference,expected", [
    ((), None, ("accepted", "accepted", "undecided", "undecided", "accepted", "accepted")),
    (("cogent_decisive",), None, ("accepted", "rejected", "accepted", "rejected", "accepted", "accepted")),
    (("pantoprazole_contraindicated",), None, ("accepted", "accepted", "undecided", "rejected", "accepted", "accepted")),
    ((), ("avoid_interaction", "keep_current"), ("accepted", "accepted", "rejected", "accepted", "accepted", "accepted")),
    ((), ("keep_current", "avoid_interaction"), ("accepted", "accepted", "accepted", "rejected", "accepted", "accepted")),
    (("pantoprazole_contraindicated",), ("avoid_interaction", "keep_current"), ("accepted", "accepted", "rejected", "rejected", "accepted", "accepted")),
])
def test_ppi_decision_table(toggles, preference, expected):
    labels = _state("medical_ppi", toggles, preference)["labels_by_proposition"]
    columns = ("continue_acid_suppression", "cardiac_interaction", "keep_omeprazole",
               "switch_to_pantoprazole", "reassess_dose", "escalate")
    assert tuple(labels[column] for column in columns) == expected
    assert labels["be_indication"] == labels["fracture_risk"] == "accepted"
```

| Check group | Count | What it protects |
| --- | --- | --- |
| Table states (PPI 6, Burn 11, NBA 8) | 25 | Every row of the tables in section 4. |
| Combined toggles and preferences (PPI 12, Burn 32, NBA 20) | 64 | Acid suppression always continues; keep and switch are never both accepted; a strong treatment preference never bypasses an absent or rejected permit; an unavailable deal cannot be preferred into existence; tank and compete are never both accepted. |
| Baseline graph counts | 3 | 15/9, 17/6, and 19/15 arguments and attacks. |
| Teaching sequence | 1 | Prefer ecology, then switch on `recent_burn`: cultural support keeps treatment undecided rather than rejected. |

| Guarantee | Holds when | Fails when |
| --- | --- | --- |
| An exceedance day rejects permission and the day's burn, whatever the treatment preferences. | The permit rule and its assumption stay below block 3. The Conflicts view moves a pair only one step above its baseline, so it cannot break this. | A deliberate block edit raises the permit rule or assumption to 3 or more. |
| Stacking veterans is unavailable unless the deal fits under the apron. | Always: the assumption is a premise, so no preference can create the argument. | Never, short of editing the rule. |
| Tank and compete are never both accepted. | Always: two strict exclusivity rules. | Never. |

| Evaluation case (suite version 10, 52 cases; 20 touch these scenarios) | What it checks |
| --- | --- |
| `medical-cogent-toggle` (replaces the pantoprazole toggle case) | With COGENT decisive, the interaction is rejected and omeprazole is kept. |
| `medical-unavailable-substitute` (new) | Contraindication plus interaction priority leaves no workable replacement. |
| `fire-suspended-permit-rule` | Suspending the permit rule leaves permission absent, not rejected. |
| `fire-exceedance-despite-treatment-priority` (new) | Block 4 for ecology does not bypass the permit requirement. |
| `nba-expansion-preference-excludes-competing` (new) | Tanking accepted implies competing rejected; the flattened lottery does not remove pick value. |
| `nba-unavailable-deal-cannot-be-preferred-into-existence` (new) | Block 5 for stacking with the deal off still yields no stacking argument. |
| 14 existing chat, proposal, and review cases | Renamed identifiers and conclusions (`treat_unit`, `burn_permitted`, `stack_for_window`, `compete`); unchanged intent. |

| Corpus text correction | Before | After |
| --- | --- | --- |
| `medical_ppi/corpus/acc_aha_antiplatelet.txt`, `wikipedia_ppi.txt` | COGENT "did not show an excess of ischemic events with pantoprazole + clopidogrel" | "with omeprazole + clopidogrel"; the trial's limited power is retained |
| `fire_prevention/corpus/epa_pm25_standards.txt` | "Under most state SMPs ... the burn permit is withheld ... For formal modeling, this is captured as a strict rule" | "Under the fictional state Smoke Management Program in this scenario ... a categorical condition of this fictional permit, not a claim that all real jurisdictions use the same rule" |

## 6. Limits

The scenarios remain fictional teaching cases, not verified clinical,
regulatory, or basketball references. Saved projects were
not migrated, but older server objects that reference corpus filenames now
resolve to the corrected text, a recorded limitation. Unconditional
applicability, immune to any block edit, is not expressible in the engine and
stayed out of scope.

## Appendix A: the reconstructed files

### A.1 `examples/medical_ppi/scenario.yaml`

```yaml
title: "PPI Therapy"
description: >
  A fictional patient takes omeprazole to control stomach acid and help manage
  Barrett's esophagus. The patient also takes clopidogrel after a heart stent
  and has low bone density. A hospital committee weighs the benefits of
  treatment against possible drug interactions and long-term risks. It
  considers whether to keep omeprazole or switch to pantoprazole, and whether
  the dose should change.

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

### A.2 `examples/fire_prevention/scenario.yaml`

```yaml
title: "Prescribed Burn"
description: >
  In this fictional case, a fire management team considers a controlled burn
  on 1,800 acres of forest where combustible material has accumulated. The
  team weighs forest health and tribal stewardship against smoke exposure in a
  nearby rural community. Local permit conditions and the day's air-quality
  forecast also affect whether the planned burn can proceed.

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

### A.3 `examples/nba_rebuild/scenario.yaml`

```yaml
title: "NBA Rebuild"
description: >
  A fictional NBA front office has promising young players but little chance
  of contending for a title this season. Should the team play to win and
  develop its young core, or accept more losses in pursuit of a high draft
  pick? It must also decide whether to trade future picks for veteran stars.
  Lottery odds, salary restrictions, competitive experience, and possible
  league expansion shape both decisions.

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

## Appendix B: the June knowledge bases, in compact form

Full files: `git show 7452f26:examples/<dir>/scenario.yaml`.

```text
PPI Therapy (June 2026)
Facts: barretts, clopidogrel, recent_pci, postmenop, low_bmd, on_ppi
Assumptions (off, block 1): ppi_is_panto, cogent_applies
Rules (block in parentheses)
  on_ppi_is_chronic (strict)  on_ppi -> long_term_ppi
  aga_rec7 (3)                barretts => be_indication
  deprescribe_default (1)     long_term_ppi => -be_indication
  continue_if_be (2)          barretts, on_ppi => continue_ppi
  clop_needs_cyp2c19 (2)      clopidogrel, recent_pci => needs_cyp2c19
  ppi_blocks_cyp2c19 (2)      needs_cyp2c19, on_ppi => cardiac_risk
  acc_aha_avoid (2)           cardiac_risk => -continue_ppi
  panto_spares (2)            ppi_is_panto => -ppi_blocks_cyp2c19
  cogent (2)                  cogent_applies => -ppi_blocks_cyp2c19
  endo_bone (2)               postmenop, low_bmd => bone_risk
  bone_avoid (2)              bone_risk => -continue_ppi
  specificity_be (3)          barretts => -bone_avoid
  bone_urges_stop (1)         bone_risk => deprescribe_now
  no_abrupt_stop (3)          barretts => -deprescribe_now
  switch_if_cardiac (2)       cardiac_risk => switch_panto
  complex_case (2)            barretts, clopidogrel, postmenop, low_bmd => escalate
Key conclusions (7): continue_ppi, cardiac_risk, bone_risk, be_indication, switch_panto, escalate, deprescribe_now
Baseline: continue_ppi undecided; cardiac_risk, bone_risk, be_indication, switch_panto, escalate accepted; deprescribe_now rejected
```

```text
Prescribed Burn (June 2026)
Facts: heavy_fuels, dry_conditions, cultural_history, tribal_partner, community_downwind, sensitive_pop, wui_unit
Assumptions: smp_permit (on, block 2), forecast_exceed (off, block 1), recent_burn (off, block 1)
Rules (block in parentheses)
  r_strict_pm25 (strict)      forecast_exceed -> -legal_today
  r_permit_gives_legal (2)    smp_permit => legal_today
  r_prudential (1)            sensitive_pop, community_downwind => -legal_today
  r_ecology (1)               heavy_fuels, dry_conditions => elevated_risk
  r_eco_benefit (1)           elevated_risk, heavy_fuels => eco_benefit
  r_ecology_pro (1)           eco_benefit => conduct_burn
  r_wui_risk (1)              wui_unit => elevated_risk
  r_culture (1)               cultural_history, tribal_partner => good_fire
  r_culture_pro (1)           good_fire => conduct_burn
  r_airshed (1)               community_downwind, sensitive_pop => smoke_harm
  r_airshed_con (1)           smoke_harm => -conduct_burn
  r_postpone_smoke (1)        smoke_harm => postpone_burn
  u_recent_burn (1)           recent_burn => -r_eco_benefit
  r_interval_short (1)        wui_unit => short_interval
  r_interval_ok (2)           heavy_fuels => -short_interval
Key conclusions (6): conduct_burn, elevated_risk, smoke_harm, legal_today, postpone_burn, short_interval
Baseline: conduct_burn undecided; elevated_risk, smoke_harm, legal_today, postpone_burn accepted; short_interval rejected
```

```text
NBA Rebuild (June 2026)
Facts: non_contender, young_core, top5_draft, below_apron, has_firsts, flat_2019, apron_categorical, process_cautionary
Assumptions: over_apron (off, block 1), expansion_pending (off, block 3)
Rules (block in parentheses)
  r_apron_strict (strict)     over_apron -> -stack_vets
  r_classic (1)               non_contender, top5_draft => classic_rebuild
  r_tank_classic (1)          classic_rebuild => tank
  r_pick_value (1)            non_contender, top5_draft => pick_premium
  r_dilution (3)              expansion_pending => talent_dilution
  r_pick_via_dilution (3)     talent_dilution => pick_premium
  r_tank_pick (3)             pick_premium => tank
  r_dev (3)                   young_core, non_contender => dev_first
  r_dev_tank (3)              dev_first => -tank
  r_stack (1)                 has_firsts, young_core, non_contender => stack_vets
  r_preserve (3)              apron_categorical, below_apron, has_firsts => preserve_flex
  r_preserve_vs_stack (3)     preserve_flex => -stack_vets
  r_flat_undercut (3)         flat_2019 => -r_pick_value
  r_process_undercut (3)      process_cautionary => -r_classic
  r_lottery_pro (1)           flat_2019, non_contender => lottery_math
  r_lottery_con (1)           flat_2019 => -lottery_math
Key conclusions (8): tank, stack_vets, dev_first, classic_rebuild, pick_premium, lottery_math, talent_dilution, preserve_flex
Baseline: tank, stack_vets, classic_rebuild, pick_premium rejected; dev_first, preserve_flex accepted; lottery_math undecided; talent_dilution absent
```

## Appendix C: records

| Record | Path or commit |
| --- | --- |
| Consolidated proposal (Tim) | `docs/scenario-reconstruction-proposal-20260910.md` |
| Review of the first proposal (David) | `docs/scenario-reconstruction-response-20260910.md` |
| Implementation note | `docs/operations/scenario-reconstruction-implementation-20260910.md` |
| Behavioural tests | `tests/test_reconstructed_scenarios.py` |
| June scenarios | commit `7452f26` (June 30, 2026) |
| Reconstruction commit | `1241851` (September 11, 2026) |
| Release receipt | `docs/operations/scenario-refinement-release-20260911.json` |
