# Decision 0001: Launch and service boundaries

Date: 2026-08-16

## Status

Accepted.

## Decision

ABDA-NL has one Python server entrypoint and three intentionally thin launch
paths:

1. The installed `abda-nl` command opens a browser for an ordinary local run.
2. The Delta user-wide `demo` launcher calls the same entrypoint with a fixed
   loopback host and port, no browser opening, and managed process lifetime.
3. The public container calls the same application with an explicit managed
   deployment configuration and no browser opening.

Delta remains private and loopback-only. Public service traffic belongs on a
managed hosting platform, not a Delta login node. Production user state will
use a database and will never be written into the tracked examples directory.

## Rationale

One server entrypoint prevents configuration and startup behavior from
drifting across local development, Delta demonstrations, and public hosting.
Thin environment-specific wrappers retain the behavior each environment
actually needs.

## Consequences

- `.demo.json` must retain `{host}` and `{port}` and a foreground command.
- A local run may choose an available port and open the default browser.
- A managed run must use an explicit port and never attempt to open a browser.
- Non-loopback binding requires an explicit managed-deployment flag.
- Delta lifecycle commands and the laptop SSH tunnel remain unchanged.
