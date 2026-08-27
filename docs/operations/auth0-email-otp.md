# Auth0 verified-email OTP runbook

ABDA-NL delegates public account authentication to a hosted OIDC provider. The
recommended initial provider is Auth0 Universal Login with email OTP. This gives
research users a normal long-lived account without making ABDA-NL store
passwords, operate SMS delivery, or accept unverified email claims.

The application requires the literal Boolean claim `email_verified: true`. It
pins the OIDC issuer and stable subject. It never merges identities merely
because two providers report the same email address.

## 1. Create the tenant and application

Create the tenant under a lab-controlled account and invite a second lab member
as an administrator. Do not make a personal account the only recovery path for
the public service. In Auth0, create a Regular Web Application. Record its
domain, client ID, and client secret. Use Authorization Code flow and exact
URLs, without wildcards.

For the first Azure deployment, configure:

- Allowed Callback URLs: `GENERATED_ORIGIN/auth/callback`
- Allowed Logout URLs: `GENERATED_ORIGIN/`
- Allowed Web Origins: `GENERATED_ORIGIN`

When the operator-owned hostname is ready, add these values before changing the
application's canonical origin:

- Allowed Callback URLs: `https://demo.abda-nl.org/auth/callback`
- Allowed Logout URLs: `https://demo.abda-nl.org/`
- Allowed Web Origins: `https://demo.abda-nl.org`

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
6. Keep signup disabled while the generated Azure origin is undergoing private
   infrastructure checks.
7. Enable signup temporarily for live email acceptance and the invited pilot.
8. Open signup for the first-100-user trial only after the release checklist
   passes.

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
per minute, and does not support a customized sender or template. Before the
invited pilot, configure an external provider in Branding, Email Provider.
Prefer a supported integration such as Microsoft 365 Exchange Online, Azure
Communication Services, Amazon SES, or another lab-approved service. Configure
SPF, DKIM, and DMARC for the sending domain.

Customize the OTP email with:

- the ABDA-NL and iDAKS names
- a clear one-time-code purpose and expiration statement
- `demo.abda-nl.org` after DNS cutover
- a support contact that the lab actually monitors
- no request for an API key, password, or reply

Send test messages to UIUC, Gmail, and another external provider. Confirm that
delivery latency is acceptable and that failures appear in Auth0 logs.

## 4. Application settings

Set these deployment values from the application and tenant settings:

```text
ABDA_DEPLOY_OIDC_METADATA_URL=https://TENANT/.well-known/openid-configuration
ABDA_DEPLOY_OIDC_ISSUER=https://TENANT/
ABDA_DEPLOY_OIDC_CLIENT_ID=APPLICATION_CLIENT_ID
ABDA_DEPLOY_OIDC_CLIENT_SECRET=APPLICATION_CLIENT_SECRET
```

The client secret belongs in the lab secret manager and the Azure deployment's
secure parameter. Never put it in `.env.example`, a URL, a screenshot, or an
issue.

## 5. Acceptance gate

Complete all of these checks on the deployed origin:

1. A new address receives an OTP, signs in, and `/api/auth/session` reports one
   verified account.
2. A wrong or expired OTP does not create an ABDA-NL account.
3. A second email creates a distinct account with no access to the first
   account's private project.
4. Signing out clears the ABDA-NL session cookie. On a shared device, also sign
   out of Auth0 or close the private browser session before another user tests.
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

- [Auth0 passwordless authentication on database connections](https://auth0.com/docs/authenticate/database-connections/passwordless-authentication-for-db-connect)
- [Auth0 Passwordless Email](https://auth0.com/docs/authenticate/passwordless/authentication-methods/email-otp)
- [Auth0 verified email guidance](https://auth0.com/docs/manage-users/user-accounts/user-profiles/verified-email-usage)
- [Auth0 application settings](https://auth0.com/docs/get-started/applications/application-settings)
- [Auth0 production email providers](https://auth0.com/docs/customize/email/smtp-email-providers)
