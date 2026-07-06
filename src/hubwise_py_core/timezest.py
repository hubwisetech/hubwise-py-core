"""TimeZest REST client — scheduling-request reads only.

Auth: ``Authorization: Bearer <api token>``. Windowed reads use a TQL filter
on ``scheduling_request.created_at`` (epoch seconds) and follow the API's
``next_page`` cursor, which the live service has been observed returning in
several shapes (absolute URL, bare query string) — both are resolved here.
Rows are also window-filtered client-side and pagination stops early once a
page reaches data older than the window, matching the legacy job's guards.

Read-only: no WriteGuard needed (this client never writes to TimeZest).
"""
from __future__ import annotations

from urllib.parse import quote

from .http import build_session

ENDPOINT = "https://api.timezest.com/v1/scheduling_requests"


class TimeZestClient:
    def __init__(self, api_token, session=None, endpoint=ENDPOINT):
        self._endpoint = endpoint
        self._session = session if session is not None else build_session()
        self._headers = {"Authorization": f"Bearer {api_token}"}

    def _resolve_next(self, next_page):
        if next_page.startswith("http"):
            return next_page
        return self._endpoint + "?" + next_page.lstrip("?=/")

    def list_scheduling_requests(self, from_epoch, to_epoch):
        """Scheduling requests created within [from_epoch, to_epoch]."""
        tql = (f"scheduling_request.created_at GTE {from_epoch} "
               f"AND scheduling_request.created_at LTE {to_epoch}")
        url = f"{self._endpoint}?tql={quote(tql)}"
        out = []
        while url:
            resp = self._session.get(url, headers=self._headers)
            resp.raise_for_status()
            body = resp.json()
            batch = body.get("data") or []
            if not batch:
                break
            out.extend(r for r in batch
                       if from_epoch <= r.get("created_at", 0) <= to_epoch)
            if any(r.get("created_at", 0) < from_epoch for r in batch):
                break  # page reached data older than the window
            next_page = body.get("next_page")
            url = self._resolve_next(next_page) if next_page else None
        return out
