# hubwise-py-core

Shared Python library for HubWise's Azure Functions automation apps
(`hubwise-sync`, `hubwise-procurement`, `hubwise-fw-lifecycle`). Part of the
[Root Repo Modernization](../Root%20Repo%20Modernization/TRANSITION-PLAN.md)
project — see that document for full architecture and decision log.

## Modules

| Module | Responsibility |
|---|---|
| `config` | Fail-loud environment variable loading — no silent empty defaults |
| `guards` | `DRY_RUN` / `ALLOW_PROD` dual-gate write safety |
| `http` | `requests.Session` with retry/backoff, honoring `429`/`Retry-After` |
| `logging` | Structured summary lines, alert markers, secret redaction |
| `state` | Table Storage idempotency store (condition-keyed action state) |

## Install (from a consuming app repo)

    pip install git+https://github.com/hubwisetech/hubwise-py-core@v0.1.0

## Development

    pip install -e ".[dev]"
    ruff check .
    pytest
