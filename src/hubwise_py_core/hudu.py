"""Hudu REST client — companies + assets (create/update/archive).

Covers the subset the CW-sites sync needs: resolve a company by exact name,
list a company's assets in a layout, create/update a site asset, and
archive/unarchive. Every write is gated by a ``WriteGuard`` — under the
default DRY_RUN it issues no HTTP and returns None/False, so a dry-run pass
resolves everything and logs intended actions without touching Hudu.

Auth: Hudu's ``x-api-key`` header. I/O via an injectable session.
"""
from __future__ import annotations

from .guards import WriteGuard
from .http import build_session

API_PREFIX = "/api/v1"


class HuduClient:
    def __init__(self, base_url, api_key, guard: WriteGuard, session=None):
        self._base = base_url.rstrip("/") + API_PREFIX
        self._guard = guard
        self._session = session if session is not None else build_session()
        self._session.headers.update({"x-api-key": api_key, "Accept": "application/json"})

    # ---- reads ----
    def find_company_id(self, name):
        """Return the id of the company whose name exactly matches, or None.

        None on no match *or* ambiguous (multiple exact matches) — an
        ambiguous company mapping must never drive blind writes.
        """
        resp = self._session.get(f"{self._base}/companies", params={"name": name})
        resp.raise_for_status()
        matches = [c for c in resp.json().get("companies", []) if c.get("name") == name]
        return matches[0]["id"] if len(matches) == 1 else None

    def list_assets(self, company_id, layout_id):
        resp = self._session.get(
            f"{self._base}/companies/{company_id}/assets",
            params={"asset_layout_id": layout_id},
        )
        resp.raise_for_status()
        return resp.json().get("assets", [])

    # ---- gated writes ----
    def create_asset(self, company_id, layout_id, name, fields):
        if not self._guard.check_write(f"create Hudu asset '{name}' (company {company_id})"):
            return None
        body = {"asset": {"name": name, "asset_layout_id": layout_id,
                          "custom_fields": [fields]}}
        resp = self._session.post(f"{self._base}/companies/{company_id}/assets", json=body)
        resp.raise_for_status()
        return resp.json()

    def update_asset(self, company_id, asset_id, layout_id, name, fields):
        if not self._guard.check_write(
                f"update Hudu asset {asset_id} '{name}' (company {company_id})"):
            return None
        body = {"asset": {"name": name, "asset_layout_id": layout_id,
                          "custom_fields": [fields]}}
        resp = self._session.put(
            f"{self._base}/companies/{company_id}/assets/{asset_id}", json=body)
        resp.raise_for_status()
        return resp.json()

    def set_archived(self, company_id, asset_id, archived: bool):
        """Archive (True) or unarchive (False) an asset. Returns True if the
        write was issued, False if suppressed by the guard.
        """
        verb = "archive" if archived else "unarchive"
        if not self._guard.check_write(f"{verb} Hudu asset {asset_id} (company {company_id})"):
            return False
        resp = self._session.put(
            f"{self._base}/companies/{company_id}/assets/{asset_id}/{verb}")
        resp.raise_for_status()
        return True
