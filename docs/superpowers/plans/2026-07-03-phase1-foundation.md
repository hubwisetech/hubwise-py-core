# Root Repo Modernization — Phase 1 Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build `hubwise-py-core` v0.1 (config, guards, http, logging, state — fully tested, no Azure required to run the suite) and scaffold the three Function App repos (`hubwise-sync`, `hubwise-procurement`, `hubwise-fw-lifecycle`), so that `hubwise-sync` can carry a hello-world timer function through the Phase 1 OIDC-deploy gate the moment the Cowork-side dependencies (GitHub repos, Entra OIDC federation, `rg-hubwise-automation`) exist.

**Architecture:** One shared library repo (`hubwise-py-core`, pip-installed by git tag) consumed by three independent Function App repos. Each Function App repo follows the Azure-Hosted Service Standard's thin-entry/pure-logic split: `function_app.py` wires triggers only; business logic lives in `src/<service>/` and is unit-tested with Azure I/O injected as fakes. Bicep is subscription-scoped, one module per resource, following `hubwise-fwmon`'s exact pattern (Flex Consumption FC1, Python 3.12, system-assigned MI, identity-based storage, App Insights bound to a shared Log Analytics workspace).

**Tech Stack:** Python 3.12 (Azure Functions v2 model), `azure-functions`, `azure-identity`, `azure-data-tables`, `requests`, pytest, ruff, Bicep, GitHub Actions (OIDC to Azure).

## Global Constraints

- Every write-capable client defaults `DRY_RUN=1`, `ALLOW_PROD=0`; both gates must be explicitly flipped to write (Transition Plan D-7).
- No secret ever in code, config, git, or logs. `DefaultAzureCredential` everywhere; Key Vault references resolved by the platform via managed identity (Transition Plan D-5; Azure-Hosted Service Standard §5).
- Fail loudly on missing required config — no silent empty-string defaults (Azure-Hosted Service Standard §6).
- One structured summary line per run: `job=... read=... written=... skipped=... errors=...` (Transition Plan D-10).
- Greppable alert markers (e.g. `SYNC_DEGRADED`) for alertable conditions, wired to Azure Monitor later (Transition Plan D-10).
- Never log secrets; redact credential-shaped values (Azure-Hosted Service Standard §8, Outbound Standard Rule 5).
- HTTP retries: back off on 5xx/timeouts, honor `429`/`Retry-After`, never retry non-idempotent methods by default (Outbound Standard Rule 4).
- Idempotency: state keyed by the causing condition, not by run/timestamp — a re-run against the same condition is a no-op (Transition Plan D-6; Outbound Standard Rule 2).
- Repo layout per Azure-Hosted Service Standard §4: `function_app.py` (thin entry) + `src/<service>/`, `src/shared/` (pure, unit-testable) + `tests/` + `infra/` (`main.bicep` + `modules/`) + `scripts/` + gitignored `.deploy/`.
- CI: pytest green + `python -m py_compile` on the Functions entry; no merge with a failing or skipped test (Azure-Hosted Service Standard §10).
- Managed Identity roles: **Key Vault Secrets User** on `hubwise-ops`; **Storage Table Data Contributor** / **Storage Blob Data Owner** / **Storage Queue Data Contributor** on the app's storage account — least privilege, never broader (Azure-Hosted Service Standard §5, `hubwise-fwmon` reconciler-app.bicep).
- Package name `hubwise-py-core` (PyPI/dist name), import name `hubwise_py_core`; consumed by app repos via `pip install git+https://github.com/hubwisetech/hubwise-py-core@v0.1.0`.

---

## Part A — `hubwise-py-core` v0.1 (fully unblocked — no external dependency)

Repo root: `C:\Users\swilson\hubwise-py-core` (git already initialized locally, branch `main`, no GitHub remote yet — see blocker note at the end of this plan).

### Task 1: Repo scaffold — packaging, lint, CI

**Files:**
- Create: `C:\Users\swilson\hubwise-py-core\pyproject.toml`
- Create: `C:\Users\swilson\hubwise-py-core\.gitignore`
- Create: `C:\Users\swilson\hubwise-py-core\README.md`
- Create: `C:\Users\swilson\hubwise-py-core\src\hubwise_py_core\__init__.py`
- Create: `C:\Users\swilson\hubwise-py-core\.github\workflows\ci.yml`

**Interfaces:**
- Produces: an installable package `hubwise_py_core` importable by later tasks; a `pytest` + `ruff check` CI gate later tasks must stay green against.

- [ ] **Step 1: Write `pyproject.toml`**

```toml
[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"

[project]
name = "hubwise-py-core"
version = "0.1.0"
description = "Shared Python library for HubWise Azure Functions automation: config, write guards, HTTP retry session, structured logging, Table Storage idempotency state."
requires-python = ">=3.12"
dependencies = [
    "requests>=2.31",
    "azure-identity>=1.17.0",
    "azure-data-tables>=12.5.0",
]

[project.optional-dependencies]
dev = ["pytest>=8.0", "ruff>=0.6"]

[tool.setuptools.packages.find]
where = ["src"]

[tool.ruff]
target-version = "py312"
line-length = 100

[tool.ruff.lint]
select = ["E", "F", "I", "UP", "B"]

[tool.pytest.ini_options]
testpaths = ["tests"]
```

- [ ] **Step 2: Write `.gitignore`**

```
.venv/
__pycache__/
*.pyc
.pytest_cache/
.mypy_cache/
.ruff_cache/
*.egg-info/
build/
dist/
local.settings.json
*.env
.env
.env.*

# Secrets / certs (NEVER commit)
*.pfx
*.pem
*.p12
*.key
*.cer

# OS cruft
.DS_Store
Thumbs.db
desktop.ini
```

- [ ] **Step 3: Write `src/hubwise_py_core/__init__.py`**

```python
"""HubWise shared Python library for Azure Functions automation.

Modules: config (fail-loud env loading), guards (DRY_RUN/ALLOW_PROD write
gate), http (retrying requests session), logging (structured summary lines
+ alert markers + secret redaction), state (Table Storage idempotency).
"""

__version__ = "0.1.0"
```

- [ ] **Step 4: Write `README.md`**

```markdown
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
```

- [ ] **Step 5: Write `.github/workflows/ci.yml`**

```yaml
name: CI

on:
  pull_request:
  push:
    branches: [main]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - run: pip install -e ".[dev]"
      - run: ruff check .
      - run: pytest -v
```

- [ ] **Step 6: Commit**

```bash
cd ~/hubwise-py-core
git add pyproject.toml .gitignore README.md src/hubwise_py_core/__init__.py .github/workflows/ci.yml
git commit -m "chore: scaffold hubwise-py-core packaging, lint, and CI"
```

---

### Task 2: `guards` module — DRY_RUN / ALLOW_PROD write gate

**Files:**
- Create: `C:\Users\swilson\hubwise-py-core\src\hubwise_py_core\guards.py`
- Test: `C:\Users\swilson\hubwise-py-core\tests\test_guards.py`

**Interfaces:**
- Produces: `WriteGuard(env: dict | None = None)` with properties `.dry_run: bool`, `.allow_prod: bool`, `.writes_allowed: bool`, and method `.check_write(description: str) -> bool`. Every write-capable client built in later phases calls `guard.check_write(...)` before performing a real write.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_guards.py
import logging

from hubwise_py_core.guards import WriteGuard


def test_default_env_blocks_writes():
    guard = WriteGuard(env={})
    assert guard.dry_run is True
    assert guard.allow_prod is False
    assert guard.writes_allowed is False


def test_dry_run_off_alone_does_not_allow_writes():
    guard = WriteGuard(env={"DRY_RUN": "0"})
    assert guard.writes_allowed is False


def test_allow_prod_alone_does_not_allow_writes():
    guard = WriteGuard(env={"ALLOW_PROD": "1"})
    assert guard.writes_allowed is False


def test_both_gates_open_allows_writes():
    guard = WriteGuard(env={"DRY_RUN": "0", "ALLOW_PROD": "1"})
    assert guard.writes_allowed is True


def test_check_write_returns_false_and_logs_when_blocked(caplog):
    caplog.set_level(logging.INFO)
    guard = WriteGuard(env={})
    assert guard.check_write("create ticket") is False
    assert "DRY_RUN" in caplog.text
    assert "create ticket" in caplog.text


def test_check_write_returns_true_when_allowed():
    guard = WriteGuard(env={"DRY_RUN": "0", "ALLOW_PROD": "1"})
    assert guard.check_write("create ticket") is True


def test_env_values_are_stripped_of_whitespace_and_cr():
    # az ... -o tsv under the WSL shim appends a trailing \r
    guard = WriteGuard(env={"DRY_RUN": "0 \r", "ALLOW_PROD": "1\r"})
    assert guard.writes_allowed is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd ~/hubwise-py-core && pip install -e ".[dev]" && pytest tests/test_guards.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'hubwise_py_core.guards'`

- [ ] **Step 3: Write minimal implementation**

```python
# src/hubwise_py_core/guards.py
"""Production write-safety guard: DRY_RUN + ALLOW_PROD dual gate.

Every write-capable client in a hubwise-py-core consumer calls
``check_write()`` before performing a real write. Two independent
environment flags must both be open for a write to proceed, so a single
misconfigured flag can never enable production writes on its own
(Transition Plan D-7).
"""
from __future__ import annotations

import logging
import os

log = logging.getLogger(__name__)


def _flag(name: str, default: str, env: dict) -> bool:
    return env.get(name, default).strip() == "1"


class WriteGuard:
    def __init__(self, env: dict | None = None):
        env = os.environ if env is None else env
        self.dry_run = _flag("DRY_RUN", "1", env)
        self.allow_prod = _flag("ALLOW_PROD", "0", env)

    @property
    def writes_allowed(self) -> bool:
        return (not self.dry_run) and self.allow_prod

    def check_write(self, description: str) -> bool:
        """Return True if the write should proceed.

        When blocked, logs a suppression line (never raises) so a dry-run
        pass produces a readable diff of what it would have done.
        """
        if self.writes_allowed:
            return True
        log.info(
            "DRY_RUN: suppressing write (%s) [dry_run=%s allow_prod=%s]",
            description, self.dry_run, self.allow_prod,
        )
        return False
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_guards.py -v`
Expected: 7 passed

- [ ] **Step 5: Commit**

```bash
git add src/hubwise_py_core/guards.py tests/test_guards.py
git commit -m "feat: add WriteGuard DRY_RUN/ALLOW_PROD dual-gate"
```

---

### Task 3: `config` module — fail-loud environment loading

**Files:**
- Create: `C:\Users\swilson\hubwise-py-core\src\hubwise_py_core\config.py`
- Test: `C:\Users\swilson\hubwise-py-core\tests\test_config.py`

**Interfaces:**
- Produces: `require(name, env=None) -> str` (raises `MissingConfigError` if absent/empty), `optional(name, default="", env=None) -> str`, `flag(name, default="0", env=None) -> bool`. Per-app `Config` dataclasses in later phases (e.g. `hubwise-sync`'s own `config.py`) build on these.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_config.py
import pytest

from hubwise_py_core.config import MissingConfigError, flag, optional, require


def test_require_returns_stripped_value():
    value = require("CW_SITE", env={"CW_SITE": " api-na.myconnectwise.net \r"})
    assert value == "api-na.myconnectwise.net"


def test_require_raises_on_missing_key():
    with pytest.raises(MissingConfigError):
        require("CW_SITE", env={})


def test_require_raises_on_empty_value():
    with pytest.raises(MissingConfigError):
        require("CW_SITE", env={"CW_SITE": "   "})


def test_require_error_names_the_missing_key():
    with pytest.raises(MissingConfigError, match="CW_SITE"):
        require("CW_SITE", env={})


def test_optional_returns_default_when_missing():
    assert optional("FOO", default="bar", env={}) == "bar"


def test_optional_returns_value_when_present():
    assert optional("FOO", default="bar", env={"FOO": "baz"}) == "baz"


def test_optional_returns_default_when_value_is_blank():
    assert optional("FOO", default="bar", env={"FOO": "   "}) == "bar"


def test_flag_true_only_for_literal_one():
    assert flag("DRY_RUN", env={"DRY_RUN": "1"}) is True
    assert flag("DRY_RUN", env={"DRY_RUN": "true"}) is False


def test_flag_uses_default_when_missing():
    assert flag("DRY_RUN", default="1", env={}) is True
    assert flag("DRY_RUN", default="0", env={}) is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_config.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'hubwise_py_core.config'`

- [ ] **Step 3: Write minimal implementation**

```python
# src/hubwise_py_core/config.py
"""Startup configuration loading: fail loudly on missing required settings.

Per the Azure-Hosted Service Standard §6, a required setting that is
silently empty is an outage waiting to happen. ``require()`` raises
immediately rather than returning an empty string a caller might not check.
"""
from __future__ import annotations

import os


class MissingConfigError(RuntimeError):
    """Raised when a required environment variable is absent or empty."""


def require(name: str, env: dict | None = None) -> str:
    """Return env[name], stripped. Raise MissingConfigError if absent/empty."""
    env = os.environ if env is None else env
    value = env.get(name, "").strip()
    if not value:
        raise MissingConfigError(f"missing required configuration: {name}")
    return value


def optional(name: str, default: str = "", env: dict | None = None) -> str:
    """Return env[name], stripped, or default if absent/empty."""
    env = os.environ if env is None else env
    value = env.get(name, "").strip()
    return value if value else default


def flag(name: str, default: str = "0", env: dict | None = None) -> bool:
    """Return True iff env[name] (or default) stripped equals '1'."""
    env = os.environ if env is None else env
    return env.get(name, default).strip() == "1"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_config.py -v`
Expected: 9 passed

- [ ] **Step 5: Commit**

```bash
git add src/hubwise_py_core/config.py tests/test_config.py
git commit -m "feat: add fail-loud config loading (require/optional/flag)"
```

---

### Task 4: `http` module — retrying session

**Files:**
- Create: `C:\Users\swilson\hubwise-py-core\src\hubwise_py_core\http.py`
- Test: `C:\Users\swilson\hubwise-py-core\tests\test_http.py`

**Interfaces:**
- Produces: `build_session(timeout=30, max_retries=3, backoff_factor=1.0) -> requests.Session`, constants `DEFAULT_TIMEOUT_SECONDS`, `DEFAULT_MAX_RETRIES`, `RETRYABLE_STATUS_CODES`. Every vendor client in later phases (`cw_manage.py`, `hudu.py`, etc.) builds its session via this function.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_http.py
import requests

from hubwise_py_core.http import (
    DEFAULT_MAX_RETRIES,
    RETRYABLE_STATUS_CODES,
    build_session,
)


def test_build_session_returns_requests_session():
    session = build_session()
    assert isinstance(session, requests.Session)


def test_build_session_mounts_retry_adapter_on_both_schemes():
    session = build_session()
    https_adapter = session.get_adapter("https://example.com")
    http_adapter = session.get_adapter("http://example.com")
    assert https_adapter.max_retries.total == DEFAULT_MAX_RETRIES
    assert http_adapter.max_retries.total == DEFAULT_MAX_RETRIES


def test_build_session_honors_custom_max_retries():
    session = build_session(max_retries=5)
    adapter = session.get_adapter("https://example.com")
    assert adapter.max_retries.total == 5


def test_retryable_status_codes_include_429_and_5xx():
    for code in (429, 500, 502, 503, 504):
        assert code in RETRYABLE_STATUS_CODES


def test_build_session_status_forcelist_matches_retryable_codes():
    session = build_session()
    adapter = session.get_adapter("https://example.com")
    assert set(adapter.max_retries.status_forcelist) == set(RETRYABLE_STATUS_CODES)


def test_build_session_respects_retry_after_header():
    session = build_session()
    adapter = session.get_adapter("https://example.com")
    assert adapter.max_retries.respect_retry_after_header is True


def test_build_session_does_not_retry_post_by_default():
    # POST is not idempotent by default; retrying it risks double-creation.
    # urllib3's default allowed_methods excludes POST/PATCH.
    session = build_session()
    adapter = session.get_adapter("https://example.com")
    assert "POST" not in adapter.max_retries.allowed_methods


def test_session_applies_default_timeout(monkeypatch):
    session = build_session(timeout=5)
    captured = {}

    def fake_send(self, request, **kwargs):
        captured["timeout"] = kwargs.get("timeout")
        response = requests.Response()
        response.status_code = 200
        return response

    monkeypatch.setattr(requests.Session, "send", fake_send)
    session.get("https://example.com")
    assert captured["timeout"] == 5


def test_session_explicit_timeout_overrides_default(monkeypatch):
    session = build_session(timeout=5)
    captured = {}

    def fake_send(self, request, **kwargs):
        captured["timeout"] = kwargs.get("timeout")
        response = requests.Response()
        response.status_code = 200
        return response

    monkeypatch.setattr(requests.Session, "send", fake_send)
    session.get("https://example.com", timeout=1)
    assert captured["timeout"] == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_http.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'hubwise_py_core.http'`

- [ ] **Step 3: Write minimal implementation**

```python
# src/hubwise_py_core/http.py
"""HTTP session with retry/backoff, honoring 429/Retry-After, TLS verify on.

Every outbound HTTP client in the hubwise-py-core apps builds its session
here rather than calling ``requests`` directly, so retry/backoff/timeout
behavior is consistent fleet-wide (Outbound Integration Standard, Rule 4).
TLS verification is always on — requests' default; never pass
``verify=False`` on a client built from this session.
"""
from __future__ import annotations

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

DEFAULT_TIMEOUT_SECONDS = 30
DEFAULT_MAX_RETRIES = 3
DEFAULT_BACKOFF_FACTOR = 1.0
RETRYABLE_STATUS_CODES = (429, 500, 502, 503, 504)


class TimeoutSession(requests.Session):
    """A requests.Session with a default timeout applied to every request."""

    def __init__(self, timeout: float = DEFAULT_TIMEOUT_SECONDS):
        super().__init__()
        self._default_timeout = timeout

    def request(self, method, url, **kwargs):
        kwargs.setdefault("timeout", self._default_timeout)
        return super().request(method, url, **kwargs)


def build_session(
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
    max_retries: int = DEFAULT_MAX_RETRIES,
    backoff_factor: float = DEFAULT_BACKOFF_FACTOR,
) -> requests.Session:
    """Build a requests.Session with retry/backoff and TLS verification on.

    Retries GET/HEAD/PUT/DELETE/OPTIONS/TRACE (urllib3's default safe
    method set — POST/PATCH are deliberately excluded so a retry can never
    double-create) on connection errors and on RETRYABLE_STATUS_CODES,
    honoring a server's Retry-After header when present.
    """
    session = TimeoutSession(timeout=timeout)
    retry = Retry(
        total=max_retries,
        backoff_factor=backoff_factor,
        status_forcelist=RETRYABLE_STATUS_CODES,
        respect_retry_after_header=True,
        raise_on_status=False,
    )
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    return session
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_http.py -v`
Expected: 9 passed

- [ ] **Step 5: Commit**

```bash
git add src/hubwise_py_core/http.py tests/test_http.py
git commit -m "feat: add retrying HTTP session builder"
```

---

### Task 5: `logging` module — structured summary, alert markers, redaction

**Files:**
- Create: `C:\Users\swilson\hubwise-py-core\src\hubwise_py_core\logging.py`
- Test: `C:\Users\swilson\hubwise-py-core\tests\test_logging.py`

**Interfaces:**
- Produces: `summary(job, read=0, written=0, skipped=0, errors=0, logger=None)`, `alert(marker, detail, logger=None)`, `redact(value) -> str`, `SecretRedactionFilter` (a `logging.Filter`). Every timer function's final line calls `summary(...)`; degraded-condition paths call `alert(...)`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_logging.py
import logging

from hubwise_py_core.logging import SecretRedactionFilter, alert, redact, summary


def test_summary_emits_structured_line(caplog):
    caplog.set_level(logging.INFO)
    summary("sync_cw_sites_to_hudu", read=42, written=5, skipped=1, errors=0)
    assert "job=sync_cw_sites_to_hudu" in caplog.text
    assert "read=42" in caplog.text
    assert "written=5" in caplog.text
    assert "skipped=1" in caplog.text
    assert "errors=0" in caplog.text


def test_summary_defaults_all_counts_to_zero(caplog):
    caplog.set_level(logging.INFO)
    summary("noop_job")
    assert "read=0" in caplog.text
    assert "written=0" in caplog.text
    assert "skipped=0" in caplog.text
    assert "errors=0" in caplog.text


def test_alert_emits_marker_and_detail(caplog):
    caplog.set_level(logging.ERROR)
    alert("SYNC_DEGRADED", "Hudu unreachable after 3 retries")
    assert "SYNC_DEGRADED" in caplog.text
    assert "Hudu unreachable after 3 retries" in caplog.text


def test_redact_replaces_nonempty_value():
    assert redact("sk-abc123") == "***REDACTED***"


def test_redact_leaves_empty_value_alone():
    assert redact("") == ""


def test_secret_redaction_filter_redacts_api_key_pairs():
    record = logging.LogRecord(
        name="test", level=logging.INFO, pathname=__file__, lineno=1,
        msg="calling Hudu api_key=abcdef123456 ok", args=(), exc_info=None,
    )
    SecretRedactionFilter().filter(record)
    assert "abcdef123456" not in record.getMessage()
    assert "***REDACTED***" in record.getMessage()


def test_secret_redaction_filter_redacts_password_and_token():
    record = logging.LogRecord(
        name="test", level=logging.INFO, pathname=__file__, lineno=1,
        msg="login password=hunter2 token: eyJhbGciOi", args=(), exc_info=None,
    )
    SecretRedactionFilter().filter(record)
    text = record.getMessage()
    assert "hunter2" not in text
    assert "eyJhbGciOi" not in text


def test_secret_redaction_filter_leaves_non_secret_pairs_alone():
    record = logging.LogRecord(
        name="test", level=logging.INFO, pathname=__file__, lineno=1,
        msg="job=sync read=42 written=5", args=(), exc_info=None,
    )
    SecretRedactionFilter().filter(record)
    assert record.getMessage() == "job=sync read=42 written=5"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_logging.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'hubwise_py_core.logging'`

- [ ] **Step 3: Write minimal implementation**

```python
# src/hubwise_py_core/logging.py
"""Structured summary logging + greppable alert markers + secret redaction.

Every function run emits exactly one structured summary line in
``job=... read=... written=... skipped=... errors=...`` form (Transition
Plan D-10) so steady-state health is readable at a glance and Azure Monitor
scheduled-query alert rules can match a stable shape. Alert conditions are
raised as a separate greppable marker line, never folded into the summary.
"""
from __future__ import annotations

import logging
import re

_SECRET_KEY_FRAGMENT = r"(?:api[_-]?key|password|secret|token|authorization)"
_PAIR_PATTERN = re.compile(
    rf"(?P<key>[\w.-]*{_SECRET_KEY_FRAGMENT}[\w.-]*)"
    r"(?P<sep>\s*[:=]\s*)"
    r"(?P<value>\S+)",
    re.IGNORECASE,
)
_REDACTED = "***REDACTED***"


def summary(
    job: str,
    read: int = 0,
    written: int = 0,
    skipped: int = 0,
    errors: int = 0,
    logger: "logging.Logger | None" = None,
) -> None:
    """Emit the one-line-per-run structured summary (Transition Plan D-10)."""
    log = logger or logging.getLogger(job)
    log.info(
        "job=%s read=%d written=%d skipped=%d errors=%d",
        job, read, written, skipped, errors,
    )


def alert(marker: str, detail: str, logger: "logging.Logger | None" = None) -> None:
    """Emit a greppable alert marker line (e.g. SYNC_DEGRADED,
    FW_UPGRADE_HALTED, CALLBACK_REJECTED — Transition Plan D-10) for an
    Azure Monitor scheduled-query alert rule to match on. ``marker`` should
    be UPPER_SNAKE_CASE and stable; alert rules match its literal text.
    """
    log = logger or logging.getLogger("alert")
    log.error("%s: %s", marker, detail)


def redact(value: str) -> str:
    """Replace a non-empty value with a redaction placeholder."""
    return _REDACTED if value else value


class SecretRedactionFilter(logging.Filter):
    """A logging.Filter that redacts values of secret-looking keys.

    Attach via ``logger.addFilter(SecretRedactionFilter())``. Scans the
    formatted message for ``key=value`` or ``key: value`` pairs where the
    key matches a secret-like pattern (api_key, password, secret, token,
    authorization) and replaces the value.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        record.msg = _PAIR_PATTERN.sub(self._redact_match, record.getMessage())
        record.args = ()
        return True

    @staticmethod
    def _redact_match(match: "re.Match[str]") -> str:
        return f"{match.group('key')}{match.group('sep')}{_REDACTED}"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_logging.py -v`
Expected: 8 passed

- [ ] **Step 5: Commit**

```bash
git add src/hubwise_py_core/logging.py tests/test_logging.py
git commit -m "feat: add structured summary logging, alert markers, secret redaction"
```

---

### Task 6: `state` module — Table Storage idempotency store

**Files:**
- Create: `C:\Users\swilson\hubwise-py-core\src\hubwise_py_core\state.py`
- Test: `C:\Users\swilson\hubwise-py-core\tests\test_state.py`

**Interfaces:**
- Produces: `ActionStateStore` (Protocol: `get_action`, `record_action`, `clear_action`), `InMemoryActionStateStore` (tests/dry-run), `TableActionStateStore` (azure-data-tables backed, managed identity). Every writer function in later phases holds one of these and checks `get_action` before writing, `record_action` after.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_state.py
from unittest.mock import MagicMock, patch

from hubwise_py_core.state import InMemoryActionStateStore, TableActionStateStore


def test_get_action_returns_none_when_unset():
    store = InMemoryActionStateStore()
    assert store.get_action("po-tracking", "PO123#TRACK456") is None


def test_record_then_get_returns_action_id():
    store = InMemoryActionStateStore()
    store.record_action("po-tracking", "PO123#TRACK456", "ticket-789")
    assert store.get_action("po-tracking", "PO123#TRACK456") == "ticket-789"


def test_record_is_idempotent_on_repeat_condition():
    store = InMemoryActionStateStore()
    store.record_action("po-tracking", "PO123#TRACK456", "ticket-789")
    store.record_action("po-tracking", "PO123#TRACK456", "ticket-789")
    assert store.get_action("po-tracking", "PO123#TRACK456") == "ticket-789"


def test_clear_action_removes_recorded_state():
    store = InMemoryActionStateStore()
    store.record_action("po-tracking", "PO123#TRACK456", "ticket-789")
    store.clear_action("po-tracking", "PO123#TRACK456")
    assert store.get_action("po-tracking", "PO123#TRACK456") is None


def test_clear_action_on_unset_condition_is_a_noop():
    store = InMemoryActionStateStore()
    store.clear_action("po-tracking", "unknown")  # must not raise
    assert store.get_action("po-tracking", "unknown") is None


def test_partitions_are_independent():
    store = InMemoryActionStateStore()
    store.record_action("po-tracking", "KEY1", "action-a")
    store.record_action("other-job", "KEY1", "action-b")
    assert store.get_action("po-tracking", "KEY1") == "action-a"
    assert store.get_action("other-job", "KEY1") == "action-b"


@patch("azure.identity.DefaultAzureCredential")
@patch("azure.data.tables.TableServiceClient")
def test_table_store_get_action_returns_none_on_missing_entity(mock_client_cls, mock_cred):
    from azure.core.exceptions import ResourceNotFoundError

    mock_table = MagicMock()
    mock_table.get_entity.side_effect = ResourceNotFoundError("not found")
    mock_client_cls.return_value.create_table_if_not_exists.return_value = mock_table

    store = TableActionStateStore(account_url="https://acct.table.core.windows.net", table_name="state")
    assert store.get_action("po-tracking", "PO123") is None


@patch("azure.identity.DefaultAzureCredential")
@patch("azure.data.tables.TableServiceClient")
def test_table_store_record_action_upserts_entity(mock_client_cls, mock_cred):
    mock_table = MagicMock()
    mock_client_cls.return_value.create_table_if_not_exists.return_value = mock_table

    store = TableActionStateStore(account_url="https://acct.table.core.windows.net", table_name="state")
    store.record_action("po-tracking", "PO123", "ticket-789")

    mock_table.upsert_entity.assert_called_once_with({
        "PartitionKey": "po-tracking",
        "RowKey": "PO123",
        "action_id": "ticket-789",
    })


@patch("azure.identity.DefaultAzureCredential")
@patch("azure.data.tables.TableServiceClient")
def test_table_store_get_action_returns_recorded_id(mock_client_cls, mock_cred):
    mock_table = MagicMock()
    mock_table.get_entity.return_value = {"action_id": "ticket-789"}
    mock_client_cls.return_value.create_table_if_not_exists.return_value = mock_table

    store = TableActionStateStore(account_url="https://acct.table.core.windows.net", table_name="state")
    assert store.get_action("po-tracking", "PO123") == "ticket-789"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_state.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'hubwise_py_core.state'`

- [ ] **Step 3: Write minimal implementation**

```python
# src/hubwise_py_core/state.py
"""Table Storage idempotency/action state (Transition Plan D-6).

``ActionStateStore`` is the interface every write-capable function depends
on. ``get_action`` / ``record_action`` are keyed by the *condition* that
caused a write (e.g. a PO number + tracking number), not by run/timestamp,
so a re-run against the same condition is a no-op. Two implementations:

* ``InMemoryActionStateStore`` — no Azure; for tests.
* ``TableActionStateStore`` — azure-data-tables backed, managed-identity
  auth; for the Function App.
"""
from __future__ import annotations

from typing import Optional, Protocol


class ActionStateStore(Protocol):
    def get_action(self, partition: str, condition_key: str) -> Optional[str]:
        """Return the previously recorded action_id for this condition, or None."""
        ...

    def record_action(self, partition: str, condition_key: str, action_id: str) -> None:
        """Record that ``action_id`` was taken for this condition."""
        ...

    def clear_action(self, partition: str, condition_key: str) -> None:
        """Clear a recorded action (e.g. once the condition resolves)."""
        ...


class InMemoryActionStateStore:
    def __init__(self):
        self._actions: dict[tuple[str, str], str] = {}

    def get_action(self, partition: str, condition_key: str) -> Optional[str]:
        return self._actions.get((partition, condition_key))

    def record_action(self, partition: str, condition_key: str, action_id: str) -> None:
        self._actions[(partition, condition_key)] = action_id

    def clear_action(self, partition: str, condition_key: str) -> None:
        self._actions.pop((partition, condition_key), None)


class TableActionStateStore:
    """azure-data-tables backed store using managed identity.

    Table design: PartitionKey=<partition> (caller-chosen, e.g. a job name),
    RowKey=<condition_key>, column ``action_id``. Imported lazily so the
    in-memory path (tests/dry-run) needs no Azure SDK.
    """

    def __init__(self, account_url: str, table_name: str, credential=None,
                 create_if_missing: bool = True):
        from azure.data.tables import TableServiceClient

        if credential is None:
            from azure.identity import DefaultAzureCredential

            credential = DefaultAzureCredential()
        svc = TableServiceClient(endpoint=account_url, credential=credential)
        self._table = (
            svc.create_table_if_not_exists(table_name)
            if create_if_missing
            else svc.get_table_client(table_name)
        )

    def get_action(self, partition: str, condition_key: str) -> Optional[str]:
        from azure.core.exceptions import ResourceNotFoundError

        try:
            entity = self._table.get_entity(partition, condition_key)
        except ResourceNotFoundError:
            return None
        return entity.get("action_id")

    def record_action(self, partition: str, condition_key: str, action_id: str) -> None:
        self._table.upsert_entity({
            "PartitionKey": partition,
            "RowKey": condition_key,
            "action_id": action_id,
        })

    def clear_action(self, partition: str, condition_key: str) -> None:
        from azure.core.exceptions import ResourceNotFoundError

        try:
            self._table.delete_entity(partition, condition_key)
        except ResourceNotFoundError:
            pass
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_state.py -v`
Expected: 9 passed

- [ ] **Step 5: Commit**

```bash
git add src/hubwise_py_core/state.py tests/test_state.py
git commit -m "feat: add Table Storage idempotency action state store"
```

---

### Task 7: Full-suite verification and v0.1.0 tag

**Files:** none new — verification only.

- [ ] **Step 1: Run the full suite and lint**

Run: `cd ~/hubwise-py-core && pytest -v && ruff check .`
Expected: all tests pass (5 modules × their test files, ~42 tests total), zero ruff findings.

- [ ] **Step 2: Tag v0.1.0**

```bash
git tag -a v0.1.0 -m "hubwise-py-core v0.1.0: config, guards, http, logging, state"
```

(Do not push yet — no GitHub remote exists for this repo. See the blocker note at the end of this plan.)

---

## Part B — `hubwise-sync` scaffold + hello-world timer (Phase 1 gate vehicle)

`hubwise-sync` is Phase 2's pilot home (`sync_cw_sites_to_hudu`) and carries the Phase 1 gate: *a hello-world timer function deploys via OIDC, reads a secret from `hubwise-ops` via Managed Identity, writes a Table Storage state row, and logs a structured line visible in Log Analytics.*

Repo root: `C:\Users\swilson\hubwise-sync` (create fresh, same pattern as `hubwise-py-core`).

### Task 8: Repo scaffold

**Files:**
- Create: `C:\Users\swilson\hubwise-sync\.gitignore`
- Create: `C:\Users\swilson\hubwise-sync\README.md`
- Create: `C:\Users\swilson\hubwise-sync\host.json`
- Create: `C:\Users\swilson\hubwise-sync\requirements.txt`
- Create: `C:\Users\swilson\hubwise-sync\function_app.py`
- Create: `C:\Users\swilson\hubwise-sync\src\sync\__init__.py`
- Create: `C:\Users\swilson\hubwise-sync\.github\workflows\ci-cd.yml`

**Interfaces:**
- Consumes: `hubwise_py_core.config.require/optional`, `hubwise_py_core.state.TableActionStateStore`, `hubwise_py_core.logging.summary`.
- Produces: `function_app.py`'s `app = func.FunctionApp()` object other timer functions in Phase 2+ register against; `src/sync/` as the package home for `sync_cw_sites_to_hudu` and its siblings.

- [ ] **Step 1: Write `.gitignore`** (identical to `hubwise-fwmon`'s, adapted)

```
.venv/
__pycache__/
*.pyc
.pytest_cache/
.mypy_cache/
.ruff_cache/
local.settings.json
*.env
.env
.env.*

# Secrets / certs (NEVER commit)
*.pfx
*.pem
*.p12
*.key
*.cer

# Azure deploy staging
.deploy/

# Diagnostic outputs (may contain customer data)
scripts/out/

# OS cruft
.DS_Store
Thumbs.db
desktop.ini
```

- [ ] **Step 2: Write `host.json`**

```json
{
  "version": "2.0",
  "logging": {
    "applicationInsights": {
      "samplingSettings": {
        "isEnabled": true,
        "excludedTypes": "Request"
      }
    }
  },
  "extensionBundle": {
    "id": "Microsoft.Azure.Functions.ExtensionBundle",
    "version": "[4.*, 5.0.0)"
  }
}
```

- [ ] **Step 3: Write `requirements.txt`**

```
azure-functions>=1.21.0
azure-data-tables>=12.5.0
azure-identity>=1.17.0
requests>=2.31
hubwise-py-core @ git+https://github.com/hubwisetech/hubwise-py-core@v0.1.0
```

- [ ] **Step 4: Write `src/sync/__init__.py`**

```python
"""Business logic package for the hubwise-sync Function App.

Pure logic + injected I/O only — no azure.functions imports here. See the
Azure-Hosted Service Standard §4: function_app.py is the thin entry; this
package is the unit-tested layer underneath.
"""
```

- [ ] **Step 5: Write `function_app.py`** (thin entry — one hello-world timer for the Phase 1 gate)

```python
"""hubwise-sync Function App — thin entry point.

Wires triggers to business logic in src/sync/ and nothing more, per the
Azure-Hosted Service Standard §4. The health_check_ping timer exists to
prove the Phase 1 pipeline (OIDC deploy, Managed Identity -> Key Vault,
Table Storage write, structured logging visible in Log Analytics) before
sync_cw_sites_to_hudu (Phase 2) lands in this same app.
"""
from __future__ import annotations

import azure.functions as func

from sync.health_check import run_health_check_ping

app = func.FunctionApp()


@app.timer_trigger(schedule="0 0 * * * *", arg_name="timer", run_on_startup=False,
                    use_monitor=True)
def health_check_ping(timer: func.TimerRequest) -> None:
    run_health_check_ping()
```

- [ ] **Step 6: Write `.github/workflows/ci-cd.yml`**

```yaml
name: CI/CD

on:
  pull_request:
  push:
    branches: [main]

permissions:
  id-token: write
  contents: read

jobs:
  build-and-test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - run: pip install -r requirements.txt
      - run: pip install ruff pytest
      - run: ruff check .
      - run: pytest -v
      - run: python -m py_compile function_app.py

  deploy:
    needs: build-and-test
    if: github.ref == 'refs/heads/main' && github.event_name == 'push'
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - name: Azure login (OIDC)
        uses: azure/login@v2
        with:
          client-id: ${{ secrets.AZURE_CLIENT_ID }}
          tenant-id: ${{ secrets.AZURE_TENANT_ID }}
          subscription-id: ${{ secrets.AZURE_SUBSCRIPTION_ID }}
      - name: Build deploy package
        run: |
          pip install --target=".python_packages/lib/site-packages" -r requirements.txt
      - name: Deploy to Azure Functions
        uses: Azure/functions-action@v1
        with:
          app-name: hubwise-sync
          package: .
```

- [ ] **Step 7: Initialize repo and commit**

```bash
mkdir -p ~/hubwise-sync/src/sync ~/hubwise-sync/.github/workflows ~/hubwise-sync/tests ~/hubwise-sync/infra/modules ~/hubwise-sync/scripts
cd ~/hubwise-sync && git init -q && git branch -m main
git add .gitignore README.md host.json requirements.txt function_app.py src/sync/__init__.py .github/workflows/ci-cd.yml
git commit -m "chore: scaffold hubwise-sync repo layout"
```

(Write `README.md` before this step using the same structure as `hubwise-py-core`'s, describing the app's purpose, the Phase 1 gate, and a link to the transition plan.)

---

### Task 9: `health_check_ping` business logic (TDD)

**Files:**
- Create: `C:\Users\swilson\hubwise-sync\src\sync\health_check.py`
- Test: `C:\Users\swilson\hubwise-sync\tests\test_health_check.py`

**Interfaces:**
- Consumes: `hubwise_py_core.config.require`, `hubwise_py_core.state.ActionStateStore` (injected), `hubwise_py_core.logging.summary`.
- Produces: `run_health_check_ping(state_store=None, env=None) -> None` — the pure-logic function `function_app.py`'s `health_check_ping` wraps. Building the real `TableActionStateStore` from `STORAGE_TABLE_URL` happens inside this function (the one Azure-touching seam), so tests inject an `InMemoryActionStateStore` instead.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_health_check.py
import logging

from hubwise_py_core.state import InMemoryActionStateStore

from sync.health_check import run_health_check_ping


def test_health_check_ping_records_a_run(caplog):
    caplog.set_level(logging.INFO)
    store = InMemoryActionStateStore()

    run_health_check_ping(state_store=store, env={"HUBWISE_OPS_PROBE_VALUE": "ok"})

    assert store.get_action("health-check", "hubwise-sync") == "ok"


def test_health_check_ping_emits_structured_summary(caplog):
    caplog.set_level(logging.INFO)
    store = InMemoryActionStateStore()

    run_health_check_ping(state_store=store, env={"HUBWISE_OPS_PROBE_VALUE": "ok"})

    assert "job=health_check_ping" in caplog.text
    assert "written=1" in caplog.text


def test_health_check_ping_is_a_noop_write_when_value_unchanged(caplog):
    caplog.set_level(logging.INFO)
    store = InMemoryActionStateStore()
    store.record_action("health-check", "hubwise-sync", "ok")

    run_health_check_ping(state_store=store, env={"HUBWISE_OPS_PROBE_VALUE": "ok"})

    assert "written=0" in caplog.text
    assert "skipped=1" in caplog.text
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd ~/hubwise-sync && pip install -e "../hubwise-py-core" && pytest tests/test_health_check.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'sync.health_check'`

- [ ] **Step 3: Write minimal implementation**

```python
# src/sync/health_check.py
"""Phase 1 gate probe: proves config -> state -> structured logging end to
end before sync_cw_sites_to_hudu (Phase 2) lands in this app. Reads a
non-secret probe value (set as a Key Vault reference in Bicep so the same
code path also proves Managed Identity -> Key Vault), and records it in
Table Storage keyed by this app's name — a no-op if the value hasn't
changed since the last tick.
"""
from __future__ import annotations

from hubwise_py_core.config import optional
from hubwise_py_core.logging import summary
from hubwise_py_core.state import ActionStateStore, InMemoryActionStateStore

PARTITION = "health-check"
CONDITION_KEY = "hubwise-sync"


def run_health_check_ping(
    state_store: "ActionStateStore | None" = None,
    env: dict | None = None,
) -> None:
    store = state_store if state_store is not None else InMemoryActionStateStore()
    probe_value = optional("HUBWISE_OPS_PROBE_VALUE", default="unset", env=env)

    previous = store.get_action(PARTITION, CONDITION_KEY)
    if previous == probe_value:
        summary("health_check_ping", read=1, written=0, skipped=1, errors=0)
        return

    store.record_action(PARTITION, CONDITION_KEY, probe_value)
    summary("health_check_ping", read=1, written=1, skipped=0, errors=0)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_health_check.py -v`
Expected: 3 passed

- [ ] **Step 5: Wire the real Table Storage store into `function_app.py`**

Update `function_app.py`'s `health_check_ping` to build the production
store from config when `state_store` is not injected:

```python
"""hubwise-sync Function App — thin entry point.

Wires triggers to business logic in src/sync/ and nothing more, per the
Azure-Hosted Service Standard §4. The health_check_ping timer exists to
prove the Phase 1 pipeline (OIDC deploy, Managed Identity -> Key Vault,
Table Storage write, structured logging visible in Log Analytics) before
sync_cw_sites_to_hudu (Phase 2) lands in this same app.
"""
from __future__ import annotations

import azure.functions as func

from hubwise_py_core.config import require
from hubwise_py_core.state import TableActionStateStore
from sync.health_check import run_health_check_ping

app = func.FunctionApp()


@app.timer_trigger(schedule="0 0 * * * *", arg_name="timer", run_on_startup=False,
                    use_monitor=True)
def health_check_ping(timer: func.TimerRequest) -> None:
    store = TableActionStateStore(
        account_url=require("STORAGE_TABLE_URL"),
        table_name="syncstate",
    )
    run_health_check_ping(state_store=store)
```

- [ ] **Step 6: Commit**

```bash
git add src/sync/health_check.py tests/test_health_check.py function_app.py
git commit -m "feat: add health_check_ping Phase 1 gate probe"
```

---

### Task 10: Bicep foundation — write and validate, DO NOT deploy

This task produces infrastructure-as-code only. **Do not run `az deployment sub create` for this task** — creating `rg-hubwise-automation`, a new storage account, and a live Function App is a real, billable, shared-subscription change and needs an explicit go/no-ahead from Scott before it runs, independent of whether the code is correct. Validate with `bicep build` / `bicep lint` only.

**Files:**
- Create: `C:\Users\swilson\hubwise-sync\infra\main.bicep`
- Create: `C:\Users\swilson\hubwise-sync\infra\modules\storage.bicep`
- Create: `C:\Users\swilson\hubwise-sync\infra\modules\sync-app.bicep`
- Create: `C:\Users\swilson\hubwise-sync\infra\modules\budget.bicep`
- Create: `C:\Users\swilson\hubwise-sync\infra\main.parameters.json`

**Interfaces:**
- Produces: a subscription-scoped deployment that creates `rg-hubwise-automation`, a storage account, a budget alert, and the `hubwise-sync` Flex Consumption Function App with system-assigned MI granted `Key Vault Secrets User` on the existing `hubwise-ops` vault and `Storage Table/Blob/Queue` data roles on its own storage account, with App Insights bound to the existing `hubwise-fwmon-law` Log Analytics workspace (runbook §4.2's explicit recommendation to reuse it).

- [ ] **Step 1: Write `infra/modules/storage.bicep`** (adapted from `hubwise-fwmon`'s `storage.bicep` pattern — Standard_LRS is sufficient here, no ZRS requirement since this app has no HA/multi-region need)

```bicep
// Storage account for hubwise-sync: Table Storage idempotency state +
// Functions deploy/runtime storage. Shared-key access disabled — all
// access is via the Function App's managed identity (identity-based
// connections in the app's siteConfig).
param prefix string
param location string
param tags object

var storageAccountName = take(toLower(replace('${prefix}${uniqueString(resourceGroup().id)}', '-', '')), 24)

resource sa 'Microsoft.Storage/storageAccounts@2023-05-01' = {
  name: storageAccountName
  location: location
  tags: tags
  sku: {
    name: 'Standard_LRS'
  }
  kind: 'StorageV2'
  properties: {
    minimumTlsVersion: 'TLS1_2'
    allowSharedKeyAccess: false
    allowBlobPublicAccess: false
  }
}

output storageAccountName string = sa.name
output tableEndpoint string = sa.properties.primaryEndpoints.table
output blobEndpoint string = sa.properties.primaryEndpoints.blob
output queueEndpoint string = sa.properties.primaryEndpoints.queue
```

- [ ] **Step 2: Write `infra/modules/sync-app.bicep`** (adapted from `hubwise-fwmon`'s `reconciler-app.bicep`, targeting the existing `hubwise-ops` vault and `hubwise-fwmon-law` workspace by resource ID rather than a locally-created one)

```bicep
// hubwise-sync Function App (Flex Consumption, Python 3.12).
// System-assigned managed identity with least-privilege RBAC:
//   - Key Vault Secrets User on the existing hubwise-ops vault
//   - Storage Table Data Contributor + Blob Data Owner + Queue Data
//     Contributor on this app's own storage account
// Storage uses identity-based connections (shared-key access disabled).
param prefix string
param location string
param tags object
param storageAccountName string
param tableEndpoint string
@description('Existing hubwise-ops Key Vault name (different resource group).')
param keyVaultName string
@description('Existing hubwise-ops Key Vault resource group.')
param keyVaultResourceGroup string
@description('Existing shared Log Analytics workspace resource id (hubwise-fwmon-law, per runbook 4.2).')
param lawId string
@description('Non-secret probe value the Phase 1 gate function records.')
param probeValue string = 'ok'

var appName = '${prefix}'
var planName = '${prefix}-plan'
var deployContainerName = 'app-package-sync'

// Built-in role definition IDs
var roleBlobOwner = 'b7e6dc6d-f1e8-4753-8033-0f276bb0955b'
var roleQueueContrib = '974c5e8b-45b9-4653-ba55-5f855dd0fb88'
var roleTableContrib = '0a9a7e1f-b9d0-4cc4-a60d-0319b160aaa3'
var roleKvSecretsUser = '4633458b-17de-408a-b874-0445c86b69e6'

resource sa 'Microsoft.Storage/storageAccounts@2023-05-01' existing = {
  name: storageAccountName
}

resource blobService 'Microsoft.Storage/storageAccounts/blobServices@2023-05-01' = {
  parent: sa
  name: 'default'
}
resource deployContainer 'Microsoft.Storage/storageAccounts/blobServices/containers@2023-05-01' = {
  parent: blobService
  name: deployContainerName
  properties: {
    publicAccess: 'None'
  }
}

resource appi 'Microsoft.Insights/components@2020-02-02' = {
  name: '${prefix}-ai'
  location: location
  kind: 'web'
  tags: tags
  properties: {
    Application_Type: 'web'
    WorkspaceResourceId: lawId
  }
}

resource plan 'Microsoft.Web/serverfarms@2024-04-01' = {
  name: planName
  location: location
  tags: tags
  sku: {
    name: 'FC1'
    tier: 'FlexConsumption'
  }
  kind: 'functionapp'
  properties: {
    reserved: true
  }
}

resource app 'Microsoft.Web/sites@2024-04-01' = {
  name: appName
  location: location
  kind: 'functionapp,linux'
  tags: tags
  identity: {
    type: 'SystemAssigned'
  }
  properties: {
    serverFarmId: plan.id
    httpsOnly: true
    functionAppConfig: {
      deployment: {
        storage: {
          type: 'blobContainer'
          value: '${sa.properties.primaryEndpoints.blob}${deployContainerName}'
          authentication: {
            type: 'SystemAssignedIdentity'
          }
        }
      }
      scaleAndConcurrency: {
        maximumInstanceCount: 40
        instanceMemoryMB: 2048
      }
      runtime: {
        name: 'python'
        version: '3.12'
      }
    }
    siteConfig: {
      appSettings: [
        {
          name: 'APPLICATIONINSIGHTS_CONNECTION_STRING'
          value: appi.properties.ConnectionString
        }
        {
          name: 'AzureWebJobsStorage__blobServiceUri'
          value: sa.properties.primaryEndpoints.blob
        }
        {
          name: 'AzureWebJobsStorage__queueServiceUri'
          value: sa.properties.primaryEndpoints.queue
        }
        {
          name: 'AzureWebJobsStorage__tableServiceUri'
          value: sa.properties.primaryEndpoints.table
        }
        {
          name: 'STORAGE_TABLE_URL'
          value: tableEndpoint
        }
        {
          name: 'DRY_RUN'
          value: '1'
        }
        {
          name: 'ALLOW_PROD'
          value: '0'
        }
        // Key Vault reference — proves Managed Identity -> hubwise-ops on
        // the Phase 1 gate. Not a secret; used only as a probe value.
        {
          name: 'HUBWISE_OPS_PROBE_VALUE'
          value: '@Microsoft.KeyVault(VaultName=${keyVaultName};SecretName=hubwise-sync-probe-value)'
        }
      ]
    }
  }
}

resource raBlob 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(sa.id, app.id, roleBlobOwner)
  scope: sa
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', roleBlobOwner)
    principalId: app.identity.principalId
    principalType: 'ServicePrincipal'
  }
}
resource raQueue 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(sa.id, app.id, roleQueueContrib)
  scope: sa
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', roleQueueContrib)
    principalId: app.identity.principalId
    principalType: 'ServicePrincipal'
  }
}
resource raTable 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(sa.id, app.id, roleTableContrib)
  scope: sa
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', roleTableContrib)
    principalId: app.identity.principalId
    principalType: 'ServicePrincipal'
  }
}

module kvRoleAssignment 'kv-role-assignment.bicep' = {
  name: 'sync-kv-role-assignment'
  scope: resourceGroup(keyVaultResourceGroup)
  params: {
    keyVaultName: keyVaultName
    principalId: app.identity.principalId
    roleDefinitionId: roleKvSecretsUser
  }
}

output principalId string = app.identity.principalId
output functionAppName string = app.name
output defaultHostName string = app.properties.defaultHostName
```

- [ ] **Step 3: Write `infra/modules/kv-role-assignment.bicep`** (a tiny cross-resource-group module — the KV lives in `rg-hubwise-secrets`, not `rg-hubwise-automation`, so its role assignment must be deployed at that RG's scope)

```bicep
// Grants a role on the existing hubwise-ops Key Vault, deployed at the
// vault's own resource group scope (it lives in rg-hubwise-secrets, not
// the automation RG this app's other resources are created in).
param keyVaultName string
param principalId string
param roleDefinitionId string

resource kv 'Microsoft.KeyVault/vaults@2023-07-01' existing = {
  name: keyVaultName
}

resource ra 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(kv.id, principalId, roleDefinitionId)
  scope: kv
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', roleDefinitionId)
    principalId: principalId
    principalType: 'ServicePrincipal'
  }
}
```

- [ ] **Step 4: Write `infra/modules/budget.bicep`** (runbook §4.4 — $50/mo tripwire)

```bicep
// $50/mo budget alert tripwire on the automation resource group (runbook
// §4.4 — Flex Consumption for these workloads should be trivially cheap;
// this alert exists to catch a misconfiguration, not to cap real spend).
param alertEmailAddress string

resource budget 'Microsoft.Consumption/budgets@2023-11-01' = {
  name: 'hubwise-automation-monthly-budget'
  properties: {
    category: 'Cost'
    amount: 50
    timeGrain: 'Monthly'
    timePeriod: {
      startDate: '2026-07-01'
    }
    notifications: {
      actual_GreaterThan_80_Percent: {
        enabled: true
        operator: 'GreaterThan'
        threshold: 80
        contactEmails: [
          alertEmailAddress
        ]
      }
    }
  }
}
```

- [ ] **Step 5: Write `infra/main.bicep`** (subscription-scoped, composes the modules)

```bicep
// =============================================================================
// hubwise-sync — Phase 1 foundation (subscription-scoped, one module per
// resource, following hubwise-fwmon's pattern exactly).
// Creates rg-hubwise-automation, a storage account, a budget alert, and the
// hubwise-sync Flex Consumption Function App with system-assigned MI
// granted least-privilege RBAC on its own storage and on the EXISTING
// hubwise-ops vault (rg-hubwise-secrets). App Insights binds to the
// EXISTING hubwise-fwmon-law workspace (runbook §4.2's recommendation).
//   az deployment sub create --location centralus --template-file main.bicep \
//      --parameters @main.parameters.json
// =============================================================================
targetScope = 'subscription'

@description('Naming prefix for all resources.')
param prefix string = 'hubwise-sync'

@description('Region for all resources (matches hubwise-ops vault region).')
param location string = 'centralus'

@description('Environment tag.')
param environment string = 'prod'

@description('Existing hubwise-ops Key Vault name.')
param keyVaultName string = 'hubwise-ops'

@description('Existing hubwise-ops Key Vault resource group.')
param keyVaultResourceGroup string = 'rg-hubwise-secrets'

@description('Existing shared Log Analytics workspace resource id (hubwise-fwmon-law).')
param lawId string

@description('Email address for the budget alert.')
param budgetAlertEmail string

var tags = {
  project: 'root-repo-modernization'
  app: 'hubwise-sync'
  environment: environment
  managedBy: 'bicep'
}

var rgName = 'rg-hubwise-automation'

resource rg 'Microsoft.Resources/resourceGroups@2024-03-01' = {
  name: rgName
  location: location
  tags: tags
}

module stg 'modules/storage.bicep' = {
  name: 'storage'
  scope: rg
  params: {
    prefix: prefix
    location: location
    tags: tags
  }
}

module syncApp 'modules/sync-app.bicep' = {
  name: 'sync-app'
  scope: rg
  params: {
    prefix: prefix
    location: location
    tags: tags
    storageAccountName: stg.outputs.storageAccountName
    tableEndpoint: stg.outputs.tableEndpoint
    keyVaultName: keyVaultName
    keyVaultResourceGroup: keyVaultResourceGroup
    lawId: lawId
  }
}

module budget 'modules/budget.bicep' = {
  name: 'budget'
  scope: rg
  params: {
    alertEmailAddress: budgetAlertEmail
  }
}

output resourceGroup string = rg.name
output storageAccountName string = stg.outputs.storageAccountName
output functionAppName string = syncApp.outputs.functionAppName
output principalId string = syncApp.outputs.principalId
```

- [ ] **Step 6: Write `infra/main.parameters.json`**

```json
{
  "$schema": "https://schema.management.azure.com/schemas/2019-04-01/deploymentParameters.json#",
  "contentVersion": "1.0.0.0",
  "parameters": {
    "lawId": {
      "value": "/subscriptions/5c43a7dd-b4fd-4660-b301-a5c5fd7738b2/resourceGroups/hubwise-fwmon-rg/providers/Microsoft.OperationalInsights/workspaces/hubwise-fwmon-law"
    },
    "budgetAlertEmail": {
      "value": "swilson@hubwisetech.com"
    }
  }
}
```

- [ ] **Step 7: Validate (build only — no deploy)**

Run: `cd ~/hubwise-sync/infra && az bicep build --file main.bicep`
Expected: compiles to `main.json` with no errors (a missing-module or type error will surface here before any deploy is attempted).

Run: `az bicep lint --file main.bicep`
Expected: no errors (warnings acceptable, review any that appear).

- [ ] **Step 8: Commit**

```bash
cd ~/hubwise-sync
git add infra/
git commit -m "feat: add Bicep foundation for hubwise-sync (not yet deployed)"
```

**STOP before deploying.** Confirm with Scott before running `az deployment sub create` — this creates real, billable Azure resources (new resource group, storage account, Function App) and grants RBAC on the shared `hubwise-ops` vault. It also requires the `hubwise-sync-probe-value` secret to exist in `hubwise-ops` first (create it manually or via the Cowork runbook §3 process — it's a non-secret placeholder like `"ok"`, but still lives in the vault per the KV-reference pattern used everywhere else).

---

### Task 11: Bare skeletons — `hubwise-procurement`, `hubwise-fw-lifecycle`

These two apps have no functions to build until Phase 4 (fw-lifecycle) and Phase 5 (procurement). Phase 1 only needs the repo shell so the Cowork side can create GitHub repos and OIDC federation against something.

**Files (per repo, so eight files total):**
- Create: `C:\Users\swilson\hubwise-procurement\.gitignore`
- Create: `C:\Users\swilson\hubwise-procurement\README.md`
- Create: `C:\Users\swilson\hubwise-fw-lifecycle\.gitignore`
- Create: `C:\Users\swilson\hubwise-fw-lifecycle\README.md`

- [ ] **Step 1: Scaffold `hubwise-procurement`**

```bash
mkdir -p ~/hubwise-procurement/src/procurement ~/hubwise-procurement/tests ~/hubwise-procurement/infra/modules ~/hubwise-procurement/scripts
cd ~/hubwise-procurement && git init -q && git branch -m main
```

`.gitignore`: identical content to `hubwise-sync`'s (Task 8, Step 1).

`README.md`:

```markdown
# hubwise-procurement

PO tracking timer + ConnectWise procurement/PO callback HTTP endpoints.
Part of the [Root Repo Modernization](../Root%20Repo%20Modernization/TRANSITION-PLAN.md)
project. Scaffolded in Phase 1; functions land in Phase 5 — see the
transition plan §5/§6 for scope and the migration schedule.

Depends on [`hubwise-py-core`](https://github.com/hubwisetech/hubwise-py-core).
```

```bash
git add .gitignore README.md
git commit -m "chore: scaffold hubwise-procurement repo shell (functions land in Phase 5)"
```

- [ ] **Step 2: Scaffold `hubwise-fw-lifecycle`**

```bash
mkdir -p ~/hubwise-fw-lifecycle/src/fw_lifecycle ~/hubwise-fw-lifecycle/tests ~/hubwise-fw-lifecycle/infra/modules ~/hubwise-fw-lifecycle/scripts
cd ~/hubwise-fw-lifecycle && git init -q && git branch -m main
```

`.gitignore`: identical content to `hubwise-sync`'s (Task 8, Step 1).

`README.md`:

```markdown
# hubwise-fw-lifecycle

NSM-orchestrated firewall fleet sync + the redesigned two-step firmware
upgrade pipeline (detect -> ticket -> human-gated manual run). Part of the
[Root Repo Modernization](../Root%20Repo%20Modernization/TRANSITION-PLAN.md)
project. Scaffolded in Phase 1; functions land in Phase 4 (fleet sync) and
Phase 6 (firmware redesign, D-9) — see the transition plan for scope.

Depends on [`hubwise-py-core`](https://github.com/hubwisetech/hubwise-py-core).
The only app in this project that can change a client firewall — see D-9
for the mandatory human-approval gate before any upgrade executes.
```

```bash
git add .gitignore README.md
git commit -m "chore: scaffold hubwise-fw-lifecycle repo shell (functions land in Phases 4 and 6)"
```

---

## Blocker note (report to Scott, do not attempt to resolve unilaterally)

The following are explicitly Cowork-runbook territory (`COWORK-RUNBOOK.md` §3, §4, §5) and this plan does not attempt them:

1. **GitHub repo creation** (`hubwisetech/hubwise-py-core`, `-sync`, `-procurement`, `-fw-lifecycle`) — runbook §4.6. Local repos in this plan have no remote until this happens.
2. **Entra OIDC federation** (per-repo app registration + federated credential) — runbook §4.7. `hubwise-sync`'s `ci-cd.yml` deploy job will fail on `azure/login@v2` until `AZURE_CLIENT_ID`/`AZURE_TENANT_ID`/`AZURE_SUBSCRIPTION_ID` repo secrets exist and the federated credential is scoped correctly.
3. **`rg-hubwise-automation` / storage account / Function App deployment** — Task 10 writes and validates the Bicep but stops short of `az deployment sub create`; needs Scott's explicit go-ahead per the safety note in that task.
4. **`hubwise-sync-probe-value` secret in `hubwise-ops`** — needed before the deployed `health_check_ping` function can resolve its Key Vault reference.
5. **NSM API coverage audit** (runbook §5.2) — not on this plan's critical path (no NSM-dependent function is built until Phase 4), but flagged as still open.

Once 1–4 are done, resume with: `az deployment sub create --location centralus --template-file infra/main.bicep --parameters @infra/main.parameters.json` from `hubwise-sync`, then push all four repos and let CI run the OIDC deploy — that satisfies the Phase 1 gate. Phase 2 (the `sync_cw_sites_to_hudu` pilot) starts immediately after in the same `hubwise-sync` repo.
