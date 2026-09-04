# Deterministic computation budget, 2026-09-04

This checkpoint records a source-level availability fix for the deterministic
argumentation engine. It does not record a public deployment. The live service
remains governed by the release sequence and source-license gate documented in
this directory.

## Problem and evidence

Request-rate limits bound how often a client can ask for a state, but they do
not bound the work performed by one valid request. Alternative derivations form
a Cartesian product, and attack discovery compares pairs of constructed
arguments. Before this change, 26 valid branching rules could keep one worker
busy for more than 12 seconds.

The largest bundled case, Popov v. Hayashi, uses 77 arguments, 24 attacks, 192
candidate combinations, and 74,533 subargument inspections during attack
discovery. A synthetic case with two alternative derivations at each of seven
levels produced 255 arguments from only 14 rules. These measurements justified
limits based on actual reasoning work rather than authored rule count alone.

## Implemented boundary

Source commit `77aa90d8fdaa4daff6fff28057381ac25ee40c14` applies the following
per-build ceilings:

| Work unit | Limit |
| --- | ---: |
| Fixpoint iterations | 100 |
| Premise-match inspections | 250,000 |
| Candidate combinations | 2,500 |
| Constructed arguments | 250 |
| One internal argument representation | 20,000 characters |
| Attack subargument inspections | 500,000 |
| Constructed attacks | 10,000 |

The limits are deterministic and do not depend on host speed. Candidate
products are accounted before enumeration, and representation length is
checked before allocating the new recursive string. This closes paths where a
small valid request could otherwise consume a worker through duplicate
combinations, missing-premise searches, deeply branching representations, or
dense attack analysis.

When a request crosses any boundary, the API returns HTTP 422 with error code
`scenario_too_complex` and a short suggestion to reduce rules or alternative
derivations. Internal diagnostics retain the specific exceeded boundary. The
response does not expose a traceback or turn the condition into a generic 500.

## Verification

The implementation checkpoint passed:

- the complete suite, 785 passed and 7 skipped
- Ruff across the repository
- compileall across application and test code
- all six scenario validators and expected-label snapshots
- focused engine, serialization, integration, semantic, and API error tests
- regression tests for every new work-unit boundary

The complete canonical state JSON for all six bundled scenarios was compared
with parent commit `78ce0a20885ff76fc12eb378edbb686ce58bf7e6` and was identical. The
existing canonical SHA-256 values remained unchanged. The former 26-rule
adversarial case was rejected locally in about 3 milliseconds. That timing is a
diagnostic observation, not a service latency guarantee.

## Release consequence

This change requires no schema migration and does not change a successful
bundled result. A future cumulative image should still pass CI, CodeQL, the
bounded public capacity smoke, sanitized-log audit, and compatible rollback
rehearsal. Publishing that image remains blocked until the imported engine's
redistribution terms are resolved.
