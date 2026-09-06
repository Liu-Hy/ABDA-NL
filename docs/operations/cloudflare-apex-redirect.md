# Friendly apex-domain redirect

State: deployed by the operator and verified externally on September 5, 2026 CDT

The application origin remains `https://demo.abda-nl.org`. The shorter
addresses `https://abda-nl.org` and `https://www.abda-nl.org` now redirect
to that origin so a visitor does not need to remember the subdomain. This is a
redirect only. It does not change Azure, Auth0, the application certificate, or
the `demo` DNS record.

## Current evidence

After correcting the condition in Cloudflare's expression editor, the operator
confirmed that the rule was saved. The first immediate DNS query returned no
apex A record. Subsequent queries to both authoritative nameservers, the
public resolver, and the local resolver returned the Cloudflare proxy
addresses. No local DNS or host configuration was changed.

The unchanged hostname gate then completed through ordinary DNS resolution
with exit code 0 and the following content-free receipt:

```text
script_revision: 1
public_origin: https://demo.abda-nl.org
apex_https_redirect: passed
apex_http_redirect: passed
www_https_redirect: passed
path_and_query_preserved: passed
demo_origin_readiness: passed
auth0_custom_domain: passed
resend_spf_dkim_dmarc_mx: passed
credentials_used: false
external_state_changed: false
result: PUBLIC_HOSTNAME_AND_EMAIL_DNS_BOUNDARY_VERIFIED
```

This validates the public hostname and existing email DNS boundary. It does
not establish Resend plan capacity or send another test email. No Azure
setting, application revision, trial limit, or provider route was changed by
the verification. Do not repeat the dashboard setup or request another manual
browser test for this completed gate.

## Earlier checks before the dashboard save

On 2026-09-02, authoritative and recursive DNS returned no address for the apex
or `www`, while `https://demo.abda-nl.org/health/ready` returned HTTP 200.
The missing apex response is therefore a DNS and redirect configuration gap,
not an application outage.

A read-only recheck on 2026-09-04 produced the same missing-apex result. The
existing `demo` and `login` CNAME records still resolved to their Azure and
Auth0 targets. The Resend DKIM, SPF, feedback MX, and authentication-subdomain
DMARC records also remained present. Only the two redirect aliases and rule
below remain to be configured.

On 2026-09-05, the read-only hostname gate again stopped because the apex had
no A record. Direct queries to both `alexis.ns.cloudflare.com` and
`dana.ns.cloudflare.com` returned authoritative `NOERROR` responses with zero
A answers. The demo readiness endpoint still returned HTTP 200 with
`{"status":"ready"}`, and Auth0 discovery returned the expected
`https://login.abda-nl.org/` issuer. This does not establish a full hostname
gate pass. The dashboard changes below remain pending.

After the GPL pilot audit on September 5, Codex repeated the read-only hostname
check and authoritative queries. The apex and `www` A records were still
absent. The new image passed public browser and bounded capacity checks, as
recorded in the [GPL live checkpoint](gpl-live-checkpoint-20260905.md).
After saving the records and rule below, tell Codex; it can verify the whole
public boundary without a Cloud Shell session or another manual browser test.

## Cloudflare dashboard steps

These are the saved configuration and recovery instructions, not a request to
repeat the completed setup.

First create the two alias-only DNS records under **DNS**, then **Records**:

| Type | Name | IPv4 address | Proxy status | TTL |
| --- | --- | --- | --- | --- |
| A | `@` | `192.0.2.1` | Proxied | Auto |
| A | `www` | `192.0.2.1` | Proxied | Auto |

`192.0.2.1` is Cloudflare's documented address for a redirect-only alias. It
does not route a request to an application origin. The orange-cloud proxy is
required so Cloudflare can receive the request and apply the redirect rule.

Then open **Rules**, **Overview**, **Create rule**, **Redirect Rule** and use:

- Rule name: `ABDA-NL apex and www to demo`
- Match type: Custom filter expression
- Click **Edit expression** next to **Expression Preview**. Replace the full
  editor content with the following condition. Do not paste this condition
  into a **URI Full**, **wildcard**, **Value** field:

```text
(http.host eq "abda-nl.org" or http.host eq "www.abda-nl.org")
```

The resulting condition must not wrap this text inside
`http.request.full_uri wildcard r#"..."#`. That form treats the condition as
literal URL-pattern text rather than evaluating the two host comparisons.

- Redirect type: Dynamic
- Target expression:

```text
concat("https://demo.abda-nl.org", http.request.uri.path)
```

- Status code: 301
- Preserve query string: Enabled

Deploy the rule. Do not use an all-subdomains wildcard. It could also capture
`login.abda-nl.org`, `auth.abda-nl.org`, or the real `demo` origin.

## Acceptance

After DNS resolves, run the repository's read-only boundary Gate from Delta or
another ordinary network:

```bash
.venv/bin/python deploy/cloudflare/gate16_public_hostname_boundary.py
```

The Gate uses only DNS queries and fixed HTTP GET requests. It requires no
credential and changes no external state. It verifies both redirects, exact
path and query preservation, the direct demo readiness endpoint, the Auth0
custom-domain issuer, and the Resend SPF, DKIM, DMARC, and MX records. Success
ends with:

```text
result: PUBLIC_HOSTNAME_AND_EMAIL_DNS_BOUNDARY_VERIFIED
```

For a manual spot check, use:

```bash
curl --head https://abda-nl.org/
curl --head 'https://www.abda-nl.org/privacy.html?source=redirect-test'
curl --fail --location https://abda-nl.org/health/ready
```

The first two responses should be 301 with a `Location` under
`https://demo.abda-nl.org`. The path and test query must be preserved. The last
command must finish with the existing content-free ready response. Also verify
that `login.abda-nl.org` still opens Auth0 and that the two email-delivery tests
remain unaffected.

## References

- [Cloudflare redirect-only domain setup](https://developers.cloudflare.com/fundamentals/manage-domains/redirect-domain/)
- [Cloudflare Single Redirect dashboard steps](https://developers.cloudflare.com/rules/url-forwarding/single-redirects/create-dashboard/)
- [Cloudflare redirect settings](https://developers.cloudflare.com/rules/url-forwarding/single-redirects/settings/)
