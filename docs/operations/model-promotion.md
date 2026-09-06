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

The same four candidate deployment names were probed again on 2026-09-04
through one isolated grounded-chat case per route. Every request returned HTTP
404, every route recorded exactly one failed provider call, and all four
reported zero metered cost. OpenRouter fallback was not allowed. The private
report is
`artifacts/evals/20260904-cloudbank-candidate-availability-refresh.json`, with
SHA-256
`55f2bb22869bef913ab0d183694a43ecb217f1b986f1c817ff123378001cac5d`.
This refresh confirms only that those exact deployment names are still absent
from the configured project. It cannot discover differently named deployments
without Azure control-plane access.

The validated primary remains `cloudbank-claude-sonnet-4-6`. It passed all 48
cases on suite version 4, SHA-256
`83345e9a6a6a13d0c3c25bac7810bd7042b48ecf6bd1ee6989a42f0773dce867`,
on 2026-08-17. The validated outage route remains
`openrouter-gemini-3.7-flash`, which also passed all 48 cases with per-request
Zero Data Retention and no-data-collection enforcement. This is a deployment
and evaluation decision, not a claim that Sonnet 4.6 is the newest model.

The complete raw reports remain in the gitignored operator evidence directory
because they contain full model responses. Their identities and summaries are:

| Route | Report SHA-256 | Gate | Average reported cost | p95 wall time |
| --- | --- | --- | --- | --- |
| `cloudbank-claude-sonnet-4-6` | `544f8017350244fe1d7d1d83de8840ac86c8303d4d47b441f6a6967bf99fcd7b` | 48 of 48, no errors | $0.0163485 per case | 7.982 seconds |
| `openrouter-gemini-3.7-flash` | `cb2f4f37a2897ad1fc65732897cf549090ed9ab893685ee82a0104b8fbc1a215` | 48 of 48, no errors | $0.0036267 per case | 10.621 seconds |

The OpenRouter report recorded $0.174080 total paid spend under a $0.50 run
cap. The CloudBank report recorded $0.784728 of metered provider cost with no
operator-paid spend. Recompute the report hashes before citing or promoting
this evidence.

## Public route refresh on 2026-09-02

The selected OpenRouter fallback was rechecked against current public provider
metadata without making a paid call. `google/gemini-3.7-flash` remained
available from two providers at $0.75 per million input tokens and $3.75 per
million output tokens, with tool calling and structured outputs. OpenRouter's
current routing contract still supports both `data_collection: deny` and
per-request `zdr: true`, which the application sends together.

Anthropic's release notes and current Sonnet 5 page also state that its $2/$10
launch price became the standard direct price. The catalog already contains
that price. The unused OpenRouter Sonnet 5 route deliberately retains its
higher $3/$15 admission ceiling, so this correction does not loosen a spending
boundary. No selected route, deployed model name, request contract, or public
profile changed, and no new model evaluation was required for this metadata
refresh.

## Public route refresh on 2026-09-04

A second content-free refresh confirmed that OpenRouter's public model metadata
still exposes `google/gemini-3.7-flash` with the required tool and structured
output support. Google's official pricing now states that Gemini 3.7 Flash costs
$0.75 per million input tokens and $3.75 per million output tokens through
2026-12-31, then $1.50 and $7.50 starting 2027-01-01. The route's existing
$1.50/$7.50 admission ceilings already cover that announced increase.

Anthropic's official Sonnet 5 page continued to list $2/$10, while Microsoft
continued to list Sonnet 5 as Hosted on Azure. Neither fact proves a deployment
exists in this CloudBank project. The same-day bounded data-plane probes for the
four guessed candidate deployment names all returned 404. No selected route,
request contract, price ceiling, or public profile changed, so no model call or
repeat quality evaluation was warranted for this metadata refresh.

## Live route revalidation on 2026-08-28

After the external service prerequisites were completed, both validated routes
were rerun against the suite version 4 smoke subset with one repetition. The
subset covers grounded chat, a structured edit proposal, and semantic review.

| Route | Report SHA-256 | Result | Provider calls | Reported cost | p95 wall time |
| --- | --- | --- | --- | --- | --- |
| `cloudbank-claude-sonnet-4-6` | `e364e26ef94ccf6e591f1f7ff8d38408302efb11d9ecd05a4896b5f9cf42f1c2` | 3 of 3, no errors | 4 | $0.121448 CloudBank metering | 6.011 seconds |
| `openrouter-gemini-3.7-flash` | `4029bb4a7d3bda19565e6f5e4cfd4fa621d337668d79631d72e7eab5a98b399c` | 3 of 3, no errors | 4 | $0.014817 paid spend | 14.118 seconds |

The first OpenRouter attempt used a $0.05 local run cap. Its conservative
reservation could not fit under that cap, so the evaluator failed closed before
any provider call and recorded zero spend. The successful rerun used the same
$0.50 cap as the complete evaluation. Raw reports remain in the gitignored
operator evidence directory because they contain full model responses.

## Candidate probe

### Verified deployment inventory on 2026-09-06

After the operator authorized the private Delta Azure CLI session, the agent
ran the read-only inventory below. It derived the Foundry account from the
deployed application's endpoint and verified these 15 successful deployments.
No API key was retrieved, no model was called, and no deployment was created
or modified.

| Deployment name | Model version | API family |
| --- | --- | --- |
| `gpt-5.5` | `2026-04-24` | OpenAI |
| `gpt-5.4` | `2026-03-05` | OpenAI |
| `gpt-5.4-mini` | `2026-03-17` | OpenAI |
| `gpt-4o` | `2024-11-20` | OpenAI |
| `gpt-4o-mini` | `2024-07-18` | OpenAI |
| `o4-mini` | `2025-04-16` | OpenAI |
| `claude-opus-4-7` | `1` | Anthropic |
| `gpt-5.4-pro` | `2026-03-05` | OpenAI |
| `claude-opus-4-6` | `1` | Anthropic |
| `claude-sonnet-4-6` | `1` | Anthropic |
| `claude-haiku-4-5` | `20251001` | Anthropic |
| `gpt-5` | `2025-08-07` | OpenAI |
| `gpt-5-mini` | `2025-08-07` | OpenAI |
| `DeepSeek-R1-0528` | `1` | DeepSeek |
| `claude-sonnet-4-5` | `20250929` | Anthropic |

The result was `FOUNDRY_DEPLOYMENT_INVENTORY_LISTED_READ_ONLY`. Sonnet 5,
GPT-5.6 Terra, DeepSeek V4 Flash, and Qwen3.6 Plus are not in this account's
deployment list. The older DeepSeek R1 deployment is not an alias for V4.
The existing GPT-5.4 mini deployment does not override its failed quality gate.
Retain the fully evaluated Sonnet 4.6 primary and Gemini 3.7 Flash outage route.
This closes the deployment-inventory prerequisite without claiming that every
listed deployment has passed ABDA evaluation. Future candidate work can use
this exact inventory instead of repeating calls to guessed deployment names.

### Read the actual Azure deployment inventory

Do not infer a deployment name from the Foundry catalog or a model ID. The
following block is read-only. It can run through the authorized Delta CLI
profile or, as a manual alternative, in Cloud Shell. It verifies the ABDA-NL subscription,
reads the non-secret Foundry endpoint already configured on the web app, finds
the matching Cognitive Services account, and lists that account's deployed
models. It does not read an API key, deploy a model, change quota, or call a
model.

```bash
set -euo pipefail
ABDA_EXPECTED_SUBSCRIPTION='00e62f6e-2174-40b2-b428-8ebfd7c2ac54'
ABDA_EXPECTED_TENANT='040f05eb-33ab-462f-af54-fb4bedb055ae'
ABDA_EXPECTED_USER='hliu2@cloudbank.org'
ABDA_RESOURCE_GROUP='abda-nl-staging'
ABDA_APP_NAME='abda-nl-stg-web'

ABDA_ACTIVE_SUBSCRIPTION="$(az account show --query id --output tsv)"
ABDA_ACTIVE_TENANT="$(az account show --query tenantId --output tsv)"
ABDA_ACTIVE_USER="$(
  az account show --query user.name --output tsv | tr '[:upper:]' '[:lower:]'
)"
if [[ "$ABDA_ACTIVE_SUBSCRIPTION" != "$ABDA_EXPECTED_SUBSCRIPTION" || \
      "$ABDA_ACTIVE_TENANT" != "$ABDA_EXPECTED_TENANT" || \
      "$ABDA_ACTIVE_USER" != "$ABDA_EXPECTED_USER" ]]; then
  printf '%s\n' \
    'STOP: Azure Cloud Shell is using a different subscription, tenant, or user.' >&2
  exit 1
fi
printf '%s\n' 'azure_identity: verified'

ABDA_FOUNDRY_ENDPOINT="$(
  az containerapp show \
    --resource-group "$ABDA_RESOURCE_GROUP" \
    --name "$ABDA_APP_NAME" \
    --query "properties.template.containers[0].env[?name=='AZURE_ANTHROPIC_ENDPOINT'].value | [0]" \
    --output tsv
)"
ABDA_FOUNDRY_HOST="${ABDA_FOUNDRY_ENDPOINT#https://}"
ABDA_FOUNDRY_HOST="${ABDA_FOUNDRY_HOST%%/*}"
case "$ABDA_FOUNDRY_HOST" in
  *.services.ai.azure.com) ;;
  *) printf '%s\n' 'STOP: the configured Foundry endpoint is not recognized.' >&2; exit 1 ;;
esac
ABDA_FOUNDRY_ACCOUNT="${ABDA_FOUNDRY_HOST%%.*}"
ABDA_FOUNDRY_RESOURCE_GROUP="$(
  az cognitiveservices account list \
    --query "[?name=='$ABDA_FOUNDRY_ACCOUNT'].resourceGroup | [0]" \
    --output tsv
)"
if [[ -z "$ABDA_FOUNDRY_RESOURCE_GROUP" || \
      "$ABDA_FOUNDRY_RESOURCE_GROUP" == 'None' ]]; then
  printf '%s\n' \
    'result: FOUNDRY_ACCOUNT_NOT_VISIBLE_IN_THIS_SUBSCRIPTION' \
    'No Azure resource was changed. Stop and send this result to Codex.'
  exit 0
fi

az cognitiveservices account deployment list \
  --resource-group "$ABDA_FOUNDRY_RESOURCE_GROUP" \
  --name "$ABDA_FOUNDRY_ACCOUNT" \
  --query "[].{deployment:name,model:properties.model.name,version:properties.model.version,format:properties.model.format,state:properties.provisioningState}" \
  --output table
printf '%s\n' 'result: FOUNDRY_DEPLOYMENT_INVENTORY_LISTED_READ_ONLY'
```

The final table contains deployment names and model metadata, not credentials.
Send only that table and the final `result` line to Codex. If the account is not
visible, the script reports that boundary without trying a data-plane request.
The `az cognitiveservices account deployment list` command is documented in the
[Azure CLI deployment reference](https://learn.microsoft.com/en-us/cli/azure/cognitiveservices/account/deployment?view=azure-cli-latest#az-cognitiveservices-account-deployment-list).

If a desired model is absent, open the matching Foundry resource and use
**Deployments**, then **Deploy model**. Keep the deployment name identical to
the model ID unless there is a concrete reason not to. Do not create or change
a deployment merely to complete this inventory step.

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
- [OpenRouter Gemini 3.7 Flash](https://openrouter.ai/google/gemini-3.7-flash)
- [Anthropic release notes](https://platform.claude.com/docs/en/release-notes/overview)
- [Claude Sonnet 5](https://platform.claude.com/docs/en/models/sonnet-5/whats-new-sonnet-5)
