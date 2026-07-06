import base64

from hubwise_py_core.cw_manage import CWManageClient


class FakeResponse:
    def __init__(self, json_data, status=200):
        self._json = json_data
        self.status_code = status

    def json(self):
        return self._json

    def raise_for_status(self):
        if self.status_code >= 400:
            raise AssertionError(f"HTTP {self.status_code}")


class FakeSession:
    """Records GET calls; serves canned responses keyed by a matcher function."""

    def __init__(self, pages):
        # pages: list of (path_contains, params_predicate, json) tuples, matched in order
        self._pages = pages
        self.calls = []
        self.headers = {}

    def get(self, url, params=None, **kwargs):
        self.calls.append((url, dict(params or {})))
        for contains, pred, data in self._pages:
            if contains in url and (pred is None or pred(params or {})):
                return FakeResponse(data)
        return FakeResponse([])


def _client(session, page_size=100):
    return CWManageClient(
        site="api-na.myconnectwise.net",
        company="hubwise",
        public_key="pub",
        private_key="priv",
        client_id="cid",
        session=session,
        page_size=page_size,
    )


def test_auth_and_client_headers_set():
    session = FakeSession([])
    _client(session)
    expected = "Basic " + base64.b64encode(b"hubwise+pub:priv").decode()
    assert session_headers(session).get("Authorization") == expected
    assert session_headers(session).get("clientId") == "cid"


def session_headers(session):
    # CWManageClient stores headers on the session it was given
    return getattr(session, "headers", {})


def test_list_client_companies_filters_non_client_and_paginates():
    page1 = [
        {"id": 1, "identifier": "ACME", "name": "Acme", "types": [{"id": 1, "name": "Client"}]},
        {"id": 2, "identifier": "VEND", "name": "Vendor Co",
         "types": [{"id": 6, "name": "Vendor"}]},
    ]
    page2 = [
        {"id": 3, "identifier": "GLOB", "name": "Globex",
         "types": [{"id": 6, "name": "Vendor"}, {"id": 1, "name": "Client"}]},
    ]
    session = FakeSession([
        ("/company/companies", lambda p: int(p.get("page", 1)) == 1, page1),
        ("/company/companies", lambda p: int(p.get("page", 1)) == 2, page2),
        ("/company/companies", lambda p: int(p.get("page", 1)) >= 3, []),
    ])
    companies = _client(session, page_size=2).list_client_companies()
    ids = [c["id"] for c in companies]
    assert ids == [1, 3]  # Acme + Globex (has Client among types); Vendor Co dropped


def test_list_client_companies_excludes_deleted():
    # A deleted CW company must never be synced, even if it still carries the
    # Client type (e.g. Tetrad Property Group, deleted 2022 but type=Client).
    page = [
        {"id": 1, "identifier": "ACME", "name": "Acme",
         "types": [{"id": 1, "name": "Client"}], "deletedFlag": False},
        {"id": 2, "identifier": "TPGC", "name": "Tetrad Property Group",
         "types": [{"id": 1, "name": "Client"}], "deletedFlag": True},
    ]
    session = FakeSession([("/company/companies", None, page)])
    companies = _client(session).list_client_companies()
    assert [c["id"] for c in companies] == [1]  # deleted Tetrad dropped


def test_list_active_sites_drops_inactive():
    sites = [
        {"id": 10, "name": "OMA1", "inactiveFlag": False},
        {"id": 11, "name": "OLD", "inactiveFlag": True},
        {"id": 12, "name": "OMA2", "inactiveFlag": False},
    ]
    session = FakeSession([("/company/companies/250/sites", None, sites)])
    active = _client(session).list_active_sites(250)
    assert [s["id"] for s in active] == [10, 12]


def test_site_code_reads_custom_field_15():
    site = {"id": 12, "name": "OMA2", "customFields": [
        {"id": 15, "caption": "HubWise Site Code", "value": "OMA2"},
        {"id": 19, "caption": "Is CRE Protect", "value": None},
    ]}
    assert CWManageClient.site_code(site) == "OMA2"


def test_site_code_empty_when_null_or_absent():
    assert CWManageClient.site_code({"id": 1, "customFields": [{"id": 15, "value": None}]}) == ""
    assert CWManageClient.site_code({"id": 1, "customFields": []}) == ""
    assert CWManageClient.site_code({"id": 1}) == ""
