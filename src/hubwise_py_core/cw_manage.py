"""ConnectWise Manage REST client — read-only companies + sites.

Replaces the read half of the legacy HWTI-CWM.psm1. Auth is the ConnectWise
scheme: ``Basic base64("<company>+<public>:<private>")`` plus a ``clientId``
header. All I/O goes through an injectable ``requests``-style session so the
client is unit-testable without a network.

Read-only: no WriteGuard needed here (this client never writes to CW).
"""
from __future__ import annotations

import base64

from .http import build_session

API_BASE_PATH = "/v4_6_release/apis/3.0"
SITE_CODE_FIELD_ID = 15  # "HubWise Site Code" custom field (verified live 2026-07-06)
_PAGE_SIZE = 100


class CWManageClient:
    def __init__(self, site, company, public_key, private_key, client_id,
                 session=None, page_size=_PAGE_SIZE):
        self._base = f"https://{site}{API_BASE_PATH}"
        self._page_size = page_size
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
