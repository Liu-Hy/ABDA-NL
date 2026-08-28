# External prerequisites checkpoint

Date: 2026-08-28

This record captures the non-secret external state verified through the Azure
staging infrastructure checkpoint. It does not prove that the application is
deployed or that any final release gate has passed.

## Azure subscription

The intended CloudBank-funded Azure subscription is enabled. The deploying
operator has effective `Contributor` and `Reader` access through Azure groups.
The providers required by the deployment templates are registered:

- `Microsoft.App`
- `Microsoft.Authorization`
- `Microsoft.ContainerRegistry`
- `Microsoft.DBforPostgreSQL`
- `Microsoft.ManagedIdentity`
- `Microsoft.Network`
- `Microsoft.OperationalInsights`

The public GHCR design does not require an Azure role assignment, managed pull
identity, or private Azure Container Registry.

The `abda-nl-staging` resource group now contains the reviewed network, private
DNS, Log Analytics workspace, Container Apps environment, and PostgreSQL
Flexible Server. The deployment `abda-nl-stg-infra` completed successfully from
source commit `a6a366ec199e1b0e2a89f8412d0e8a04b2bad4c5`. PostgreSQL reports
`Ready`, has no public network access, retains backups for seven days, and
contains the `abda` database. Log Analytics retains container logs for 30 days.
No Container App or migration job exists at this checkpoint.

## Domain and incoming mail

- `abda-nl.org` is active under operator control in Cloudflare.
- Cloudflare is authoritative for the zone and DNSSEC reports success.
- `support@abda-nl.org` and `privacy@abda-nl.org` are enabled exact-match
  forwarding rules.
- Both aliases delivered test messages to the monitored operator inbox, and
  the Cloudflare activity log recorded delivery.
- Catch-all routing is disabled.

The initial response owner is Haoyang Liu. The support and privacy aliases are
the public contact points, so the private destination address is not recorded
in the repository.

## Authentication mail

- `auth.abda-nl.org` is verified in Resend in `us-east-1`.
- Sending is enabled and receiving is disabled.
- SPF, DKIM, and DMARC passed on a delivered Auth0 test message.
- The authentication sender is `ABDA-NL <no-reply@auth.abda-nl.org>`.
- The Resend credential is stored only by Auth0 and the operator's private
  credential manager, not by ABDA-NL.

## Auth0 identity

- The United States production tenant and the `ABDA-NL Public Service`
  Regular Web Application exist.
- `login.abda-nl.org` is verified as the Auth0 custom domain with an
  Auth0-managed certificate.
- The public discovery document reports the exact issuer
  `https://login.abda-nl.org/`.
- Custom-domain notification links are enabled.
- Passwordless Email is the only application connection. It uses a six-digit
  one-time code with a five-minute expiry and permits first-time signup.
- The Resend-backed Auth0 provider delivered a test message with SPF, DKIM,
  and DMARC all passing.
- Suspicious IP throttling and brute-force protection use the approved default
  thresholds and block settings, with empty IP allowlists.
- Auth0 Dashboard MFA is enabled and its recovery code is stored privately.
- Dynamic client registration and automatic application connection enablement
  are disabled. Generic public-signup errors are enabled.
- The public discovery document advertises the OIDC end-session endpoint.
- The application client ID and secret are stored in the operator's private
  credential manager.

The Regular Web Application uses these exact generated-origin values, with no
wildcards:

```text
Allowed Callback URLs:
https://abda-nl-stg-web.blueforest-da494f7c.eastus2.azurecontainerapps.io/auth/callback

Allowed Logout URLs:
https://abda-nl-stg-web.blueforest-da494f7c.eastus2.azurecontainerapps.io/

Allowed Web Origins:
https://abda-nl-stg-web.blueforest-da494f7c.eastus2.azurecontainerapps.io
```

## Source and container ownership

- `idaks/ABDA-NL` remains the stable paper-facing repository.
- `Liu-Hy/ABDA-NL` is the standalone public service repository.
- Personal `main` matches the reviewed paper-demo commit, while hosted work is
  isolated on `development`.
- GitHub branch protection, secret scanning, push protection, vulnerability
  alerts, and automated security updates are enabled.
- The `abda-nl` GHCR package is public. Anonymous registry requests returned
  HTTP 200 for the initial image and the exact deployment candidate recorded in
  [the staging deployment record](staging-deployment-record-20260828.md).
- GitHub account two-factor authentication is enabled and recovery codes are
  stored privately.

## Remaining deployment-dependent gates

The next stage must publish the exact candidate commit and digest, run the
database migration job, and deploy the Container App at the recorded generated
origin. After generated-origin acceptance passes, the operator can create
`demo.abda-nl.org`, bind its managed certificate, add its exact Auth0 URLs, and
complete live identity, model, persistence, security, observability, and
rollback checks.
