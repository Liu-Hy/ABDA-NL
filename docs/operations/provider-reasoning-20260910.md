# Provider reasoning and parser evidence

The [preserved Fireworks smoke](evaluation-baseline-20260909.md#glm-and-kimi-follow-up)
found GLM proposal failures at 2,048 output tokens and GLM/Kimi review failures at
1,024 output tokens. The compatible adapter omitted the catalog's configured
`low` effort. These observations justify an adapter correction and a diagnostic
replay before deciding whether any prompt or output allowance needs changing.

| Route | Documented request setting now sent |
| --- | --- |
| Azure Fireworks GLM 5.3 and Kimi K3 | Top-level `reasoning_effort: "low"` |
| OpenRouter GPT, Gemini, GLM and Kimi | `reasoning: {"effort": "low"}` |
| Native GPT Responses and Gemini | Existing `reasoning.effort` and `thinkingConfig.thinkingLevel` settings |

The configured effort remains model-specific. This change forwards its actual
value, including an explicit omission, and preserves Claude and DeepSeek's
existing modes.

GLM 5.3 supports `low`, `high`, and `max`, defaults to `max`, and requires
thinking. Kimi K3 also always thinks, accepts those three effort levels, and
defaults to `max`. Its native API requires removing the older K2 `thinking`
field. These are vendor contracts, not measured Azure behavior.
([GLM model guide](https://docs.z.ai/guides/llm/glm-5.3),
[Kimi effort guide](https://platform.kimi.ai/docs/guide/use-reasoning-effort))

Fireworks documents the same compatible API for Foundry customers and supports
top-level `reasoning_effort`. Its detailed behavior table currently stops at
older GLM/Kimi versions. Consequently, `low` is a documented control to verify
on the exact Azure deployments, not a proven numeric thinking limit. Do not use
Fireworks' integer effort extension or combine its `thinking` and effort fields
without exact model support.
([Foundry integration](https://docs.fireworks.ai/ecosystem/integrations/azure-foundry),
[Chat Completions reference](https://docs.fireworks.ai/api-reference/post-chatcompletions),
[reasoning guide](https://docs.fireworks.ai/guides/reasoning))

OpenRouter's public model metadata was read without credentials on September 10,
2026. Terra, Sol, Gemini 3.8 Flash, Gemini 3.1 Pro Preview, GLM 5.3 and Kimi K3 all
advertise `low`. None advertises `supports_max_tokens` in its reasoning metadata.
The gateway's common `reasoning.effort` field therefore provides the supported
mapping; this does not establish a hard separate reasoning budget or prove live
fallback behavior. No OpenRouter generation was used for this check.
([reasoning controls and metadata contract](https://openrouter.ai/docs/guides/best-practices/reasoning-tokens),
[public model metadata](https://openrouter.ai/api/v1/models))

Kimi's native provider rejects a named forced tool while thinking. The demo now
sends `tool_choice: "required"` with its one advertised function on both routes,
then rejects multiple calls or the wrong function. Other compatible models keep
named tool choice. This avoids depending on the more permissive behavior seen
in the original Azure Kimi smoke.
([Kimi tool choice](https://platform.kimi.ai/docs/guide/use-tool-choice),
[Fireworks tool choice](https://docs.fireworks.ai/guides/function-calling))

The feature's total output cap is unchanged. Fireworks treats
`max_completion_tokens` as an alias of `max_tokens`, so renaming the field cannot
create room for a final tool payload. A later increase must also increase the
pre-dispatch reservation and stay within the model and evaluation limits.
([completion limit reference](https://docs.fireworks.ai/api-reference/post-chatcompletions))

HTTP adapter parser errors now carry a separate `diagnostics` attribute with
finish reason, requested cap, actual model, visible content, returned function
names/arguments, normalized usage, and a reasoning-token count when reported.
It contains no transport fields or reasoning text and is absent from public
error messages. Synthetic evaluation explicitly captures the allowed fields;
parser failures remain terminal for retry and fallback purposes. Native Gemini
also excludes thought-marked parts from visible answers while counting their
billable tokens.

The credential-free provider and routing regression passed 122 tests. Standard
and security Ruff checks passed. The bounded Azure replay still needs to establish whether low
effort resolves the recorded failures. Prompt tuning remains conditional on the
actual replay results.
