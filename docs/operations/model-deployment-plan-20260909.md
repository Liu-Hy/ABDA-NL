# Model deployment and funding decision

The initial read-only inspection completed September 9, 2026 (02:14 UTC on
September 10). No feature registration, terms acceptance, cloud deployment,
billing change, key retrieval, or inference call was performed in that initial
inspection. Its findings below are retained as a dated decision record.

## Pinned versions, September 10 at 03:10 UTC

The authorized policy update completed at 03:10:44 UTC. GPT-5.6 Terra,
GPT-5.6 Sol, and DeepSeek V4 Flash 0731 now report `NoAutoUpgrade` and
`Succeeded`. Their exact models, versions, GlobalStandard capacity 500,
500 requests and 500,000 tokens per minute, and `Microsoft.DefaultV2`
guardrail are unchanged. All other deployments, including the scoped Opus
resource, are unchanged. The [policy receipt](model-deployment-plan-20260909/version-policy-20260910.json)
records the complete sanitized before/after comparison. No inference call
was made for this update.

This prevents a provider's new default version from bypassing application
qualification. The operator must monitor retirement dates, qualify a
replacement, and update the deployment explicitly before retirement.
Microsoft documents that a pinned deployment stops serving when its model
[retires](https://learn.microsoft.com/en-us/azure/foundry/openai/how-to/working-with-models).

## Current throughput, September 10 at 02:58 UTC

The approved moderate increase completed at 02:58:33 UTC. Every changed
deployment reports `Succeeded`, with its exact model, version, Standard SKU,
guardrail, and version-upgrade setting preserved. The
[before/after receipt](model-deployment-plan-20260909/moderate-throughput-20260910.json)
records the changes and quota readback. The
[preceding seven-model inventory](model-deployment-plan-20260909/model-throughput-20260910.json)
records the individual quota names and per-unit limits.

| Model | Requests per minute | Tokens per minute | Allocated capacity / quota |
| --- | ---: | ---: | ---: |
| GPT-5.6 Terra | 500 | 500,000 | 500 / 10,000 |
| GPT-5.6 Sol | 500 | 500,000 | 500 / 10,000 |
| Claude Sonnet 5 | 500 | 500,000 | 500 / 10,000 |
| DeepSeek V4 Flash 0731 | 500 | 500,000 | 500 / 10,000 |
| GLM 5.3 | 250 | 250,000 | 500 / 2,000 shared with Kimi |
| Kimi K3 | 250 | 250,000 | 500 / 2,000 shared with GLM |
| Claude Opus 5, unchanged | 5,000 | 5,000,000 | 5,000 / 10,000 |

The four smaller GlobalStandard deployments have separate model quota pools,
with 9,500 units still available in each. Fireworks has 1,500 shared units
available. Opus and all other deployments kept their previous allocations.
These Standard deployments use [token-based billing](https://learn.microsoft.com/en-us/azure/foundry/foundry-models/concepts/deployment-types);
no provisioned capacity or fixed hosting reservation was purchased. Tests
still need pacing based on input plus reserved output tokens. A high request
limit does not make a lower token limit irrelevant.

## Approved and completed enablement, September 9, 2026

Following the user's authorization, the release agent registered
`Microsoft.CognitiveServices / Fireworks.EnableDeploy` and deployed the exact
GLM 5.3 and Kimi K3 models in the existing funded Foundry resource. An independent
read on September 10 at 02:47 UTC confirmed `Registered` and both deployments
`Succeeded`. The earlier `NotRegistered` state and pending-registration steps
below are historical, and are no longer rollout blockers.

The two existing deployments were subsequently raised from capacity 10 to 100
after checking their actual SKU limits and shared subscription quota. The
[sanitized before/after receipt](model-deployment-plan-20260909/fireworks-capacity-20260910.json)
records completion at 02:47:15 UTC. Both retain format `Fireworks`, version `1`,
SKU `DataZoneStandard`, `Microsoft.DefaultV2`, and `NoAutoUpgrade`:

| Deployment | Exact model | Capacity | Requests per minute | Tokens per minute |
| --- | --- | ---: | ---: | ---: |
| `abda-glm-5-3` | `FW-GLM-5.3` | 100 | 100 | 100,000 |
| `abda-kimi-k3` | `FW-Kimi-K3` | 100 | 100 | 100,000 |

At 02:47 UTC their shared `eastus2` Standard allocation was 200 of 2,000 units;
the later increase is recorded above.
Each unit provides one request and 1,000 tokens per minute. This changes rate
limits within the existing allocation. Microsoft explicitly identifies this
SKU as [pay per token](https://learn.microsoft.com/en-us/azure/foundry/how-to/fireworks/enable-fireworks-models),
so it does not create a provisioned-throughput reservation or fixed hosting
charge. Other deployments were unchanged by this update. No inference calls
were made by the capacity update.

The [Fireworks consent](https://aka.ms/fireworks-consent) and Azure billing
boundary described below still apply. Deployment authorization and successful
Azure billing setup do not constitute an independent certification of this
specific CloudBank award's reimbursement terms. The public Azure token prices
below are verified; an EA discount, if any, is not reflected. Application
feature qualification remains a separate gate before public model promotion.

DeepSeek V4 Flash 0731 has verified public Azure pricing. Grok 4.6's Azure
price remains unverified, so its prepared request does not authorize paid
acceptance or public promotion.

## Prices and exact identities

All amounts are USD per million tokens. Azure rates below are undiscounted
public retail rates for `eastus2`, not a negotiated Enterprise Agreement
price or proof of CloudBank award eligibility. The [retail-price receipt](model-deployment-plan-20260909/retail-prices.json)
retains exact meter IDs, units, dates, and the reproducible query. Azure's
[Retail Prices API](https://learn.microsoft.com/en-us/rest/api/cost-management/retail-prices/azure-retail-prices)
reports these meters per 1,000 tokens; the table multiplies those rates by 1,000.

| Exact model and deployment type | Azure input | Azure cached input | Azure output | OpenRouter input/output reference |
| --- | ---: | ---: | ---: | --- |
| `DeepSeek-V4-Flash-0731`, GlobalStandard | $0.44 | $0.014 | $1.32 | [From $0.05 / $0.16](https://openrouter.ai/deepseek/deepseek-v4-flash-0731), varies by provider |
| `grok-4.6`, GlobalStandard | Unverified | Unverified | Unverified | [Standard $2 / $6](https://openrouter.ai/x-ai/grok-4.6) |
| `FW-GLM-5.3`, DataZoneStandard | $2.10 | $0.39 | $6.60 | [Ordinary $1.40 / $4.40](https://openrouter.ai/z-ai/glm-5.3), with endpoint discounts |
| `FW-Kimi-K3`, DataZoneStandard | $3.30 | $0.33 | $16.50 | [Ordinary $3 / $15](https://openrouter.ai/moonshotai/kimi-k3), excluding premium endpoints |

The actual DeepSeek deployment reports `format=DeepSeek`,
`name=DeepSeek-V4-Flash-0731`, `version=2026-07-31`, GlobalStandard capacity
100, and `Succeeded`. The account catalog links the exact Azure model asset
at version `2026-07-31`. The [Azure catalog](https://ai.azure.com/catalog/models/DeepSeek-V4-Flash-0731)
and the dated OpenRouter `deepseek/deepseek-v4-flash-0731` entry identify the
same July 31 revision. This establishes catalog identity; it is not a claim
that every provider uses identical serving settings. The older April 23 model
and its lower prices are separate. Replace the unverified $0.10 / $0.40
placeholder with the exact GlobalStandard retail rates above before testing.

Grok's full public Retail Prices API product inventory and the
[Azure Grok pricing page](https://azure.microsoft.com/en-us/pricing/details/ai-foundry-models/grok/)
did not expose a 4.6 meter. The page lists older versions through 4.3.
OpenRouter's $2 / $6 is not an Azure quote. Grok should remain out of paid
acceptance until an Azure meter, deployment quote, or applicable EA price is
established. Kimi's rates also match the embedded regional prices on the
[Azure Fireworks page](https://azure.microsoft.com/en-us/pricing/details/ai-foundry-models/fireworks/).
GLM 5.3's exact Data Zone meters are present in the Retail Prices API even
though that page has not added its row.

## Live subscription and account evidence

The private CLI identity matches the approved ABDA session. The subscription
is enabled and reports `EnterpriseAgreement_2014-09-01`, spending limit Off.
The billing-property API confirms `EnterpriseAgreement` and returns no
offer/SKU or credit-eligibility field. The caller is not the billing account
administrator. Paginated billing-account enumeration returns no visible
accounts, and an exact billing-account read did not succeed. These reads
cannot certify which meters the CloudBank award reimburses.

The Foundry resource was matched privately to `.env`. It is an AIServices S0
account in `eastus2`, with project management enabled, one existing project,
and local key authentication enabled. Its ARM permissions include deployment
writes through inherited Contributor permissions, but no inference data
actions were returned. The intended endpoint can use a Foundry resource key;
this plan does not assume that an unrelated Azure resource's key will work.
Resource names, endpoint values, account identities, and credentials are
omitted from these artifacts.

Grok's live model metadata reports `xAI/grok-4.6/1`, GlobalStandard, Preview,
and `isMarketplaceRequired=false`. Its regional capacity endpoint reports
5,000 available capacity units. The SKU's default is 10, with 1,000 token and
one request per minute per unit. The proposed capacity 10 therefore requests
10,000 TPM and 10 RPM. The separate `maxCapacity=3` model field is not used
as the SKU limit; the SKU-specific capacity endpoint and SKU limits are the
relevant deployment checks.

## Fireworks decision

The live `Fireworks.EnableDeploy` feature is `NotRegistered`, with
`AutoApproval`, no registration metadata, and no authorization profile.
The returned feature description identifies Fireworks as a Non-Microsoft
Product and states that customer data leaves Microsoft systems and is not
covered by Foundry's data residency documentation. The exact terms link is
[Fireworks consent](https://aka.ms/fireworks-consent). The
[enablement instructions](https://learn.microsoft.com/en-us/azure/foundry/how-to/fireworks/enable-fireworks-models)
explicitly require reviewing those terms before selecting Register.

No organization-name attestation or external Fireworks account is required
by the returned registration metadata or the documented prerequisites.
The documented flow uses the existing Azure subscription/project and a
Foundry endpoint/key. It runs inference on Fireworks infrastructure and bills
through Azure. This does not establish funding under this specific EA award.
[Startup-credit guidance](https://learn.microsoft.com/en-us/startups/benefits/azure-credits/use-azure-credits#use-fireworks-models-on-foundry)
explicitly permits Fireworks consumption for that separate credit program;
those startup terms must not be substituted for the CloudBank agreement.

The concrete remaining decision is whether the project may accept this
Fireworks data-processing boundary and charge `Azure Fireworks Models`
consumption to its current CloudBank allocation. Registration must remain
unexecuted until that authority is established. No new Marketplace purchase
was established as necessary from this inspection; if deployment later
requires one, its actual offer and terms need review before acceptance.

## Prepared requests and bounded execution sequence

The [Grok request body](model-deployment-plan-20260909/grok-4.6.json) is based
on live account model and SKU metadata. The [GLM candidate](model-deployment-plan-20260909/fw-glm-5.3.candidate.json)
and [Kimi candidate](model-deployment-plan-20260909/fw-kimi-k3.candidate.json)
record the intended models, version 1, DataZoneStandard, capacity 10, and
the default guardrail. They are conditional candidates, not validated
deployment requests. Fireworks models are currently absent from both the
account and location model inventories, and their capacity lookups return
empty results. Exact SKU limits must be read again after authorized
registration. Public version-1 catalog entries exist for
[GLM 5.3](https://ai.azure.com/catalog/models/FW-GLM-5.3?publisher=Fireworks)
and [Kimi K3](https://ai.azure.com/catalog/models/FW-Kimi-K3).

1. Keep the existing Foundry resource/project and current funding scope.
   Establish Grok's Azure price before any Grok inference. Confirm the
   Fireworks funding and terms decision before its registration.
2. If authorized, register only `Microsoft.CognitiveServices / Fireworks.EnableDeploy`.
   Poll until Registered. The documented enablement can take 30 minutes.
3. Repeat `az cognitiveservices account list-models` and location capacity
   reads. Require the exact requested model/version, format `Fireworks`,
   SKU `DataZoneStandard`, capacity 10 within live limits, and sufficient
   quota. Do not substitute another model, choose PTU, or increase capacity
   if these checks fail. Resolve any newly returned Marketplace requirement.
4. Use the documented [ARM deployment schema](https://learn.microsoft.com/en-us/azure/foundry/foundry-models/how-to/create-model-deployments)
   to PUT each approved body to
   `{foundry-resource-id}/deployments/{deployment-name}?api-version=2025-06-01`.
   Proposed names are `abda-grok-4-6`, `abda-glm-5-3`, and `abda-kimi-k3`.
   A same-name existing deployment must be inspected before any update.
5. Read back exact model/version, SKU, capacity, guardrail, and Succeeded.
   Add catalog routes only after the intended Azure endpoint/key has been
   configured privately. Foundry's `/openai/v1/chat/completions` uses the
   deployment name as `model`, with no external Fireworks payment account.
6. Run the existing bounded CloudBank-only feature acceptance. Preserve the
   aggregate $100 ceiling and avoid OpenRouter fallback during testing.
   Tune prompts only for observed failures. Enable quota/BYOK selection only
   after the same exact model has passed the relevant feature contracts.

This inspection did not execute any step that changes cloud state. The
[manifest](model-deployment-plan-20260909/manifest.json) records remaining
preconditions so a prepared body cannot be mistaken for deployment approval.
