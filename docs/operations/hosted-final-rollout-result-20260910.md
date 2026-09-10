# Final hosted rollout, 2026-09-10

The eight-model release is healthy at `abda-nl-stg-web--qualified-eight-0910`. The web application and persistent manual migration job both use source `234ffc97522b5d82e0a4a4d05082d88a4ab0c173`, image `sha256:a9a0cf2cbef909624f853e120a44fd5714e3cd5168821d2d2ee4fd4ccc002d73`.

The old revision is inactive with no replicas. Live and ready checks returned HTTP 200. The public quota and BYOK catalogs expose the same eight qualified models. Only the image and web revision suffix changed; funding identities, provider settings, OIDC, named-credit activation, secrets, probes and scale settings were preserved. The migration command was not executed during this image promotion.

Restricted read-only SQL inspection confirmed schema `20260909_0006`, one registered named administrator with a $50 lifetime grant, four future named entitlements, preserved historical spending and pool balances, and zero pending reservations. The complete before and after ledger reports have the same SHA-256, `f28bacb8ab4614cb8172c28c61543f0153b203554920957047042e8eeba89d0f`.

[Hosted browser acceptance](hosted-public-ui-acceptance-20260910.md) separately verifies the served assets, model menus, editable question insertion and all six baseline scenario graphs. Native subscribed-client acceptance and its synthetic-account cleanup are recorded separately. A real administrator owner session was unavailable, so the live owner sign-in boundary was not impersonated.

The [machine-readable rollout receipt](hosted-final-rollout-result-20260910.json) binds the exact release, payload, resource and ledger evidence. This rollout and its deterministic acceptance made no server inference calls.
