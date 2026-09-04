# Delta contingency checkpoint, 2026-08-29

State: server-side Delta lifecycle verified, laptop tunnel retest pending

This checkpoint records live verification of the private Delta fallback. The
initial checks were read-only. A later lifecycle check deliberately restarted
the launcher-managed process without changing its configuration.

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

A third read-only check on 2026-09-02 produced the same result on
`dt-login03.delta.ncsa.illinois.edu`. The tracked launcher still uses
`make run PORT={port} HOST={host}`, both health endpoints returned their exact
success payloads, and `/config` exposed only the public model catalog and
feature flags. The check did not restart or reconfigure the running demo.

A later lifecycle check on 2026-09-02 ran `demo doctor`, then deliberately ran
`demo restart` from the repository. The launcher reported the demo ready,
`demo status` reported the expected repository and pinned node, and
`GET http://127.0.0.1:8765/health/ready` returned `{"status":"ready"}` after
the replacement process started. The tracked `.demo.json` remained unchanged.
At the same checkpoint, the managed public readiness endpoint also returned
`{"status":"ready"}`. No model provider was called.

On 2026-09-04 CDT, another read-only check confirmed the same tracked launcher
contract. `demo doctor` and `demo status` identified the expected repository,
pinned node, loopback port, and running process. Both loopback health endpoints
returned their exact success payloads, and `/config` reported the public model
catalog without exposing a credential. The process was not restarted or
reconfigured.

## Boundary not yet claimed

This server-side check does not prove the laptop path. Before the conference,
open `ssh delta-demo` on the actual presentation laptop, visit
`http://127.0.0.1:8765`, and confirm that the ABDA-NL page and `/config` load.
The loopback URL is not directly reachable from the laptop without that SSH
session.

An ordinary-computer install should also be exercised once outside Delta to
confirm that `abda-nl` opens the local browser automatically. Unit tests prove
the launcher logic but cannot prove OS browser integration.
