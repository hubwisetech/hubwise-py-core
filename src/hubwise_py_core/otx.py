"""AlienVault OTX client — threat-indicator export reads.

Fetches recently-modified indicators (IPv4/IPv6/domain) from the OTX export
API, following the ``next`` pagination cursor. Auth is the ``X-OTX-API-KEY``
header, sent per-request rather than stored on the session. Read-only — no
WriteGuard. Unlike the legacy job, TLS verification stays ON (never pass
verify=False), per the Outbound Integration Standard.
"""
from __future__ import annotations

from urllib.parse import quote

from .http import build_session

EXPORT_URL = "https://otx.alienvault.com/api/v1/indicators/export"
DEFAULT_TYPES = "IPv4,IPv6,domain"


class OTXClient:
    def __init__(self, api_key, session=None):
        self._session = session if session is not None else build_session()
        self._headers = {"X-OTX-API-KEY": api_key}

    def export_indicators(self, modified_since, types=DEFAULT_TYPES):
        """All indicators modified since ``modified_since`` (``yyyy-mm-dd``),
        following the ``next`` cursor. Returns the raw result dicts."""
        url = f"{EXPORT_URL}?types={quote(types)}&modified_since={quote(modified_since)}"
        out = []
        while url:
            resp = self._session.get(url, headers=self._headers)
            resp.raise_for_status()
            body = resp.json()
            out.extend(body.get("results") or [])
            url = body.get("next") or None
        return out
