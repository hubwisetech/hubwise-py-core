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
