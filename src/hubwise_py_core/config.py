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
