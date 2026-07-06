"""ConnectWise Manage REST client — read-only companies + sites.

Replaces the read half of the legacy HWTI-CWM.psm1. Auth is the ConnectWise
scheme: ``Basic base64("<company>+<public>:<private>")`` plus a ``clientId``
header. All I/O goes through an injectable ``requests``-style session so the
client is unit-testable without a network.

Read-only: no WriteGuard needed here (this client never writes to CW).
"""
from __future__ import annotations

import base64

from .guards import WriteGuard
from .http import build_session

API_BASE_PATH = "/v4_6_release/apis/3.0"
SITE_CODE_FIELD_ID = 15  # "HubWise Site Code" custom field (verified live 2026-07-06)
_PAGE_SIZE = 100


class CWManageClient:
    def __init__(self, site, company, public_key, private_key, client_id,
                 session=None, page_size=_PAGE_SIZE, guard=None):
        self._base = f"https://{site}{API_BASE_PATH}"
        self._page_size = page_size
        # Writes are gated; reads never touch the guard. A missing guard
        # defaults to a suppressing one so read-only callers stay safe.
        self._guard = guard if guard is not None else WriteGuard()
        self._session = session if session is not None else build_session()
        raw = f"{company}+{public_key}:{private_key}"
        self._session.headers.update({
            "Authorization": "Basic " + base64.b64encode(raw.encode()).decode(),
            "clientId": client_id,
            "Accept": "application/json",
        })

    def _get(self, path, params=None):
        resp = self._session.get(f"{self._base}{path}", params=params)
        resp.raise_for_status()
        return resp.json()

    def list_client_companies(self):
        """All companies carrying the 'Client' type, following pagination.

        The CW API cannot server-filter on ``types/name``, so we page through
        companies and filter client-side (matching the legacy job's behavior).
        """
        out = []
        page = 1
        while True:
            batch = self._get("/company/companies",
                              params={"page": page, "pageSize": self._page_size})
            if not batch:
                break
            for company in batch:
                # Never sync a deleted CW company (can still carry type=Client).
                if company.get("deletedFlag"):
                    continue
                if any(t.get("name") == "Client" for t in company.get("types", [])):
                    out.append(company)
            if len(batch) < self._page_size:
                break
            page += 1
        return out

    def list_contacts_with_types(self, type_names):
        """Active contacts whose type set intersects ``type_names``.

        Paginates /company/contacts and filters client-side (CW can't
        server-filter on types/name). Excludes inactive contacts.
        """
        wanted = set(type_names)
        out = []
        page = 1
        while True:
            batch = self._get("/company/contacts",
                              params={"page": page, "pageSize": self._page_size})
            if not batch:
                break
            for contact in batch:
                if contact.get("inactiveFlag", False):
                    continue
                if wanted & {t.get("name") for t in contact.get("types", [])}:
                    out.append(contact)
            if len(batch) < self._page_size:
                break
            page += 1
        return out

    def list_tickets_by_ids(self, ticket_ids, chunk_size=50):
        """Service tickets for the given ids, fetched in ``id in (…)``
        condition chunks so arbitrarily large id sets stay within CW's
        URL/condition limits."""
        ids = list(ticket_ids)
        out = []
        for i in range(0, len(ids), chunk_size):
            chunk = ids[i:i + chunk_size]
            out.extend(self._get(
                "/service/tickets",
                params={"conditions": f"id in ({','.join(str(t) for t in chunk)})",
                        "pageSize": self._page_size}))
        return out

    def list_configurations(self, conditions=None):
        """All company configurations (optionally narrowed by a CW
        ``conditions`` string, e.g. ``type/name="Remote Access"``),
        following pagination. Read-only."""
        out = []
        page = 1
        while True:
            params = {"page": page, "pageSize": self._page_size}
            if conditions:
                params["conditions"] = conditions
            batch = self._get("/company/configurations", params=params)
            if not batch:
                break
            out.extend(batch)
            if len(batch) < self._page_size:
                break
            page += 1
        return out

    def create_configuration(self, payload):
        """Gated POST /company/configurations. ``payload`` is the full CW
        configuration body (name/type/company/site/status/questions).
        Returns the created config, or None when suppressed."""
        if not self._guard.check_write(
                f"create CW configuration '{payload.get('name')}'"):
            return None
        resp = self._session.post(f"{self._base}/company/configurations", json=payload)
        resp.raise_for_status()
        return resp.json()

    def update_configuration(self, config_id, patch_ops):
        """Gated PATCH /company/configurations/{id} with a JSON-Patch op
        list. Returns the updated config, or None when suppressed."""
        if not self._guard.check_write(f"update CW configuration {config_id}"):
            return None
        resp = self._session.patch(
            f"{self._base}/company/configurations/{config_id}", json=patch_ops)
        resp.raise_for_status()
        return resp.json()

    def list_active_sites(self, company_id):
        """Active (non-inactive) sites for a company."""
        sites = self._get(f"/company/companies/{company_id}/sites",
                          params={"pageSize": self._page_size})
        return [s for s in sites if not s.get("inactiveFlag", False)]

    @staticmethod
    def site_code(site):
        """The 'HubWise Site Code' custom-field value (id 15), or '' if unset."""
        for field in site.get("customFields", []):
            if field.get("id") == SITE_CODE_FIELD_ID:
                return field.get("value") or ""
        return ""
