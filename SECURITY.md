# Security policy

ABDA-NL is a research service, not a safety-critical system. The current public
release line receives security fixes. Older commits and private development
deployments may not.

## Report a vulnerability privately

Use the repository's
[GitHub Security Advisory form](https://github.com/Liu-Hy/ABDA-NL/security/advisories/new)
to report a suspected vulnerability. Do not open a public issue for an
unpatched vulnerability, API key, share link, MCP token, identity token,
private project, or personal data.

Include the affected commit or public origin, a minimal reproduction, likely
impact, and any relevant request identifier. Remove secrets and personal data
from screenshots and logs. The project team will acknowledge the report,
investigate it, coordinate a fix, and agree on disclosure timing when needed.

For ordinary bugs that do not expose data, credentials, authorization, or
budget controls, use the public issue tracker.

## Operational response

The operator may pause public mutations, funded model access, sharing, or MCP
access while investigating an incident. Rotating the session secret signs out
browser users. Rotating the MCP token pepper invalidates every MCP credential.
Provider and BYOK keys must be revoked at their issuing provider if exposure is
suspected.
