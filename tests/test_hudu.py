from hubwise_py_core.guards import WriteGuard
from hubwise_py_core.hudu import HuduClient


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
    def __init__(self, get_map=None):
        self.headers = {}
        self._get_map = get_map or {}
        self.calls = []  # (method, url, params, json)

    def get(self, url, params=None, **kwargs):
        self.calls.append(("GET", url, dict(params or {}), None))
        for contains, data in self._get_map.items():
            if contains in url:
                return FakeResponse(data)
        return FakeResponse({})

    def post(self, url, json=None, **kwargs):
        self.calls.append(("POST", url, {}, json))
        return FakeResponse({"asset": {"id": 999, "name": (json or {}).get("name")}})

    def put(self, url, json=None, **kwargs):
        self.calls.append(("PUT", url, {}, json))
        return FakeResponse({"asset": {"id": 1, "name": (json or {}).get("name")}})


def _open_guard():
    return WriteGuard(env={"DRY_RUN": "0", "ALLOW_PROD": "1"})


def _client(session, guard=None):
    return HuduClient(base_url="https://hudu.example.com", api_key="key",
                      guard=guard or WriteGuard(env={}), session=session)


def test_api_key_header_set():
    session = FakeSession()
    _client(session)
    assert session.headers.get("x-api-key") == "key"


def test_find_company_id_exact_match():
    session = FakeSession({"/companies": {"companies": [
        {"id": 7, "name": "Acme"}, {"id": 8, "name": "Acme Subsidiary"}]}})
    assert _client(session).find_company_id("Acme") == 7


def test_find_company_id_none_when_no_match():
    session = FakeSession({"/companies": {"companies": [{"id": 8, "name": "Other"}]}})
    assert _client(session).find_company_id("Acme") is None


def test_find_company_id_none_when_ambiguous():
    session = FakeSession({"/companies": {"companies": [
        {"id": 7, "name": "Acme"}, {"id": 9, "name": "Acme"}]}})
    assert _client(session).find_company_id("Acme") is None


def test_list_assets_uses_layout_filtering_endpoint():
    # Regression: the nested /companies/{id}/assets endpoint IGNORES
    # asset_layout_id and returns ALL layers' assets. Must use the top-level
    # /assets endpoint with company_id + asset_layout_id, which filters.
    session = FakeSession({"/assets": {"assets": [{"id": 1, "name": "OMA1", "archived": False}]}})
    _client(session).list_assets(company_id=7, layout_id=19)
    get_calls = [c for c in session.calls if c[0] == "GET"]
    assert len(get_calls) >= 1
    url, params = get_calls[0][1], get_calls[0][2]
    assert url.endswith("/assets")  # NOT /companies/7/assets
    assert "/companies/" not in url
    assert params.get("company_id") == 7
    assert params.get("asset_layout_id") == 19


def test_list_assets_paginates():
    class PagingSession(FakeSession):
        def get(self, url, params=None, **kwargs):
            self.calls.append(("GET", url, dict(params or {}), None))
            page = int((params or {}).get("page", 1))
            data = {1: [{"id": 1, "name": "A"}], 2: [{"id": 2, "name": "B"}]}.get(page, [])
            return FakeResponse({"assets": data})

    session = PagingSession()
    assets = HuduClient(base_url="https://h.example.com", api_key="k",
                        guard=WriteGuard(env={}), session=session,
                        page_size=1).list_assets(company_id=7, layout_id=19)
    assert [a["id"] for a in assets] == [1, 2]


def test_create_asset_suppressed_under_default_guard():
    session = FakeSession()
    result = _client(session).create_asset(7, 19, "OMA1", {"HubWise_Site_Code": "OMA1"})
    assert result is None
    assert not any(c[0] == "POST" for c in session.calls)  # no write issued


def test_create_asset_issued_under_open_guard():
    session = FakeSession()
    result = _client(session, guard=_open_guard()).create_asset(
        7, 19, "OMA1", {"HubWise_Site_Code": "OMA1"})
    assert result is not None
    post = [c for c in session.calls if c[0] == "POST"]
    assert len(post) == 1
    assert "/companies/7/assets" in post[0][1]
    assert post[0][3]["asset"]["name"] == "OMA1"


def test_update_asset_suppressed_under_default_guard():
    session = FakeSession()
    result = _client(session).update_asset(7, 1, 19, "OMA1", {})
    assert result is None
    assert not any(c[0] == "PUT" for c in session.calls)


def test_update_asset_issued_under_open_guard():
    session = FakeSession()
    _client(session, guard=_open_guard()).update_asset(7, 1, 19, "OMA1", {"Phone_Number": "402"})
    put = [c for c in session.calls if c[0] == "PUT"]
    assert len(put) == 1 and "/companies/7/assets/1" in put[0][1]


def test_set_archived_true_hits_archive_path_when_allowed():
    session = FakeSession()
    ok = _client(session, guard=_open_guard()).set_archived(7, 1, True)
    assert ok is True
    put = [c for c in session.calls if c[0] == "PUT"]
    assert len(put) == 1 and put[0][1].endswith("/assets/1/archive")


def test_set_archived_false_hits_unarchive_path_when_allowed():
    session = FakeSession()
    _client(session, guard=_open_guard()).set_archived(7, 1, False)
    put = [c for c in session.calls if c[0] == "PUT"]
    assert len(put) == 1 and put[0][1].endswith("/assets/1/unarchive")


def test_set_archived_suppressed_under_default_guard():
    session = FakeSession()
    ok = _client(session).set_archived(7, 1, True)
    assert ok is False
    assert not any(c[0] == "PUT" for c in session.calls)


def test_upsert_magic_dash_issued_under_open_guard():
    session = FakeSession()
    result = _client(session, guard=_open_guard()).upsert_magic_dash(
        title="Primary Contact and Approvers", company_name="Acme",
        message="Primary: Amy A", content="<table></table>", shade="success",
        icon="fas fa-user-tie")
    assert result is not None
    post = [c for c in session.calls if c[0] == "POST"]
    assert len(post) == 1 and post[0][1].endswith("/magic_dash")
    body = post[0][3]
    assert body["title"] == "Primary Contact and Approvers"
    assert body["company_name"] == "Acme"
    assert body["message"] == "Primary: Amy A"
    assert body["content"] == "<table></table>"
    assert body["shade"] == "success" and body["icon"] == "fas fa-user-tie"


def test_upsert_magic_dash_suppressed_under_default_guard():
    session = FakeSession()
    result = _client(session).upsert_magic_dash(
        title="T", company_name="Acme", message="m", content="c")
    assert result is None
    assert not any(c[0] == "POST" for c in session.calls)


def test_find_article_id_exact_match():
    session = FakeSession({"/articles": {"articles": [
        {"id": 42, "name": "MSP 360 Backup Report"},
        {"id": 43, "name": "MSP 360 Backup Report (old)"}]}})
    assert _client(session).find_article_id("MSP 360 Backup Report") == 42


def test_find_article_id_none_when_no_match_or_ambiguous():
    session = FakeSession({"/articles": {"articles": [{"id": 43, "name": "Other"}]}})
    assert _client(session).find_article_id("MSP 360 Backup Report") is None
    ambiguous = FakeSession({"/articles": {"articles": [
        {"id": 42, "name": "Report"}, {"id": 44, "name": "Report"}]}})
    assert _client(ambiguous).find_article_id("Report") is None


def test_create_article_issued_under_open_guard():
    session = FakeSession()
    result = _client(session, guard=_open_guard()).create_article(
        name="MSP 360 Backup Report", content="<table></table>")
    assert result is not None
    post = [c for c in session.calls if c[0] == "POST"]
    assert len(post) == 1 and post[0][1].endswith("/articles")
    assert post[0][3]["article"] == {"name": "MSP 360 Backup Report",
                                     "content": "<table></table>"}


def test_create_article_suppressed_under_default_guard():
    session = FakeSession()
    assert _client(session).create_article(name="R", content="c") is None
    assert not any(c[0] == "POST" for c in session.calls)


def test_update_article_issued_under_open_guard():
    session = FakeSession()
    _client(session, guard=_open_guard()).update_article(
        article_id=42, name="MSP 360 Backup Report", content="<p>new</p>")
    put = [c for c in session.calls if c[0] == "PUT"]
    assert len(put) == 1 and put[0][1].endswith("/articles/42")
    assert put[0][3]["article"]["content"] == "<p>new</p>"


def test_update_article_suppressed_under_default_guard():
    session = FakeSession()
    assert _client(session).update_article(42, "R", "c") is None
    assert not any(c[0] == "PUT" for c in session.calls)
