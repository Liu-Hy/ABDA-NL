# Additional model families, public evidence

Checked September 9, 2026. This note supports the model selection discussion.
It does not change the catalog, authorize provider spending, or claim that a
publicly listed deployment is enabled on the CloudBank subscription.

Grok 4.6 is the strongest additional family among the direct Azure candidates
examined. GLM 5.3 and Kimi K3 merit consideration through Fireworks on Foundry
if the actual CloudBank offer covers their Azure consumption. Mistral Medium
3.5 and Kimi K2.7 Code have material limitations for this demo.

Scores below use the public Artificial Analysis Intelligence Index, with the
reported reasoning setting. Prices are USD per million input/output tokens
from public OpenRouter endpoints. They are dated observations, not negotiated
Azure prices or estimates of one ABDA interaction's total token use.

| Model | Public AA score | OpenRouter input/output | Assessment |
| --- | ---: | ---: | --- |
| Grok 4.6 (high) | [44](https://artificialanalysis.ai/models/grok-4-6) | [$2 / $6](https://openrouter.ai/x-ai/grok-4.6) | Strong additional family. Azure supports tools and JSON. |
| Mistral Medium 3.5 | [15](https://artificialanalysis.ai/models/mistral-medium-3-5) | [$1.50 / $7.50](https://openrouter.ai/mistralai/mistral-medium-3-5/providers) | Hold. Azure explicitly reports no tool calling, and this score/price combination is unpersuasive for the requested capable pool. |
| Kimi K2.7 Code | [26](https://artificialanalysis.ai/models/kimi-k2-7-code) | [From $0.68 / $3.40](https://openrouter.ai/moonshotai/kimi-k2.7-code), commonly $0.95 / $4 | Hold as a general ABDA addition. Coding specialization and obligatory thinking introduce integration costs without a compelling broad benchmark advantage. |
| GLM 5.3 (max) | [45](https://artificialanalysis.ai/models/glm-5-3) | [Baseline $1.40 / $4.40](https://openrouter.ai/z-ai/glm-5.3), with endpoint discounts | Strong conditional candidate through `FW-GLM-5.3`. Confirm grant coverage and full feature behavior. |
| Kimi K3 (max) | [44](https://artificialanalysis.ai/models/kimi-k3) | [Commonly $3 / $15](https://openrouter.ai/moonshotai/kimi-k3) | Strong conditional candidate through `FW-Kimi-K3`, but substantially more expensive than GLM 5.3. Family preference can still justify it. |

The [direct Azure catalog](https://learn.microsoft.com/en-us/azure/foundry/foundry-models/concepts/models-sold-directly-by-azure)
marks Grok 4.6, Mistral Medium 3.5, and Kimi K2.7 Code as previews. Grok's
Azure context limit is 200,000 tokens, below OpenRouter's 500,000. A shared
configuration must respect the smaller limit. Mistral's Azure listing provides
128,000 input/output tokens and JSON, but explicitly says tool calling is not
supported. Its capabilities through Mistral's own API or OpenRouter do not
establish equivalent Azure support. Kimi K2.7 Code supports tools on Azure.

OpenRouter describes [Kimi K2.7 Code](https://openrouter.ai/moonshotai/kimi-k2.7-code)
as always thinking and preserving reasoning content across turns. The demo's
ordinary answer history cannot be assumed sufficient for that provider
contract. Its Code label alone is not a reason to reject it, but the broader
benchmark result does not justify prioritizing this older Kimi over K3.

[Grok's OpenRouter endpoints](https://openrouter.ai/x-ai/grok-4.6) include
ordinary SpaceXAI service, a more expensive priority tier, and Amazon Bedrock.
Provider selection should exclude AWS and respect the ordinary price ceiling.
For [Kimi K3](https://openrouter.ai/moonshotai/kimi-k3), the advertised minimum
of $2.40 / $12 came from a Relace endpoint reporting 59.66% uptime in the page's
current observation window. That price is unsuitable as the sole reliability
or budgeting assumption. AA's Grok high-setting first-token latency is
[43 seconds](https://artificialanalysis.ai/models/grok-4-6); OpenRouter's
all-settings endpoint latency uses a different measurement and should not be
substituted for it.

## Usage and broader candidates

The [OpenRouter rankings](https://openrouter.ai/rankings) show actual token
traffic, which is useful for discovering alternatives but is not a quality
score. The weekly list observed here placed GLM 5.3 Flash third and DeepSeek
V4 Flash 0731 fourth, while a free MiniMax M3 variant was ninth. Free variants
and mixed application workloads make a strict quality ranking inappropriate.
Grok, Mistral Medium, and Kimi were not in the displayed weekly top ten.

GLM 5.3 Flash has an attractive [AA score of 42](https://artificialanalysis.ai/models/glm-5-3-flash)
and [low OpenRouter prices](https://openrouter.ai/z-ai/glm-5.3-flash), but no
direct Foundry or listed Fireworks deployment for this exact Flash model was
established in this investigation. [Availability through Azure Databricks](https://learn.microsoft.com/en-au/azure/databricks/release-notes/product/2026/august)
would require a separate deployment path. MiniMax M3's
[AA score of 30](https://artificialanalysis.ai/models/minimax-m3) and
[low OpenRouter pricing](https://openrouter.ai/minimax/minimax-m3) make it a
budget alternative, although its benchmark result is less compelling than
GLM 5.3. These distinctions should remain visible when discussing additions.

## Fireworks funding and deployment boundary

Microsoft's [Fireworks on Foundry instructions](https://learn.microsoft.com/en-us/azure/foundry/how-to/fireworks/enable-fireworks-models)
list pay-per-token support for `FW-GLM-5.3`, `FW-Kimi-K3`, and `FW-MiniMax-M3`.
Setup requires an Azure subscription, Foundry project/resource, appropriate
Azure roles, and registration of `Fireworks.EnableDeploy`. The documented
prerequisites do not require a separate Fireworks account. Inference runs on
Fireworks infrastructure outside Microsoft's data residency commitments.
Per-token models have a 15-day retirement notice period, requiring maintenance.

Microsoft's [startup-credit guidance](https://learn.microsoft.com/en-us/startups/benefits/azure-credits/use-azure-credits#use-fireworks-models-on-foundry)
explicitly says Fireworks on Foundry is sold and billed through Azure and that
startup credits apply. It also directs users to check the chosen model,
deployment type, region, and credit eligibility. The accompanying
[Foundry sponsorship policy](https://learn.microsoft.com/en-us/startups/benefits/technical-benefits/azure-credits/foundry-model-sponsorship-coverage)
distinguishes direct Azure consumption from separately billed partner and
Marketplace purchases.

These are Microsoft for Startups terms. They establish that Fireworks models
are not inherently excluded from every Azure credit program, but do not prove
coverage under this particular CloudBank research award. The remaining
funding check is the actual subscription offer and meter eligibility. Public
catalog presence alone should neither enable self-paid use nor cause an
automatic exclusion as an external-account service.
