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
_PAGE_SIZE = 100


class HuduClient:
    def __init__(self, base_url, api_key, guard: WriteGuard, session=None, page_size=_PAGE_SIZE):
        self._base = base_url.rstrip("/") + API_PREFIX
        self._guard = guard
        self._page_size = page_size
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
        """All assets for a company in one asset layout, following pagination.

        Uses the TOP-LEVEL ``/assets`` endpoint with ``company_id`` +
        ``asset_layout_id``. The nested ``/companies/{id}/assets`` endpoint
        silently ignores ``asset_layout_id`` and returns every layout's
        assets — which would make a site-sync archive all non-site assets.
        """
        out = []
        page = 1
        while True:
            resp = self._session.get(
                f"{self._base}/assets",
                params={"company_id": company_id, "asset_layout_id": layout_id,
                        "page": page, "page_size": self._page_size},
            )
            resp.raise_for_status()
            batch = resp.json().get("assets", [])
            if not batch:
                break
            out.extend(batch)
            if len(batch) < self._page_size:
                break
            page += 1
        return out

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

    def upsert_magic_dash(self, title, company_name, message, content,
                          shade=None, icon=None):
        """Create/update a MagicDash (upsert by title + company_name).

        POST /api/v1/magic_dash is idempotent on (title, company_name), so this
        is naturally a reconcile-to-desired-state write. Gated; returns None
        when suppressed.
        """
        if not self._guard.check_write(f"upsert MagicDash '{title}' for '{company_name}'"):
            return None
        body = {"title": title, "company_name": company_name,
                "message": message, "content": content}
        if shade is not None:
            body["shade"] = shade
        if icon is not None:
            body["icon"] = icon
        resp = self._session.post(f"{self._base}/magic_dash", json=body)
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
