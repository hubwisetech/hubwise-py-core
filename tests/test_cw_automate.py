from hubwise_py_core.cw_automate import CWAutomateClient


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
    def __init__(self, groups_payload=None):
        self.headers = {}
        self.calls = []  # (method, url, params, headers, json)
        self._groups = groups_payload if groups_payload is not None else []

    def post(self, url, json=None, headers=None, **kwargs):
        self.calls.append(("POST", url, None, headers or {}, json))
        if "apitoken" in url:
            return FakeResponse({"AccessToken": "auto-tok", "ExpirationDate": "2099-01-01"})
        return FakeResponse({}, status=404)

    def get(self, url, params=None, headers=None, **kwargs):
        self.calls.append(("GET", url, dict(params or {}), headers or {}, None))
        if "/groups" in url:
            return FakeResponse(self._groups)
        return FakeResponse({}, status=404)


def _client(groups_payload=None):
    session = FakeSession(groups_payload)
    return CWAutomateClient(server="hubwisetech.hostedrmm.com", client_id="cid",
                            username="user", password="pw", session=session), session


def test_login_posts_apitoken_with_clientid_and_credentials():
    client, session = _client([{"Name": "G", "computers": []}])

    client.list_group_computers("HWT - Term Servers and RDS Servers")

    post = [c for c in session.calls if c[0] == "POST"][0]
    assert "https://hubwisetech.hostedrmm.com/cwa/api/v1/apitoken" == post[1]
    assert post[3].get("ClientId") == "cid"
    assert post[4] == {"Username": "user", "Password": "pw"}


def test_group_query_uses_bearer_clientid_condition_and_expand():
    client, session = _client([{"Name": "G", "computers": [{"ComputerName": "SVR1"}]}])

    computers = client.list_group_computers("HWT - Term Servers and RDS Servers")

    assert [c["ComputerName"] for c in computers] == ["SVR1"]
    get = [c for c in session.calls if c[0] == "GET"][0]
    assert get[1] == "https://hubwisetech.hostedrmm.com/cwa/api/v1/groups"
    assert get[3].get("Authorization") == "Bearer auto-tok"
    assert get[3].get("ClientId") == "cid"
    assert get[2].get("expand") == "computers"
    assert "name contains 'HWT - Term Servers and RDS Servers'" == get[2].get("condition")


def test_apostrophes_in_group_name_are_doubled():
    client, session = _client([])
    client.list_group_computers("O'Brien's Servers")
    get = [c for c in session.calls if c[0] == "GET"][0]
    assert get[2].get("condition") == "name contains 'O''Brien''s Servers'"


def test_flattens_computers_across_returned_groups():
    client, _ = _client([
        {"Name": "A", "computers": [{"ComputerName": "S1"}, {"ComputerName": "S2"}]},
        {"Name": "B", "computers": [{"ComputerName": "S3"}]},
    ])
    computers = client.list_group_computers("x")
    assert [c["ComputerName"] for c in computers] == ["S1", "S2", "S3"]


def test_handles_single_group_object_response():
    # some CWA responses come back as a single object, not a list
    client, _ = _client({"Name": "A", "computers": [{"ComputerName": "S1"}]})
    assert [c["ComputerName"] for c in client.list_group_computers("x")] == ["S1"]


def test_token_reused_across_calls():
    client, session = _client([{"Name": "G", "computers": []}])
    client.list_group_computers("x")
    client.list_group_computers("y")
    assert len([c for c in session.calls if c[0] == "POST"]) == 1


def test_password_not_in_session_default_headers():
    client, session = _client([])
    client.list_group_computers("x")
    joined = " ".join(f"{k}={v}" for k, v in session.headers.items())
    assert "pw" not in joined
