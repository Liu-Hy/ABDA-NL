# Hosted native MCP acceptance preparation

Completed on 2026-09-10: [the terminal native-client result](hosted-native-mcp-acceptance-result-20260910.md) records both successful subscribed workflows, independent browser verification, and complete cleanup. The original plan below and every failed attempt remain preserved as dated evidence. Its preparation statements do not describe pending work.

Prepared on 2026-09-10. This plan has not created an account or token, run a native model turn, or changed hosted configuration. The exact payload hashes, private paths, sequence, and remaining image bindings are in [the machine-readable plan](hosted-native-mcp-acceptance-plan-20260910.json).

The proposed acceptance exercises the final deployed MCP endpoint with existing subscribed Codex and Claude Code clients. Two disposable accounts have no ABDA credit, no institutional identity, and tokens limited to `projects:read` and `projects:write`. The authenticated fixture is limited to two immutable synthetic account identifiers. It does not test OIDC login or impersonate a registered administrator.

The current recovery image is `ghcr.io/liu-hy/abda-nl@sha256:11244a0df0b78c236945e0ef7a93add6acebf655e2758225d841276483812c44`, with schema `20260909_0006`. The fixture jobs pin that compatible image. Every hosted API and native-client phase must separately bind the final qualified image and its ready revision after CI and rollout. The persistent migration job configuration remains unchanged by these execution-only overrides.

## Execution and evidence

1. Recheck the final ready image, identity, funding configuration, schema, and writers. Run the restricted read-only fixture inspection and retain canonical hashes and row counts for all seven accounting tables.
2. Run the reviewed setup override once. It inserts only the two named synthetic fixture records, with no identity, entitlement, grant, reservation, or usage rows. Require unchanged accounting hashes.
3. Verify each synthetic owner session and an inactive, zero-valued `/api/trial` response. Create one project read/write token per fixture through the real owner API, expiring after one day. Keep raw tokens only in the protected credential file.
4. Run the existing native-client helper once for each subscribed client. Require the actual six-tool workflow: list examples, read an example, create a project, read it, apply one versioned assumption toggle, and read it again. The expected version changes from 1 to 2, and `legal_today` changes from accepted to rejected. Independent stale-version and invalid-operation checks must fail without mutation.
5. Confirm the project through its owner API and the actual hosted Chromium workspace. Require cross-owner read/write denial and missing-`llm:use` denial for both server question and proposal tools. A browser request guard blocks chat, proposal, refinement, and review inference paths.
6. Archive every fixture project, including any stranded attempt. Revoke every fixture token twice through the owner API, then require repeated MCP initialization to return HTTP 401.
7. Always run the restricted retirement override, including after a failed client phase. It archives only fixture projects, revokes only fixture tokens, and suspends and unverifies the two synthetic accounts while preserving audit records.
8. Run the final read-only inspection. Require complete cleanup and no fixture credit or usage. Compare all seven accounting tables with the initial proof, attributing unrelated public traffic separately if any. Verify the persistent migration job configuration remains unchanged. Remove only the raw native credential file after authoritative cleanup and revocation proof.

The seven accounting tables are `llm_usage_events`, `usage_reservations`, `emergency_usage_reservations`, `trial_grants`, `trial_programs`, `emergency_budgets`, and `named_credit_entitlements`. Raw SQL results, cloud configuration, sessions, and tokens stay in the mode-600 preparation directory named in the JSON plan. Public receipts contain only sanitized outcomes and hashes.

The proposed bounded Slurm allocation is one GPU, two CPUs, 8 GB, and 15 minutes under `bhay-delta-gpu` / `gpuA40x4-interactive`. It has not been submitted. A subscription authentication failure stops the native step. The workflow does not switch to API billing. No ABDA server inference is authorized by this plan.

## Prepared checks

The two existing client subscriptions were checked without inference, including the minimal child environment: Codex 0.153.4 and Claude Code 2.1.267. The native process environment excludes CloudBank, direct-provider, OpenRouter, session-signing, and MCP-pepper credentials. The helper uses an environment-held MCP bearer token and an explicit tool allowlist, both supported by the [official Codex MCP configuration](https://learn.chatgpt.com/docs/extend/mcp?surface=cli).

Twelve offline tests pass. They cover fixed synthetic identities, refusal to sign an arbitrary real-user session, the restricted database role, immutable images and stripped job environments, provider-credential exclusion, zero-credit gates, cleanup of completed and stranded projects, and exact binding of all three execution templates to the reviewed runner. All seven protected preparation files have recorded SHA-256 hashes and mode 600. The three current execution templates have a `.v2.execution.json` suffix. Earlier templates remain as historical artifacts and must not be executed.

[The hosted model readiness receipt](hosted-model-configuration-readiness-20260910.json) confirms configuration for all eight proposed models, including the separate funded Opus resource and the exact CloudBank Vertex project, quota project, ADC content, and mount. No credential change is needed. The first inspector incorrectly preferred an empty legacy literal over Azure's `secretRef`; that incorrect receipt is preserved, and the resolver now selects the actual referenced secret.

The referenced OpenRouter key matches the authorized source and returned HTTP 200 from the metadata-only `GET /api/v1/key` check. It reports a paid tier and available per-key limit. This verifies key metadata, not account-wide balance or model inference. The endpoint and metadata fields are documented in [OpenRouter's limits reference](https://openrouter.ai/docs/api_reference/limits). No OpenRouter inference or secret update was performed.

## Remaining boundaries

Root approved the exact protected fixture, native-client, and cleanup steps after reviewing the scripts and all seven payload hashes and modes. Execution remains held until root supplies the verified final image and ready revision after the release gates pass. No additional user operation is required for the approved synthetic workflow.

There is no existing authenticated browser session for the registered administrator. Its owner `/api/trial` sign-in acceptance remains unverified. The actual hosted $50 entitlement, preserved spending, future entitlements, and accounting invariants are proved separately by [the completed recovery receipt](hosted-recovery-rollout-result-20260910.json) and account-route regressions. This plan does not synthesize an administrator session.

The separate [funded MCP acceptance record](mcp-server-llm-acceptance-20260910.md) covers real CloudBank question and proposal calls through in-process MCP. Those results do not replace this hosted, native-client acceptance, and this plan does not repeat paid server tests.
