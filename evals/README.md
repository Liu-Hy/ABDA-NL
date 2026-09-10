# Funded application evaluations

This suite checks whether each selected model works correctly in ABDA. Public
benchmarks determine general model selection. These tests do not rank models or
retest whether a newer model is generally stronger than its predecessor.

Test every selected model on every exposed feature. Tune a prompt when and only
when inspection of the recorded failures shows a need. Preserve passing prompts.
A shared prompt change requires regression across all affected models and
features. Cases marked `split: regression` provide examples to hold aside while
diagnosing and tuning failures.

The suite covers all six bundled examples, custom and imported scenarios,
grounded chat, selected-item questions, corpus questions, sensitivity, all four
proposal tasks, refinement, and semantic review. Every feature has routine,
ambiguous, adversarial, and edge cases. Three repetitions are the default.
Automatic checks include exact quotations against source text, label claims
against computed state, edit polarity and targets, field preservation, pending
proposition promotion, and unchanged state before Apply. Answers and operations
also require identified review for grounding, semantic fidelity, usefulness,
and presentation before a model receives application acceptance.

The evaluation budget is one lifetime maximum of $100 (100,000,000 microUSD),
shared by Azure and GCP routes, all processes, retries, smoke checks, tuning,
regressions, and resumed runs. The fixed ledger is
`artifacts/evals/cloudbank-budget.sqlite3`. Each physical provider attempt reserves
its conservative maximum charge before dispatch. Reconciliation uses the route's
verified prices and provider usage. Uncertain charges remain committed. A new
output file or run never resets the ledger. `--paid-run-cap-microusd` can impose
a smaller limit on a run; it cannot raise the $100 lifetime ceiling.

Verified upward pricing corrections use separate, idempotent ledger adjustments
bound to the hash of a calculation receipt. They consume both the original run's
allowance and the lifetime allowance without rewriting physical-call records.
An operator pause does not prevent recording a known additional charge.

The ledger uses full synchronous rollback-journal transactions and an additional
atomic directory mutex. The repository lives on NFS, so this secondary lock avoids
depending on SQLite's advisory file locks alone. Existing locks are never deleted
on a timeout. If a writer is interrupted while holding the lock, verify that its
recorded host/process or Slurm job has stopped before recovering that lock.
Retain pending reservations until there is a verified billing receipt. Do not
delete or replace the ledger to continue testing. See SQLite's
[network filesystem guidance](https://www.sqlite.org/atomiccommit.html#_broken_locking_implementations).

Use the funded launcher, which passes only Azure/GCP credentials from the private
environment file into a fresh child process and isolates synthetic usage events
from the public account database. The evaluation child never loads the root
`.env`, rejects inherited OpenRouter credentials, and blocks generation requests
outside Azure/GCP at the HTTP transport, including redirect targets. The legacy
`--allow-openrouter-spend` flag is rejected. Live OpenRouter behavior remains
unverified under the CloudBank-only testing authorization.

A short availability check can run locally after the model deployment and prices
are verified. The six smoke cases include chat, every proposal type, and review:

```bash
.venv/bin/python -m app.evals.funded \
  --route cloudbank-gpt-5.6-terra --smoke --repetitions 1 \
  --phase availability --paid-run-cap-microusd 2000000 \
  --output artifacts/evals/terra-availability.json --no-fail-on-gate
```

Full runs belong in one Slurm allocation. Submit from the repository root, using
the user's valid allocation and partition. Pass only qualified funded routes:

```bash
mkdir -p artifacts/evals
sbatch --account=YOUR_ALLOCATION --partition=YOUR_PARTITION \
  evals/run_cloudbank.slurm \
  --route cloudbank-gpt-5.6-terra --route cloudbank-gpt-5.6-sol \
  --workers 2 --repetitions 3 --phase baseline
```

The available Delta allocation for the September 9 smoke check was
`bhay-delta-gpu`, with an immediate slot on `gpuA40x4-interactive`. That run used
`--gpus-per-node=1 --mem=8G --time=01:00:00` because no CPU allocation was
available, and released the allocation after 57 seconds. The GPU was reserved
only to obtain a permitted Slurm slot for this network workload. Check current
allocation availability before another run; never use an exhausted allocation.

The batch runs at most two model processes by default, sharing the same ledger.
Each evaluator saves an incremental `.checkpoint.jsonl` beside its JSON report.
To resume, keep the same output path, routes, cases, repetitions, phase, model
settings, and code/prompt/suite hashes and pass `--resume`. Changing those inputs
requires a new report, while lifetime spend remains shared. A batch can resume by
using its existing `--output-dir`. A successful process exit means the evidence
was collected; it does not imply application acceptance.

Reports contain full synthetic requests and returned drafts, including drafts
that application validation rejected. They include code, prompt, suite and catalog
hashes, model/deployment configuration, output/reasoning settings, usage events for
every physical retry, total cost, request duration, and a model-by-feature matrix.
`automated_gate_passed` describes deterministic checks.
`application_accepted` requires complete feature coverage and answer inspection.
If the budget stops a run, remaining cases stay incomplete.

To attach an inspection, create a JSON file with an identified `reviewer` and
`results` keyed as `route:case:repetition`. Each annotation must contain the exact
result's `evidence_sha256` as `response_sha256`, boolean `grounding`,
`semantic_fidelity`, `usefulness`, and `presentation` assessments, plus concrete
`notes` explaining the evidence. Keep failed assessments and unresolved cases in
the report. Do not infer approval from keywords or another model's success.

```bash
.venv/bin/python -m app.evals.review_report \
  --report artifacts/evals/terra-baseline.json \
  --reviews artifacts/evals/terra-answer-reviews.json \
  --output artifacts/evals/terra-reviewed.json
```

Keep the original baseline report and any later tuned report. If no prompt changes
were needed, the reviewed baseline is the evidence for retaining that prompt.
