# Staging BYOK browser acceptance

Run this acceptance after the read and scoped-write MCP checks, and before the
disposable-account privacy deletion check. It validates one real OpenRouter
request at `https://demo.abda-nl.org` without exposing the provider key to the
operator script.

## Safety boundary

- Enter the OpenRouter key only in the password field at
  `https://demo.abda-nl.org`.
- Never paste the key into Azure Cloud Shell, chat, a document, or a command.
- The browser makes exactly one short paid request on the key owner's account.
- The script reads Azure control-plane state, application accounting rows, and
  count-only Log Analytics results. It does not print raw logs or private
  account content.
- It does not deploy, restart, update a setting, change a secret, activate a
  trial, or enable public OpenRouter failover.

## Evidence collected

The embedded read-only verifier proves that all physical calls for the one
browser request use `byok:openrouter:gemini-3.7-flash`, have a successful event
with metered usage, and leave both the user's trial ledger and the independent
owner-funded OpenRouter emergency ledger unchanged. It hashes the user's
private project, share, and MCP metadata before and after the call without
printing that material.

The browser operator confirms that a reload removes the in-memory key. The
operator then reapplies the key without making another provider call, signs
out, signs back in, and confirms that the field is empty again. Finally, the
gate waits for a count-only Log Analytics query that sees the accepted route
and zero provider-key, authorization, bearer-token, or email patterns.

Provider accounts can independently reject an otherwise correct BYOK request
because of account quota, billing, or model access. This gate uses the current
working OpenRouter key because that is the practical live route. Direct
Anthropic, OpenAI, and Google adapters remain covered by provider-client,
routing, API secrecy, and browser tests. Their account-specific success is not
claimed without a working disposable key.

## Failure handling

If the gate stops before a successful browser call, clear the browser field and
sign out. If the successful call already happened, do not repeat it until the
visible failure section has been reviewed. Send only the section name and shell
exit code, never the provider key, account email, raw provider response, or raw
application logs.
