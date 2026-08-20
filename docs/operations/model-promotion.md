# Funded model promotion runbook

ABDA-NL treats a model catalog entry, an Azure project deployment, and a
quality-approved public profile as three different states. A Foundry model is
eligible for public trial traffic only after the CloudBank project can call the
deployment and the complete ABDA gate passes on that exact route.

## Current evidence

The live checks on 2026-08-17 used the configured CloudBank endpoints and
credentials without printing either value.

| Candidate route | API surface | Live result |
| --- | --- | --- |
| `cloudbank-claude-sonnet-5` | Anthropic Messages | HTTP 404, `DeploymentNotFound` |
| `cloudbank-gpt-5.6-terra` | Azure Responses | HTTP 404 |
| `cloudbank-deepseek-v4-flash` | Azure chat completions | HTTP 404 |
| `cloudbank-qwen3.6-plus` | Azure chat completions | HTTP 404 |

Microsoft Foundry currently documents Claude Sonnet 5, including Hosted on
Azure availability. That catalog fact does not create a deployment in the
CloudBank project. Foundry routes by the deployment name supplied in the model
field. The 404 results therefore block promotion until the CloudBank owner
deploys and authorizes one of these models.

The validated primary remains `cloudbank-claude-sonnet-4-6`. It passed all 48
cases on suite version 4, SHA-256
`83345e9a6a6a13d0c3c25bac7810bd7042b48ecf6bd1ee6989a42f0773dce867`,
on 2026-08-17. The validated outage route remains
`openrouter-gemini-3.7-flash`, which also passed all 48 cases with per-request
Zero Data Retention and no-data-collection enforcement. This is a deployment
and evaluation decision, not a claim that Sonnet 4.6 is the newest model.

## Candidate probe

1. Create the Foundry deployment in the same CloudBank project or obtain its
   exact endpoint, deployment name, and authentication method.
2. Put the deployment name in the matching gitignored `.env` variable listed in
   `.env.example`.
3. Confirm that the route appears without revealing credentials:

```bash
.venv/bin/abda-nl-eval --list-routes
```

4. Run the smoke subset and retain its JSON artifact:

```bash
.venv/bin/abda-nl-eval \
  --route cloudbank-claude-sonnet-5 \
  --smoke \
  --no-fail-on-gate
```

Replace the route ID for another candidate. A 401, 403, 404, unsupported API
surface, empty tool result, or missing usage record is a failed probe. Do not
route a deployment error through paid OpenRouter fallback during an evaluation.

## Complete quality gate

After the smoke subset passes, run the versioned suite at its default three
repetitions:

```bash
.venv/bin/abda-nl-eval --route cloudbank-claude-sonnet-5
```

Promotion requires every suite gate, including:

- grounded chat with no validator rejection
- schema-valid proposals with the required semantics
- clean-review precision and unsafe-edit recall
- zero provider or parsing errors
- acceptable p95 wall time
- acceptable average cost for the proposed trial policy
- a complete provider-call audit record for every physical call

Do not tune the evaluator to a candidate's observed mistakes. If a prompt needs
model-family tuning, make the prompt change explicit, rerun the existing public
primary to detect regression, then rerun the candidate. Record the suite
version, suite SHA-256, catalog version, route ID, deployment name, date, gate
summary, latency, and cost.

For an OpenRouter route, paid testing also requires
`--allow-openrouter-spend` and an explicit per-run cap. The global emergency
ledger and route price ceilings still apply.

## Promotion change

Only after the full gate passes:

1. Update the intended profile's `primary_route` in `app/llm/models.yaml`.
2. Keep `public_ready: true` only when both primary and outage routes have
   current evidence.
3. Update catalog tests, the model-routing ADR, and dated prices from primary
   provider sources.
4. Run the entire automated test suite.
5. Deploy the new Foundry deployment name through the secure Azure parameter.
6. Run one funded chat and one reviewed edit in staging, then inspect route,
   usage, cost, and ledger records.
7. Retain the previous deployment and image for rollback until the release has
   operated cleanly.

Never promote because of a general leaderboard alone. ABDA's structured edit
and semantic review tasks have already exposed failures in otherwise strong and
cheap models.

## Primary references

- [Claude models in Microsoft Foundry](https://learn.microsoft.com/en-us/azure/foundry/foundry-models/concepts/claude-models)
- [Deploy and use Claude in Foundry](https://learn.microsoft.com/en-us/azure/foundry/foundry-models/how-to/use-foundry-models-claude)
- [OpenRouter provider routing](https://openrouter.ai/docs/guides/routing/provider-selection)
- [OpenRouter Zero Data Retention](https://openrouter.ai/docs/guides/features/zdr)
