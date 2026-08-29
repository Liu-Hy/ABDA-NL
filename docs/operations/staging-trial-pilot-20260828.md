# Staging funded trial pilot

Date: 2026-08-28

State: `IMPLEMENTED_NOT_DEPLOYED`

This checkpoint defines the first CloudBank-funded trial for the live staging
service at `https://demo.abda-nl.org`. It is deliberately smaller than the
future public research-service allowance.

## Pilot limits

- the first 10 verified-email accounts that activate the trial can receive it
- each activated account receives 5,000,000 microdollars, which is $5
- the global allocation limit is 50,000,000 microdollars, which is $50
- an account cannot receive a second grant
- reservations and settlements cannot exceed an account's remaining grant
- OpenRouter failover remains disabled and its ledger must remain empty
- BYOK remains available and keys remain request-scoped rather than stored

The 10-user limit applies to funded-trial activation, not account registration.
Additional verified users may still sign in and use BYOK after all funded grants
have been claimed.

## Deployment boundary

The guarded transition is implemented by
`deploy/azure/gate5-trial-pilot.sh`. It accepts only the current healthy staging
revision or its exact resume state. After one explicit operator confirmation,
it changes only these Container App environment values:

```text
ABDA_TRIAL_ENABLED: false -> true
ABDA_TRIAL_MAX_USERS: 100 -> 10
ABDA_TRIAL_BUDGET_MICROUSD: 500000000 -> 50000000
```

The grant remains 5,000,000 microdollars. The script does not change the image,
secrets, database, migration, Auth0, DNS, certificate, scaling, health probes,
or OpenRouter setting. Azure single revision mode keeps the healthy revision in
service until the replacement revision is ready.

Before the update, the gate requires an empty trial ledger and an empty,
disabled OpenRouter ledger. After the update, it checks the exact public HTTPS
origin, authenticated LLM requirement, BYOK contract, funded profile, protected
metrics endpoint, application health, replica health, revision configuration,
and reconciled accounting limits.

## Acceptance sequence

1. Run the pinned Gate 5 script from Azure Cloud Shell and enter its exact
   confirmation phrase.
2. Require the result
   `TRIAL_PILOT_ENABLED_BROWSER_MODEL_TEST_REQUIRED` with a zero-use ledger.
3. Sign in at `https://demo.abda-nl.org` with a verified email address.
4. Activate the trial and confirm a $5 balance.
5. Run one request using the funded `balanced` profile.
6. Rerun the same pinned Gate 5 script without making another Azure change.
7. Require `TRIAL_PILOT_ACCOUNTING_VERIFIED`, zero pending reservations, and
   settled spend within the $5 user grant and $50 global limit.

Do not enable OpenRouter during this gate. Expansion beyond 10 funded users is
a separate promotion that requires reviewing real pilot usage, provider cost,
error handling, and accounting evidence.
