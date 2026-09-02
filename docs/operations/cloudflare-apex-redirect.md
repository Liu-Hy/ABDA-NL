# Friendly apex-domain redirect

State: prepared, Cloudflare dashboard change pending

The application origin remains `https://demo.abda-nl.org`. The shorter
addresses `https://abda-nl.org` and `https://www.abda-nl.org` should redirect
to that origin so a visitor does not need to remember the subdomain. This is a
redirect only. It does not change Azure, Auth0, the application certificate, or
the `demo` DNS record.

## Current evidence

On 2026-08-30, authoritative and recursive DNS returned no address for the apex
or `www`, while `https://demo.abda-nl.org/health/ready` returned HTTP 200.
The missing apex response is therefore a DNS and redirect configuration gap,
not an application outage.

## Cloudflare dashboard steps

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
- Expression:

```text
(http.host eq "abda-nl.org" or http.host eq "www.abda-nl.org")
```

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
