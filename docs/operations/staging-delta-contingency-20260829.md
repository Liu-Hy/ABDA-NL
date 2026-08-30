# Delta contingency checkpoint, 2026-08-29

State: server-side Delta launcher path verified, laptop tunnel retest pending

This checkpoint records a read-only verification of the private Delta fallback.
No server was restarted or reconfigured.

## Tracked launcher contract

The tracked `.demo.json` contains:

```json
{
  "name": "ABDA-NL",
  "command": "make run PORT={port} HOST={host}",
  "ready_path": "/health/ready",
  "startup_timeout": 30
}
```

The command retains both launcher placeholders and keeps the server in the
foreground for lifecycle management.

## Live Delta evidence

From `dt-login03.delta.ncsa.illinois.edu`:

- `demo doctor` identified `/u/haoyang/ABDA-NL`, pinned node `dt-login03`,
  loopback port 8765, and the expected `ssh delta-demo` forwarding model.
- `demo status` reported the repository as running on the pinned node.
- `GET http://127.0.0.1:8765/health/live` returned `{"status":"ok"}`.
- `GET http://127.0.0.1:8765/health/ready` returned
  `{"status":"ready"}`.
- `/config` reported LLM support, BYOK support, and the balanced default
  profile without exposing a credential.
- Managed logs recorded the three verification requests as normalized routes.

The repository test suite also covers loopback defaults, readiness-gated
automatic browser opening, `--no-browser`, and `--basic`. The complete local
suite passed 654 tests with 5 environment-dependent skips on 2026-08-30. The
installed-wheel CI smoke test now starts outside the checkout with a harmless
browser handler, proves that the default command opens the exact local URL only
after readiness, and still serves all bundled scenarios. The production
container smoke test separately exercises `--no-browser --basic`.

A second read-only Delta check on 2026-08-30 again passed `demo doctor` and
`demo status`, preserved the pinned-node relay, and returned successful live,
ready, and public configuration responses from loopback port 8765. The running
demo was not restarted or reconfigured.

## Boundary not yet claimed

This server-side check does not prove the laptop path. Before the conference,
open `ssh delta-demo` on the actual presentation laptop, visit
`http://127.0.0.1:8765`, and confirm that the ABDA-NL page and `/config` load.
The loopback URL is not directly reachable from the laptop without that SSH
session.

An ordinary-computer install should also be exercised once outside Delta to
confirm that `abda-nl` opens the local browser automatically. Unit tests prove
the launcher logic but cannot prove OS browser integration.
