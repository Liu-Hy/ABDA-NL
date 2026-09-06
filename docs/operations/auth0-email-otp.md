# Auth0 verified-email OTP runbook

ABDA-NL delegates public account authentication to a hosted OIDC provider. The
recommended initial provider is Auth0 Universal Login with email OTP. This gives
research users a normal long-lived account without making ABDA-NL store
passwords, operate SMS delivery, or accept unverified email claims.

The application requires the literal Boolean claim `email_verified: true`. It
pins the OIDC issuer and stable subject. It never merges identities merely
because two providers report the same email address.

## 1. Create the tenant and application

Follow [the operator bootstrap runbook](operator-service-bootstrap.md) first.
Create the tenant under an operator-controlled, long-lived account with
multifactor authentication and stored recovery codes. A second named
administrator is required before public registration opens when the selected
plan permits it, but it does not block private staging. Do not share one
person's Dashboard login.

Auth0's public plan table checked on 2026-09-02 includes Passwordless and one
custom domain in the Free plan. Its custom-domain documentation says the Free
tenant must keep a valid credit card on file for ownership and fraud checks,
but that card is not charged for this verification. The current
`login.abda-nl.org` design therefore does not depend on the temporary feature
trial shown after tenant creation. Recheck the plan only if Auth0 announces a
pricing change or the tenant reports a feature-expiration warning.

Create a Regular Web Application named `ABDA-NL Public Service`. Record its
domain, client ID, and client secret in the private operator record. Use
Authorization Code flow and exact URLs, without wildcards.

For the first Azure deployment, configure:

- Allowed Callback URLs: `GENERATED_ORIGIN/auth/callback`
- Allowed Logout URLs: `GENERATED_ORIGIN/`
- Allowed Web Origins: `GENERATED_ORIGIN`

When the operator-owned hostname is ready, substitute the acquired root domain
for `DOMAIN` and add these values before changing the application's canonical
origin:

- Allowed Callback URLs: `https://demo.DOMAIN/auth/callback`
- Allowed Logout URLs: `https://demo.DOMAIN/`
- Allowed Web Origins: `https://demo.DOMAIN`

Keep both exact callback sets during the DNS transition. Remove the generated
origin only after the custom origin has passed login and logout tests.

ABDA-NL requests the scopes `openid profile email`. Configure the deployment
with the tenant's discovery URL, issuer, client ID, and client secret. Do not
copy an Auth0 management token into the application.

## 2. Configure email OTP

Use Auth0's established Passwordless Email connection for the initial service.
Passwordless OTP on a database connection is currently an Early Access feature
and must not be a production dependency unless Auth0 explicitly enables and
supports it for this tenant.

1. Open Authentication, Passwordless, and enable Email.
2. Select the one-time code flow, not a magic link.
3. Set a short expiry and retain Auth0's limit on failed code attempts.
4. Enable the Email connection only for the ABDA-NL application.
5. Disable every database, social, and enterprise connection for this
   application during the initial launch.
6. Keep signup enabled so invited first-time addresses can create Auth0
   identities during staging. Keep `ABDA_DEPLOY_TRIAL_ENABLED=false`, and do
   not advertise the origin, until the release checklist passes.
7. Open the service to the first-100-user trial only after identity, accounting,
   persistence, and security acceptance passes.

The first successful OTP creates the Auth0 user on the Email connection. The
application still requires the literal Boolean claim `email_verified: true` and
rejects a token that does not prove that condition. Do not build a custom
password or OTP endpoint in ABDA-NL.

If Auth0 later makes passwordless database connections generally available for
the selected tenant and plan, evaluate that flow in a separate Auth0
application first. Do not migrate public identities merely to adopt a newer
login feature.

Start with only the Passwordless Email connection. Social and enterprise
connections can report the same email under different stable subjects. ABDA-NL
intentionally rejects that situation until an explicit reauthentication-based
linking flow exists. It does not silently join accounts by email.

Verified email means that the user controlled the mailbox during verification.
It is not proof of current institutional affiliation and must not be used as an
authorization role.

## 3. Configure production email delivery

Auth0's built-in email sender is for private testing, is limited to ten emails
per minute, and does not support a customized sender or template. Use Auth0's
supported Resend integration before the invited pilot. Resend sends from the
dedicated `auth.DOMAIN` subdomain. Cloudflare Email Routing independently
receives `support@DOMAIN` and `privacy@DOMAIN` at the root domain.

In Resend:

1. Add and verify `auth.DOMAIN` using its generated Cloudflare DNS records.
2. Keep receiving, open tracking, and click tracking disabled.
3. Create a sending-only API key named `ABDA-NL Auth0` and restrict it to the
   verified sending domain when available.
4. Store the key in the password manager. Do not put it in the ABDA-NL `.env`
   file because only Auth0 uses it.

Resend documents that open and click tracking are disabled by default and
become active only after a tracking subdomain is configured and verified. The
current `auth.abda-nl.org` domain has no Tracking DNS record or tracking
subdomain, so neither mechanism is active even if the domain-creation controls
were unavailable after setup.

In Auth0, open Branding, Email Provider, enable the external provider, and
select Resend. Use the same From address in the provider and the Passwordless
Email connection:

```text
no-reply@auth.DOMAIN
```

Paste the Resend API key, save, and use **Send Test Email**. Confirm the message
in the destination inbox, Auth0 logs, and Resend delivery logs.

Customize the OTP email with:

- the ABDA-NL and iDAKS names
- a clear one-time-code purpose and expiration statement
- `demo.DOMAIN` after DNS cutover
- `support@DOMAIN`, which the operator actively monitors
- no request for an API key, password, or reply

Send test messages to UIUC, Gmail, and another external provider. Confirm that
delivery latency is acceptable and that failures appear in Auth0 logs.

### Capacity before general registration

Decision recorded on 2026-09-06: the operator confirmed returning to Resend
Free and accepted responsibility for monitoring sent and delivered email counts
during the conference, upgrading to Pro when needed, and accepting a temporary
quota-related login interruption. This supersedes the earlier recommendation
to require Pro or retain the ten-user pilot. A paid sender plan is not a
prerequisite for the 100-account trial promotion. Do not request another plan
confirmation or introduce a new quota-monitoring setup gate.

The [official plan table](https://resend.com/docs/knowledge-base/what-is-resend-pricing)
checked on 2026-09-06 lists Free at 100 messages per day and 3,000 per month.
Pro includes 50,000 messages for $20 per month with no daily limit. Pay-as-you-go
is available only on paid plans and does not extend Free's daily allowance.
Trial accounts and email deliveries are separate quantities; returning users
and repeated OTP requests can consume additional messages.

The [Metrics dashboard](https://resend.com/changelog/enhanced-metrics-dashboard)
supports current sending statistics and date filtering. For quota planning,
use sent counts and the provider's quota display rather than delivered counts
alone. The [API limit documentation](https://resend.com/docs/api-reference/rate-limit)
defines quota-exceeded responses and daily and monthly usage headers. It does
not promise a precise upgrade activation delay. The project does not currently
claim an automatic email-volume alert or subscription-upgrade mechanism.
Keep the verified sender and Auth0 provider configuration; do not replace them
with Auth0's built-in test sender. This operational choice does not weaken
verified-email checks, model budgets, or credential protections.

Auth0 Free itself has ample identity capacity for this release. Its current
plan includes Passwordless, one custom domain, and up to 25,000 monthly active
users. Its Free Authentication API policy separately limits passwordless-code
starts to 50 per hour from one source IP. This is not a global 50-user limit,
but many attendees behind one conference-network address can share it. Keep
the presentation account signed in before the talk. For a workshop expecting
more than 50 first-time registrations from one shared network within an hour,
stagger onboarding or review a higher Auth0 tier before the event.

## 4. Application settings

Set these deployment values from the application and tenant settings:

```text
ABDA_DEPLOY_OIDC_METADATA_URL=https://TENANT/.well-known/openid-configuration
ABDA_DEPLOY_OIDC_ISSUER=https://TENANT/
ABDA_DEPLOY_OIDC_CLIENT_ID=APPLICATION_CLIENT_ID
ABDA_DEPLOY_OIDC_CLIENT_SECRET=APPLICATION_CLIENT_SECRET
```

For the current operator-owned tenant, the verified public discovery values
are:

```text
ABDA_DEPLOY_OIDC_METADATA_URL=https://login.abda-nl.org/.well-known/openid-configuration
ABDA_DEPLOY_OIDC_ISSUER=https://login.abda-nl.org/
```

The client secret belongs in the private operator password manager and the
Azure deployment's secure parameter. Never put it in `.env.example`, a URL, a
screenshot, or an issue.

## 5. Acceptance gate

Complete all of these checks on the deployed origin:

1. A new address receives an OTP, signs in, and `/api/auth/session` reports one
   verified account.
2. A wrong or expired OTP does not create an ABDA-NL account.
3. A second email creates a distinct account with no access to the first
   account's private project.
4. Signing out clears the ABDA-NL session cookie, ends the Auth0 browser
   session through its discovered OIDC logout endpoint, and returns to the exact
   allowed application origin.
5. The callback rejects a token with a different issuer, missing subject,
   malformed email, or `email_verified` other than the Boolean `true`.
6. The login callback query is absent from Uvicorn access logs.
7. Trial activation succeeds once per verified account and cannot be reset by
   signing out or changing email letter case.
8. Replaying two concurrent callbacks for one valid first login resolves to one
   ABDA-NL account, while two distinct identities with one email remain blocked.

Items 5 through 8 have automated regression tests, including a real PostgreSQL
race. Items 1 through 4 also need live Auth0 acceptance because mocked tokens
cannot prove email delivery or tenant configuration.

## Primary references

- [Auth0 pricing and plan comparison](https://auth0.com/pricing)
- [Auth0 custom domains](https://auth0.com/docs/customize/custom-domains)
- [Auth0 passwordless authentication on database connections](https://auth0.com/docs/authenticate/database-connections/passwordless-authentication-for-db-connect)
- [Auth0 Passwordless Email](https://auth0.com/docs/authenticate/passwordless/authentication-methods/email-otp)
- [Auth0 Free rate limits](https://auth0.com/docs/troubleshoot/customer-support/operational-policies/rate-limit-policy/rate-limit-configurations/free-public)
- [Auth0 verified email guidance](https://auth0.com/docs/manage-users/user-accounts/user-profiles/verified-email-usage)
- [Auth0 application settings](https://auth0.com/docs/get-started/applications/application-settings)
- [Auth0 OIDC logout](https://auth0.com/docs/authenticate/login/logout/log-users-out-of-auth0)
- [Auth0 production email providers](https://auth0.com/docs/customize/email/smtp-email-providers)
- [Auth0 Resend provider](https://auth0.com/docs/customize/email/smtp-email-providers/resend)
- [Resend Cloudflare verification](https://resend.com/docs/knowledge-base/cloudflare)
- [Resend open and click tracking](https://resend.com/docs/dashboard/domains/tracking)
- [Resend pricing](https://resend.com/pricing/)
- [Resend account quotas and limits](https://resend.com/docs/knowledge-base/account-quotas-and-limits)
