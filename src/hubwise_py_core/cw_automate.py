"""ConnectWise Automate (RMM) REST client — group/computer reads only.

Auth: ``POST /cwa/api/v1/apitoken`` with a ``ClientId`` header and a
``{Username, Password}`` body returns an ``AccessToken`` bearer, sent
per-request rather than stored in the session's default headers so the
credential surface stays small. Endpoint/payload shapes mirror the legacy
job's transport (`CONNECTWISE-Connect_to_Automate_API.ps1`). Read-only —
no WriteGuard.
"""
from __future__ import annotations

from .http import build_session


class CWAutomateClient:
    def __init__(self, server, client_id, username, password, session=None):
        self._base = f"https://{server.rstrip('/')}/cwa/api/v1"
        self._client_id = client_id
        self._username = username
        self._password = password
        self._session = session if session is not None else build_session()
        self._token = None

    def _headers(self):
        if self._token is None:
            resp = self._session.post(
                f"{self._base}/apitoken",
                headers={"ClientId": self._client_id},
                json={"Username": self._username, "Password": self._password},
            )
            resp.raise_for_status()
            self._token = resp.json()["AccessToken"]
        return {"ClientId": self._client_id, "Authorization": f"Bearer {self._token}"}

    def list_group_computers(self, group_name):
        """Computers in the CW Automate group whose name contains
        ``group_name`` (with ``expand=computers``), flattened across any
        groups the condition matches. Apostrophes are doubled for the
        Automate query-condition string."""
        escaped = group_name.replace("'", "''")
        resp = self._session.get(
            f"{self._base}/groups",
            headers=self._headers(),
            params={"condition": f"name contains '{escaped}'", "expand": "computers"},
        )
        resp.raise_for_status()
        data = resp.json()
        groups = data if isinstance(data, list) else [data]
        out = []
        for group in groups:
            # CW Automate returns PascalCase fields ("Computers"); tolerate
            # lowercase too for robustness.
            out.extend(group.get("Computers") or group.get("computers") or [])
        return out
