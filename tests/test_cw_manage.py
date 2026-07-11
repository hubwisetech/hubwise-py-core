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


def test_list_contacts_with_types_filters_and_paginates():
    page1 = [
        {"id": 1, "firstName": "Amy", "lastName": "A", "inactiveFlag": False,
         "company": {"id": 100}, "types": [{"id": 14, "name": "HubWise Primary Contact"}]},
        {"id": 2, "firstName": "Bob", "lastName": "B", "inactiveFlag": False,
         "company": {"id": 100}, "types": [{"id": 3, "name": "End User"}]},
    ]
    page2 = [
        {"id": 3, "firstName": "Cy", "lastName": "C", "inactiveFlag": False,
         "company": {"id": 101}, "types": [{"id": 1, "name": "Approver"}]},
        {"id": 4, "firstName": "Di", "lastName": "D", "inactiveFlag": True,
         "company": {"id": 101}, "types": [{"id": 14, "name": "HubWise Primary Contact"}]},
    ]
    session = FakeSession([
        ("/company/contacts", lambda p: int(p.get("page", 1)) == 1, page1),
        ("/company/contacts", lambda p: int(p.get("page", 1)) == 2, page2),
        ("/company/contacts", lambda p: int(p.get("page", 1)) >= 3, []),
    ])
    got = _client(session, page_size=2).list_contacts_with_types(
        {"HubWise Primary Contact", "Approver"})
    # Amy (primary) + Cy (approver); Bob (End User) dropped; Di (inactive) dropped
    assert [c["id"] for c in got] == [1, 3]


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


def test_list_tickets_by_ids_uses_in_condition():
    session = FakeSession([
        ("/service/tickets", None,
         [{"id": 101, "owner": {"name": "Amy Adams"}},
          {"id": 102, "owner": {"name": "Bob Brown"}}]),
    ])
    tickets = _client(session).list_tickets_by_ids([101, 102])
    assert {t["id"] for t in tickets} == {101, 102}
    url, params = session.calls[0]
    assert url.endswith("/service/tickets")
    assert params["conditions"] == "id in (101,102)"


def test_list_tickets_by_ids_chunks_large_id_sets():
    session = FakeSession([("/service/tickets", None, [{"id": 1}])])
    ids = list(range(1, 121))  # 120 ids -> 3 chunks of 50
    _client(session).list_tickets_by_ids(ids, chunk_size=50)
    conditions = [p["conditions"] for _, p in session.calls]
    assert len(conditions) == 3
    assert conditions[0].startswith("id in (1,")
    assert conditions[2].endswith(",120)")


def test_list_tickets_by_ids_empty_input_makes_no_calls():
    session = FakeSession([])
    assert _client(session).list_tickets_by_ids([]) == []
    assert session.calls == []


# ---- config reads + gated writes (#7 / #14 shared) ----
from hubwise_py_core.guards import WriteGuard  # noqa: E402


class WriteFakeSession:
    def __init__(self, get_pages=None):
        self.headers = {}
        self.calls = []  # (method, url, params, json)
        self._get_pages = get_pages or {}

    def get(self, url, params=None, **kwargs):
        self.calls.append(("GET", url, dict(params or {}), None))
        page = int((params or {}).get("page", 1))
        return FakeResponse(self._get_pages.get(page, []))

    def post(self, url, json=None, **kwargs):
        self.calls.append(("POST", url, None, json))
        return FakeResponse({"id": 555, "name": (json or {}).get("name")})

    def patch(self, url, json=None, **kwargs):
        self.calls.append(("PATCH", url, None, json))
        return FakeResponse({"id": 1})


def _wclient(session, guard):
    return CWManageClient(site="api-na.myconnectwise.net", company="hubwise",
                          public_key="pub", private_key="priv", client_id="cid",
                          session=session, guard=guard, page_size=100)


def _open():
    return WriteGuard(env={"DRY_RUN": "0", "ALLOW_PROD": "1"})


def test_list_configurations_paginates_and_passes_conditions():
    session = WriteFakeSession(get_pages={1: [{"id": 1}] * 100, 2: [{"id": 2}]})
    cfgs = _wclient(session, WriteGuard(env={})).list_configurations(
        conditions='type/name="Remote Access"')
    assert [c["id"] for c in cfgs] == [1] * 100 + [2]
    first = [c for c in session.calls if c[0] == "GET"][0]
    assert first[1].endswith("/company/configurations")
    assert first[2].get("conditions") == 'type/name="Remote Access"'


def test_create_configuration_suppressed_under_default_guard():
    session = WriteFakeSession()
    result = _wclient(session, WriteGuard(env={})).create_configuration({"name": "X"})
    assert result is None
    assert not any(c[0] == "POST" for c in session.calls)


def test_create_configuration_issued_under_open_guard():
    session = WriteFakeSession()
    payload = {"name": "Acme HQ RDS - SVR1", "type": {"name": "Remote Access"}}
    result = _wclient(session, _open()).create_configuration(payload)
    assert result is not None
    post = [c for c in session.calls if c[0] == "POST"][0]
    assert post[1].endswith("/company/configurations")
    assert post[3] == payload


def test_update_configuration_suppressed_under_default_guard():
    session = WriteFakeSession()
    result = _wclient(session, WriteGuard(env={})).update_configuration(
        7, [{"op": "replace", "path": "status", "value": {"name": "Active"}}])
    assert result is None
    assert not any(c[0] == "PATCH" for c in session.calls)


def test_update_configuration_issued_under_open_guard():
    session = WriteFakeSession()
    ops = [{"op": "replace", "path": "name", "value": "new"}]
    _wclient(session, _open()).update_configuration(7, ops)
    patch = [c for c in session.calls if c[0] == "PATCH"][0]
    assert patch[1].endswith("/company/configurations/7")
    assert patch[3] == ops


def test_default_client_without_guard_suppresses_writes():
    # existing read-only callers construct without a guard; writes must not fire
    session = WriteFakeSession()
    client = CWManageClient(site="s", company="c", public_key="p",
                            private_key="pk", client_id="ci", session=session)
    assert client.create_configuration({"name": "X"}) is None
    assert not any(c[0] == "POST" for c in session.calls)


# ---- gated ticket create + note writes ----

class _Resp:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        pass

    def json(self):
        return self._payload


class _TicketSession:
    """Records POSTs; returns a canned CW body."""
    def __init__(self):
        self.headers = {}
        self.posts = []

    def post(self, url, json=None):
        self.posts.append((url, json))
        return _Resp({"id": 4242, **(json or {})})


def _ticket_client(session, allow=True):
    from hubwise_py_core.guards import WriteGuard
    env = {"DRY_RUN": "0", "ALLOW_PROD": "1"} if allow else {}
    guard = WriteGuard(env=env)
    return CWManageClient(site="cw.example", company="hwti", public_key="pk",
                          private_key="sk", client_id="cid",
                          session=session, guard=guard)


def test_create_ticket_posts_and_returns_body():
    session = _TicketSession()
    client = _ticket_client(session)
    result = client.create_ticket(summary="New GA firmware for 3 models",
                                  board_name="Internal", company_id=250,
                                  initial_description="details")
    url, body = session.posts[0]
    assert url.endswith("/service/tickets")
    assert body["summary"] == "New GA firmware for 3 models"
    assert body["board"] == {"name": "Internal"}
    assert body["company"] == {"id": 250}
    assert body["initialDescription"] == "details"
    assert result["id"] == 4242


def test_create_ticket_truncates_summary_to_100_chars():
    session = _TicketSession()
    client = _ticket_client(session)
    client.create_ticket(summary="x" * 150, board_name="Internal", company_id=250)
    _, body = session.posts[0]
    assert len(body["summary"]) == 100


def test_create_ticket_suppressed_by_guard():
    session = _TicketSession()
    client = _ticket_client(session, allow=False)
    assert client.create_ticket(summary="s", board_name="b", company_id=1) is None
    assert session.posts == []


def test_add_ticket_note_posts_and_returns_body():
    session = _TicketSession()
    client = _ticket_client(session)
    result = client.add_ticket_note(4242, "wave 0 verified", internal=True)
    url, body = session.posts[0]
    assert url.endswith("/service/tickets/4242/notes")
    assert body == {"text": "wave 0 verified", "internalAnalysisFlag": True,
                    "detailDescriptionFlag": False}
    assert result["id"] == 4242


def test_add_ticket_note_external_uses_detail_description():
    session = _TicketSession()
    client = _ticket_client(session)
    client.add_ticket_note(4242, "visible to client", internal=False)
    _, body = session.posts[0]
    assert body == {"text": "visible to client", "internalAnalysisFlag": False,
                    "detailDescriptionFlag": True}


def test_add_ticket_note_suppressed_by_guard():
    session = _TicketSession()
    client = _ticket_client(session, allow=False)
    assert client.add_ticket_note(4242, "t") is None
    assert session.posts == []
