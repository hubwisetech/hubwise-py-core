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
