# Operator service bootstrap

This runbook orders the manual account and domain work needed before the first
paid Azure deployment. It is written for an operator who controls the service
without depending on iSchool IT, iDAKS organization administration, or
CloudBank staff.

Complete one checkpoint at a time. Do not paste passwords, API keys, client
secrets, recovery codes, billing information, or Azure access tokens into an
issue, chat, screenshot, or repository file.

## Fixed service names

After registering a root domain, substitute it for `DOMAIN` below. Keep these
names stable unless a DNS conflict requires a change:

| Purpose | Name |
| --- | --- |
| Public application | `https://demo.DOMAIN` |
| Transactional sending domain | `auth.DOMAIN` |
| Authentication sender address | `no-reply@auth.DOMAIN` |
| User support | `support@DOMAIN` |
| Privacy and deletion requests | `privacy@DOMAIN` |
| Auth0 custom domain | `login.DOMAIN` |
| Auth0 application | `ABDA-NL Public Service` |

Using a dedicated `auth` subdomain isolates the reputation and DNS records of
transactional login mail. Cloudflare Email Routing remains responsible for
incoming mail at the root domain. Resend receiving must remain disabled for the
`auth` subdomain.

The initial ABDA-NL operator setup completed these checkpoints on 2026-08-28.
See the dated
[external prerequisites checkpoint](external-prerequisites-20260828.md) for
the verified non-secret state. The instructions below remain the reproducible
procedure for recovery or a future operator.

## Checkpoint 0: Secure the operator accounts

Use operator-controlled accounts that do not depend on continued access to an
institutional position. For GitHub, Cloudflare, Resend, and Auth0:

1. Use a long-lived account email address.
2. Enable a passkey or authenticator-based multifactor authentication.
3. Store recovery codes in a password manager, separately from the account
   password.
4. Do not share one person's login. Invite a second named administrator when
   the service is ready for public registration and the selected plan permits
   it.
5. Record the account owner and recovery procedure in the private operator
   record, not in this public repository.

A second administrator is a public-launch resilience gate. It is not necessary
to create the initial private staging resources.

## Checkpoint 1: Register the root domain in Cloudflare

1. Open Cloudflare Dashboard and select **Domain Registration**, then
   **Register Domains**.
2. Search for `abda-nl.org`. If it is unavailable or unusually expensive, try
   `abdanl.org`, `abda-nl.net`, and `abdanl.net`, in that order.
3. Prefer a one-year registration with automatic renewal enabled.
4. Review both the initial and renewal price before completing the purchase.
5. Enter accurate registrant contact information using ASCII characters.
6. Complete any account-email or registrant-email verification that Cloudflare
   presents. An active registration with no verification warning is acceptable
   when Cloudflare uses the already verified account address.
7. Confirm that the registration **Overview** reports **Active**, that
   Cloudflare is authoritative for its DNS zone, and that DNSSEC reports
   success.

Stop here and record only the acquired domain and verification status. Do not
send billing information or registrant contact details.

## Checkpoint 2: Create monitored incoming addresses

Use Cloudflare Email Routing for incoming mail. It forwards mail to the
operator's existing monitored inbox without requiring a mailbox subscription.

1. Open **Compute**, **Email Service**, **Email Routing**.
2. Select **Onboard Domain**, choose `DOMAIN`, review the proposed MX, SPF, and
   DKIM records, and complete onboarding.
3. Open **Destination Addresses**, add the primary operator inbox, and follow
   the verification link sent to that inbox.
4. Create an exact routing rule from `support@DOMAIN` to the verified inbox.
5. Create another exact rule from `privacy@DOMAIN` to the same inbox.
6. Leave catch-all routing disabled. It attracts unnecessary spam and makes
   typos appear valid.
7. From a different mailbox, send a harmless test message to each address.
   Confirm delivery and reply from the operator inbox without exposing private
   material.

The initial operator is Haoyang Liu. `support@DOMAIN` handles ordinary service
questions. `privacy@DOMAIN` handles access, correction, and deletion requests.
The response target for a deletion request is 30 days. These aliases can later
forward to more than one monitored operator without changing the public
application.

## Checkpoint 3: Configure Resend transactional delivery

Use Resend only to send Auth0 authentication messages. Do not use it as the
incoming support mailbox.

1. Create or sign in to the operator-controlled Resend account and enable its
   strongest available account authentication.
2. Open **Domains**, select **Add Domain**, and enter `auth.DOMAIN`.
3. Keep receiving disabled. Select the United States sending region unless a
   documented service requirement calls for another region.
4. Use Resend's **Sign in to Cloudflare** flow to add the generated SPF, DKIM,
   and return-path records. Review that every new record is beneath
   `auth.DOMAIN`, not the root domain or `demo.DOMAIN`.
5. Return to Resend and wait for the domain status to become **Verified**.
6. Keep open and click tracking disabled for authentication mail.
7. Open **API Keys** and create `ABDA-NL Auth0`. Select sending-only access and
   restrict it to `auth.DOMAIN` when the dashboard offers that scope.
8. Copy the API key once into the password manager. Never send it back through
   chat or place it in the ABDA-NL `.env` file. Auth0, not ABDA-NL, owns this
   credential.

Stop here with three non-secret facts: the verified sending domain, whether
tracking is disabled, and whether the domain-restricted sending key is stored.

## Checkpoint 4: Create Auth0 identity resources

1. Create or sign in to the operator-controlled Auth0 account. Enable
   multifactor authentication for Dashboard access.
2. Create one tenant in the United States region. Use a recognizable name such
   as `abda-nl-public` if it is available. The tenant name is permanent.
3. In **Settings**, **General**, assign the tenant the **Production**
   environment tag because this tenant will eventually serve public users.
4. Open **Applications**, **Applications**, select **Create Application**, name
   it `ABDA-NL Public Service`, and select **Regular Web Applications**.
5. Leave callback, logout, and web-origin values empty until the Azure
   infrastructure deployment reports the exact generated origin. Never enter a
   wildcard or localhost production URL.
6. Open **Authentication**, **Passwordless**, enable **Email**, select one-time
   code rather than magic link, use a six-digit code with a five-minute
   expiry, and retain Auth0's failed-attempt limit.
7. Set the Passwordless Email **From** value to `no-reply@auth.DOMAIN`. Enable
   this connection only for the ABDA-NL application. Disable database, social,
   and enterprise connections for that application.
8. Open **Branding**, **Email Provider**, enable **Use my own email provider**,
   select **Resend**, enter the same `no-reply@auth.DOMAIN` From address, and
   paste the Resend key from the password manager. Save it.
9. Select **Send Test Email**. Confirm arrival and confirm the delivery event in
   both Auth0 and Resend logs.
10. Record the tenant domain and application client ID in the private operator
    record. Store the application client secret in the password manager. The
    client secret itself remains private.
11. Keep signup enabled on the Passwordless Email connection so invited new
    users can create identities. Trial credit remains disabled independently
    until the application release gates pass.
12. Keep Suspicious IP Throttling and Brute-force Protection enabled with
    default detection thresholds, empty IP allowlists, IP-scoped blocking, and
    global Account Lockout disabled.
13. Disable Dynamic Client Registration and automatic connection enablement for
    new applications. Enable generic public-signup error responses.

The Auth0 application remains incomplete but safe at this checkpoint. The
Azure infrastructure step supplies the generated origin. Add its exact
callback, logout URL, and web origin only after recording that output.

## Checkpoint 5: Confirm funded-provider boundaries

The private root `.env` may supply the existing CloudBank and OpenRouter
credentials for staging. Confirm only that the required names are present and
that the file mode is `600`. Never copy their values into this repository or a
chat transcript.

The operator has accepted using the current OpenRouter key for staging and the
initial public outage fallback.
`ABDA_DEPLOY_OPENROUTER_FAILOVER_ENABLED` remains `false` until the controlled
outage and final promotion Gates pass. The application ledger remains the hard
$500 service boundary even when the current provider key has a different
account-level limit.

After the deadline, create a dedicated ABDA-NL inference key with a $500
lifetime spending limit and no automatic reset. Store it in the password
manager and replace only the Azure deployment secret through a separately
reviewed secret rotation. A dedicated key avoids letting unrelated personal use
consume the service reserve or letting the service affect another project. Key
rotation is recommended defense in depth, but it is not a blocker for the
operator-approved initial release.

The application ledger independently caps OpenRouter fallback at $500. Raising
that application boundary above $500 requires the documented acknowledgement,
and the application refuses a limit above $1,000.
Per-request routing also requires Zero Data Retention and denies provider data
collection, so an account-wide privacy change is not necessary for staging.

## Checkpoint 6: Hand off to Azure staging

After checkpoints 1 through 5 pass, follow the public Azure deployment
runbook. The first Azure step creates the resource group, private network,
Container Apps environment, Log Analytics workspace, and private PostgreSQL
server. It incurs Azure charges, so review `az deployment group what-if`
before every create operation.

The infrastructure deployment outputs the generated origin. Add exactly:

```text
Allowed Callback URLs: GENERATED_ORIGIN/auth/callback
Allowed Logout URLs: GENERATED_ORIGIN/
Allowed Web Origins: GENERATED_ORIGIN
```

Only then load the Auth0 OIDC values into the private deployment shell, run the
migration job, and deploy the web application. Trials and OpenRouter failover
remain disabled for this first staging revision.

## Primary references

- [Cloudflare domain registration](https://developers.cloudflare.com/registrar/get-started/register-domain/)
- [Cloudflare Email Routing](https://developers.cloudflare.com/email-service/get-started/route-emails/)
- [Resend domain verification with Cloudflare](https://resend.com/docs/knowledge-base/cloudflare)
- [Resend verified domains](https://resend.com/docs/dashboard/domains/introduction)
- [Auth0 Resend provider](https://auth0.com/docs/customize/email/smtp-email-providers/resend)
- [Auth0 Passwordless Email](https://auth0.com/docs/authenticate/passwordless/authentication-methods/email-otp)
- [Auth0 Regular Web Applications](https://auth0.com/docs/get-started/auth0-overview/create-applications/regular-web-apps)
- [Auth0 application settings](https://auth0.com/docs/get-started/applications/application-settings)
- [OpenRouter key limits](https://openrouter.ai/docs/api/api-reference/api-keys/create-keys)
- [OpenRouter Zero Data Retention](https://openrouter.ai/docs/guides/features/zdr)
