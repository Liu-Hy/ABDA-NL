# ADR 0003: Model routing and cost controls

Status: Accepted

Date: 2026-08-17

## Context

ABDA-NL needs three ways to pay for model calls:

1. CloudBank-funded Azure Foundry deployments for registered users with trial credit.
2. OpenRouter as a temporary service-outage route, paid by the project owner.
3. User-provided keys, which do not consume project trial credit.

Model names alone are not a safe routing policy. A model can appear in a provider catalog without being deployed in our Azure project. Provider names and prices also change quickly. Most importantly, a strong general benchmark does not establish reliable structured editing for ABDA-NL.

Live checks on 2026-08-17 established the following provider reality:

- The Azure Foundry catalog advertised newer Claude, GPT, DeepSeek, and Qwen models, but deployment probes for the new candidates returned `404 DeploymentNotFound`. The usable project deployments remained Claude Sonnet 4.6, GPT-5.4 mini, and GPT-5.5. Catalog visibility is therefore not treated as deployment availability.
- Google released stable Gemini 3.7 Flash on 2026-08-13. It supports function calling and structured outputs, and OpenRouter exposed a privacy-compatible tool route during the live gate.
- Anthropic launched Claude Sonnet 5 at $2 per million input tokens and $10 per
  million output tokens, then announced that this would remain its standard
  price. The catalog records that direct price. The OpenRouter route ceiling
  remains at the more conservative $3/$15 level.
- OpenAI documents GPT-5.6 Luna, Terra, and Sol at $0.20/$1.20, $2/$12, and $5/$30 per million input/output tokens, respectively.
- OpenRouter exposes model-specific provider routes, exact response cost, price ceilings, parameter compatibility filters, and data-collection filters. Its credit purchases add a 5.5 percent fee even though inference prices have no markup.

The direct CloudBank deployment probes were:

| Candidate route | API surface | Result |
| --- | --- | --- |
| `cloudbank-claude-sonnet-5` | Anthropic Messages | HTTP 404, `DeploymentNotFound` |
| `cloudbank-gpt-5.6-terra` | Azure Responses | HTTP 404 |
| `cloudbank-deepseek-v4-flash` | Azure chat completions | HTTP 404 |
| `cloudbank-qwen3.6-plus` | Azure chat completions | HTTP 404 |

These routes remain executable evaluation candidates in the catalog, but no
public profile selects them. The operator can rerun a smoke test and the full
gate without adding code after CloudBank supplies a working deployment name.

## Decision

ABDA-NL keeps a versioned catalog in `app/llm/models.yaml`. It separates four concepts:

- A model specification records family, display name, context limit, structured-tool support, and dated reference prices.
- A route records the adapter, provider, billing source, deployment identifier, canonical model, cost ceiling, and accounting policy.
- A logical profile selects a primary route and a service-outage route.
- A BYOK default selects a safe provider-specific starting model without accepting arbitrary endpoint URLs.

The profiles are product choices, not permanent model aliases. A profile can change only after the ABDA evaluation suite verifies grounded chat, valid edit proposals, semantic review behavior, latency, and cost. Browser and HTTP funded access advertise and accept only profiles whose `public_ready` flag is true in every environment. Candidate routes remain directly selectable through the evaluation CLI.

The selected routes are:

| Profile | Primary | Outage fallback | Public status |
| --- | --- | --- | --- |
| Economy | CloudBank GPT-5.4 mini | OpenRouter Gemini 3.7 Flash | Hidden pending quality acceptance |
| Balanced | CloudBank Claude Sonnet 4.6 | OpenRouter Gemini 3.7 Flash | Public |
| Quality | CloudBank GPT-5.5 | OpenRouter GPT-5.6 Terra | Hidden pending a complete primary-route gate |

Gemini 3.7 Flash is the balanced fallback because it passed every ABDA case, was inexpensive, had acceptable interactive latency, and diversifies the model family and provider path from the Claude primary. GPT-5.6 Terra remains a validated secondary option. GPT-5.4 mini remains hidden because repeated clean-edit reviews produced false positives even after deterministic normalization. A cheaper but unreliable reviewer is not a user-friendly public option.

OpenRouter is an outage route, not a silent substitute for an individual poor answer. Failover is limited to transport errors, timeouts, throttling, and provider 5xx responses after bounded primary retries. Authentication errors, invalid requests, missing deployments, and grounding-validator failures do not trigger paid failover.

Every OpenRouter request applies these provider constraints:

- Sort compatible providers by price and allow provider fallback.
- Require support for all requested parameters.
- Deny providers that may collect user data.
- Require an endpoint that OpenRouter marks as Zero Data Retention.
- Reject routes above the catalog's conservative input and output price ceilings.

The public OpenRouter BYOK list exposes only models with a current ZDR endpoint
that supports the required tool parameters. Qwen 3.6 remains available as an
evaluation route, but is not advertised for BYOK because its current endpoints
do not meet that combined contract.

## Accounting and safety controls

Every physical provider attempt receives its own conservative reservation. This is required because one browser action can make several calls through proposer retries, semantic review, or chat grounding retries. Metered Anthropic routes disable the SDK's internal retry layer and use only the application's bounded retry wrapper, so every repeated network attempt receives a separate reservation and audit event.

OpenRouter responses settle from the provider-reported `usage.cost`, rounded to microdollars, then apply a 1.055 multiplier for the documented credit-purchase fee. Responses that report a charged provider failure are also settled. A failed response that includes usage or provider cost settles that known amount, including a completed response that fails structured-output validation. A provider-declared uncharged error or a transport failure proven to occur before dispatch releases its reservation. An indeterminate read, write, successful-response parsing failure, or successful result without billing metadata settles the full conservative reservation immediately. Its audit event is marked `billing_uncertain`. OpenRouter error objects returned inside an HTTP 200 response are treated as errors rather than successful empty completions.

A process or host loss can occur after provider dispatch but before usage is
settled. On the next startup, an expired pending reservation is charged at its
full conservative value in every attached ledger. Releasing an uncertain call
would let repeated worker failures exceed the advertised hard cap. The
`expired_charged` reservation status preserves evidence of this exceptional
path for operator reconciliation.

Three independent controls apply to project-funded fallback calls:

1. The user must have sufficient trial credit.
2. The global OpenRouter emergency ledger must have sufficient unreserved budget.
3. Paid evaluation runs reserve against an in-process run cap before each physical provider call.

Before public failover is enabled, staging uses an isolated operator drill. The
`abda-nl-outage-drill` command is restricted to the staging environment and is
a dry run unless the operator supplies an exact confirmation. It injects one
sanitized HTTP 503 classification into the same `FailoverClient` used by the
public router, then sends a fixed, content-free marker request through the real
balanced OpenRouter route. It temporarily enables only the database emergency
budget row while the deployed web revision still has failover disabled. A
`finally` path restores that row even when the provider rejects the request.
Successful acceptance requires matching settled trial and emergency
reservations, matching usage events, a positive provider-reported cost, no
pending emergency reservation, and restoration of the disabled state. The
subsequent deployment gate may enable public fallback only after this live
evidence passes.

The evaluation cap uses the full conservative reservation, not the previous case's average cost. A call that cannot fit is rejected before reaching OpenRouter, and remaining paid cases are skipped. The default global OpenRouter hard cap is $500. Raising it above $500 requires an explicit deployment acknowledgement. It cannot exceed $1,000 without a code and policy change.

As of the completed 2026-08-17 ZDR revalidation, the emergency ledger recorded
$3.352004 spent, no outstanding reservations, and $496.647996 available under
the $500 cap.

BYOK calls bypass project-funded ledgers but retain authentication, rate limiting, fixed provider endpoints, and request validation. A user key exists only in the request model and provider client for that call. It is not written to the database, session cookie, audit event, response, or application log. BYOK cannot turn the service into an arbitrary network proxy.

## Evaluation evidence

The candidate comparison used suite version 3, SHA-256
`079dc0f121da317b40cb050229492b2ded9f7ddd216b0bfa48c3ae9503477746`,
with 16 cases and three repetitions per case. Cost figures for OpenRouter
include the 1.055 owner-spend multiplier. These results remain historical
comparison evidence for routes that were not selected.

| Route | Passed | Failed cases | p95 wall time | Average cost per case | Gate |
| --- | ---: | --- | ---: | ---: | --- |
| CloudBank Claude Sonnet 4.6 | 48/48 | None | 7,520 ms | 15,645 microUSD | Pass |
| OpenRouter Gemini 3.7 Flash | 48/48 | None | 8,957 ms | 3,837 microUSD | Pass |
| OpenRouter Gemini 3.6 Flash | 48/48 | None | 9,663 ms | 8,509 microUSD | Pass |
| OpenRouter GPT-5.6 Terra | 48/48 | None | 8,655 ms | 10,468 microUSD | Pass |
| OpenRouter Claude Sonnet 5 | 45/48 | `review-clean-fire-rule` | 9,598 ms | 29,209 microUSD | Fail |
| OpenRouter DeepSeek V4 Flash | 46/48 | Two grounded-chat cases | 52,323 ms | 649 microUSD | Fail |

After ZDR was added, one exploratory run exposed a lexical false negative: a
grounded answer said the engine would `reject` a concern, while the rubric
accepted only `rejected`. Suite version 4 adds equivalent grammatical forms
for that case and no new semantic concept. A regression test covers the exact
wording. Both selected routes were then rerun from scratch on version 4,
SHA-256
`83345e9a6a6a13d0c3c25bac7810bd7042b48ecf6bd1ee6989a42f0773dce867`:

| Current production route | Passed | p95 wall time | Average cost per case | Provider calls | Artifact SHA-256 |
| --- | ---: | ---: | ---: | ---: | --- |
| CloudBank Claude Sonnet 4.6 | 48/48 | 7,982 ms | 16,349 microUSD | 57 | `544f8017350244fe1d7d1d83de8840ac86c8303d4d47b441f6a6967bf99fcd7b` |
| OpenRouter Gemini 3.7 Flash with ZDR | 48/48 | 10,621 ms | 3,627 microUSD | 57 | `cb2f4f37a2897ad1fc65732897cf549090ed9ab893685ee82a0104b8fbc1a215` |

Both runs had zero provider and parser errors. The OpenRouter run spent
174,080 microUSD and remained below its explicit 500,000 microUSD run cap.

GPT-5.4 mini passed 45/48 in the preceding full comparison. Targeted reruns
fixed two rubric and premise-note gaps, but five additional repetitions of the
clean-review case all produced unnecessary reviewer warnings. Economy
therefore remains non-public.

Additional paid smoke tests established that GPT-5.6 Sol and DeepSeek V4 Pro could use the required chat and tool surfaces. They were not promoted after cheaper candidates passed the complete gate. GPT-5.6 Luna was throttled during the tool matrix. The tested Qwen 3.6 routes had no tool endpoint that also satisfied the required data-collection policy. These models remain cataloged for later reevaluation, not production fallback.

On 2026-09-02, the public route facts were refreshed without making a paid
provider call. OpenRouter still listed `google/gemini-3.7-flash`, two serving
providers, the same $0.75/$3.75 per-million-token price, tool calling, and
structured output support. Its current routing documentation still supports
per-request `data_collection: deny` and `zdr: true`. Anthropic's release notes
and current Sonnet 5 model page state that its $2/$10 launch price became the
standard price. These checks did not change a selected route, request contract,
or admission ceiling, so the previously completed ABDA quality gates remain the
relevant behavioral evidence.

## Consequences

The UI and API can report the actual model, provider, route, billing source, and project-accounted cost for each completed operation. Provider-specific credentials remain server-side during funded calls.

Reference prices are dated evidence, not a promise about future provider billing. OpenRouter's exact reported cost controls settlement, while the route ceiling controls admission. The release checklist must refresh official prices, live route availability, and the ABDA quality gate before COMMA and after any fallback-model change.

Expected failures use sanitized API responses. Missing trial credit returns HTTP 402. Invalid BYOK selection or a rejected BYOK credential returns HTTP 400. A BYOK provider rate limit or account quota response returns HTTP 429 with a retry hint. Provider outage, disabled emergency capacity, route configuration failure, or accounting unavailability returns HTTP 503 with a request identifier for support. Raw provider response bodies and configuration details are never returned to the browser.

## Sources checked for this decision

- [Azure Foundry model list API](https://learn.microsoft.com/en-us/azure/foundry/openai/reference-preview-latest)
- [Claude models in Microsoft Foundry](https://learn.microsoft.com/en-us/azure/foundry/foundry-models/concepts/claude-models)
- [Deploy and use Claude in Foundry](https://learn.microsoft.com/en-us/azure/foundry/foundry-models/how-to/use-foundry-models-claude)
- [Azure model lifecycle guidance](https://learn.microsoft.com/en-au/azure/ai-foundry/concepts/model-lifecycle-retirement?view=azureml-api-2)
- [Anthropic model pricing](https://platform.claude.com/docs/en/about-claude/pricing)
- [Anthropic release notes](https://platform.claude.com/docs/en/release-notes/overview)
- [Claude Sonnet 5](https://platform.claude.com/docs/en/models/sonnet-5/whats-new-sonnet-5)
- [Google Gemini 3.7 Flash model](https://ai.google.dev/gemini-api/docs/models/gemini-3.7-flash)
- [Google Gemini API pricing](https://ai.google.dev/gemini-api/docs/pricing)
- [OpenAI GPT-5.6 Sol](https://developers.openai.com/api/docs/models/gpt-5.6-sol)
- [OpenAI GPT-5.6 Terra](https://developers.openai.com/api/docs/models/gpt-5.6-terra)
- [OpenAI GPT-5.6 Luna](https://developers.openai.com/api/docs/models/gpt-5.6-luna)
- [OpenRouter provider routing](https://openrouter.ai/docs/guides/routing/provider-selection)
- [OpenRouter Zero Data Retention](https://openrouter.ai/docs/guides/features/zdr)
- [OpenRouter usage accounting](https://openrouter.ai/docs/cookbook/administration/usage-accounting)
- [OpenRouter fees](https://openrouter.ai/docs/faq)
- [OpenRouter models API](https://openrouter.ai/api/v1/models)
- [OpenRouter Gemini 3.7 Flash](https://openrouter.ai/google/gemini-3.7-flash)
