# Final hosted catalog promotion preparation

The final promotion is prepared without hosted writes. The web draft changes only its image and revision suffix; the persistent manual migration-job draft changes only its image. All existing settings remain intact. The final image field is an intentionally invalid placeholder until the verified digest is available. Exact protected paths and SHA-256 hashes are in [the machine-readable plan](hosted-final-rollout-plan-20260910.json).

The source is `00d773123e1e04481c68ebad7b10d6a93e70da86`, tagged `service-image-demo-revision-qualified-20260910`. Its eight-model catalog has SHA-256 `2a0090bbac38e18cbe189c8b088faba86154baeace1624fa3c9eb63bc6dc8c88`. Final image CI, cryptographic and security verification, and the remaining 48 sensitivity observations are separate release gates. Root reviews the final bound payload hashes before execution.

Fresh protected reads at 07:38 UTC on September 10 confirmed the healthy revision `abda-nl-stg-web--compat-8f83-0910-recovery-ready`, one healthy replica, one Container App, one manual migration job, and no running job execution. The app and job both use the verified schema-0006 recovery image. Every resolved environment value and secret value matches [the previously verified model-readiness state](hosted-model-configuration-readiness-20260910.json).

No schema migration, grant reconciliation, secret update, or activation-flag transition is required. The named grant policy is already active under schema `20260909_0006`. The final image keeps authentication, identity, credits, provider endpoints, secret references, CloudBank project and quota settings, the ADC mount, probes, scale, and resources unchanged.

The protected local binder will verify the draft hashes, the admitted catalog hash, and the exact source/image binding in the release agent's receipt. It then creates three new mode-600 payloads for the web update, migration-job update, and read-only after-state inspection. It has no network or cloud-write operation. Eight offline controls pass, covering changes on a copy, preservation of every non-image field, rejection of mutable or missing images, rejection of modified drafts, and secret-reference precedence.

The execution sequence is:

1. Bind the verified image after CI and supplemental acceptance, then obtain root's review of the exact final payload hashes.
2. Recheck identity, configuration, writers, and health for drift. Run the existing restricted-role read-only ledger inspection and preserve the private before-state.
3. Update the persistent manual job to the final image while preserving its entrypoint and settings. Do not run its migration command.
4. Update the web template. Require the exact ready revision `abda-nl-stg-web--qualified-eight-0910`, exact image, healthy replicas, and successful provisioning. Reconcile an empty successful PATCH response with fresh resource reads before retrying anything.
5. Verify public health, static and scenario flows, the eight admitted models, the matching BYOK pool, and every funding and credit setting. Confirm the previous revision has drained.
6. Run the restricted read-only ledger after-check using the final image. Preserve $50 named grants, historical spending, future entitlements, public accounting, and the independent emergency cap, accounting separately for concurrent public activity.
7. Run [the approved synthetic hosted MCP acceptance](hosted-native-mcp-acceptance-plan-20260910.md) against this exact ready image. Always complete fixture retirement and repeated token-revocation proof, including after any failed native phase.

The recovery templates pin `ghcr.io/liu-hy/abda-nl@sha256:11244a0df0b78c236945e0ef7a93add6acebf655e2758225d841276483812c44`, the already deployed and verified `8f83ac9` image. Recovery keeps schema 0006, named activation, grants, and funding configuration intact, with the historical `balanced` public profile. It does not restore schema 0005 or reverse accounting. The [completed recovery receipt](hosted-recovery-rollout-result-20260910.json) records its actual hosted verification.

No image has been bound or applied by this preparation, and no inference call was made. The synthetic native-client steps have been approved separately but remain unexecuted until root supplies the final verified image and ready revision.

The later [binding receipt](hosted-final-rollout-bound-20260910.json) records the verified `d61ef30a` image at exact source `00d7731` and root approval of all three bound payloads. At 07:49 UTC, the approved [read-only preflight](hosted-final-rollout-preflight-20260910.json) also passed. Its complete private ledger report has the same SHA-256 as the verified recovery proof, including the $50 registered grant, four future entitlements, spending, program totals, emergency budget, and restricted-role privileges. There are no pending reservations, and persistent application and job configuration, identity, and secrets are unchanged. Images and native-client fixtures remain unmodified while the final sensitivity supplement is pending.
