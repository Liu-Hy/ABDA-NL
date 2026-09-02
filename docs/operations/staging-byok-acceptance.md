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
- The script reads Azure control-plane state, protected aggregate accounting
  metrics, and count-only Log Analytics results. It does not print raw logs,
  private account content, or secret values.
- It does not deploy, restart, update a setting, change a secret, activate a
  trial, or enable public OpenRouter failover.

## Evidence collected

The gate snapshots protected aggregate metrics immediately before the browser
call. It then proves that the model-event count increased by a bounded amount
while funded-trial spending, reservations, allocations, and the independent
owner-funded OpenRouter emergency ledger remained unchanged. Count-only logs
prove that the accepted `byok:openrouter:gemini-3.7-flash` route ran and that no
provider-key, authorization, bearer-token, or email pattern entered managed
logs. Unit, PostgreSQL, browser, and schema tests separately prove the
request-scoped key and no-storage implementation boundary.

The browser operator confirms that a reload removes the in-memory key. The
operator then reapplies the key without making another provider call, signs
out, signs back in, and confirms that the field is empty again.

Revision 4 does not depend on a long-lived interactive Container Apps exec
session. It writes only timestamps, aggregate counters, immutable image
identity, and a browser-phase marker to a mode-600 resume file. Each browser
confirmation advances that marker atomically. If a later Azure or log query
fails, rerunning the same pinned gate resumes the read-only checks without
repeating the paid provider call. The state is removed after success.

The current Gate is pinned to managed-boundary candidate revision
`abda-nl-stg-web--secure-b873112` and exact image digest
`sha256:567ec34602e1b5ab1e1a9b01864f2a67219910dc3080300bc108eb33d569856c`.

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
