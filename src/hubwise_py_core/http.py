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
