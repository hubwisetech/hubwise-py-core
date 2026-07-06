from hubwise_py_core.msp360 import MSP360Client


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
    """Fake transport: POST /Provider/Login issues a token, GET /Monitoring
    returns the canned rows. Records every call for assertions."""

    def __init__(self, monitoring_rows=None):
        self.headers = {}
        self.calls = []  # (method, url, data/params, headers)
        self._rows = monitoring_rows or []

    def post(self, url, data=None, json=None, **kwargs):
        self.calls.append(("POST", url, data if data is not None else json))
        if "Provider/Login" in url:
            return FakeResponse({"access_token": "tok-123", "expires_in": 7200})
        return FakeResponse({}, status=404)

    def get(self, url, params=None, headers=None, **kwargs):
        self.calls.append(("GET", url, headers or {}))
        if "Monitoring" in url:
            return FakeResponse(self._rows)
        return FakeResponse({}, status=404)


def make_client(rows=None):
    session = FakeSession(monitoring_rows=rows)
    return MSP360Client(username="apiuser", password="apipass", session=session), session


def test_list_monitoring_logs_in_then_reads_with_bearer_token():
    client, session = make_client(rows=[{"PlanName": "Nightly", "Status": "Success"}])

    rows = client.list_monitoring()

    assert [r["PlanName"] for r in rows] == ["Nightly"]
    login_calls = [c for c in session.calls if c[0] == "POST"]
    assert len(login_calls) == 1
    assert "Provider/Login" in login_calls[0][1]
    assert login_calls[0][2] == {"UserName": "apiuser", "Password": "apipass"}
    get_calls = [c for c in session.calls if c[0] == "GET"]
    assert get_calls[0][2].get("Authorization") == "Bearer tok-123"


def test_token_is_reused_across_calls():
    client, session = make_client(rows=[])

    client.list_monitoring()
    client.list_monitoring()

    assert len([c for c in session.calls if c[0] == "POST"]) == 1


def test_numeric_status_and_plan_type_are_normalized_to_names():
    client, _ = make_client(rows=[
        {"PlanName": "A", "Status": 0, "PlanType": 1},
        {"PlanName": "B", "Status": 2, "PlanType": 3},
        {"PlanName": "C", "Status": 7, "PlanType": 0},
    ])

    rows = client.list_monitoring()

    assert [r["Status"] for r in rows] == ["Success", "Error", "Warning"]
    assert [r["PlanType"] for r in rows] == ["Backup", "BackupFiles", "NA"]


def test_string_status_passes_through_and_unknown_numeric_is_kept():
    client, _ = make_client(rows=[
        {"PlanName": "A", "Status": "Running", "PlanType": "Backup"},
        {"PlanName": "B", "Status": 99},
    ])

    rows = client.list_monitoring()

    assert rows[0]["Status"] == "Running"
    assert rows[0]["PlanType"] == "Backup"
    assert rows[1]["Status"] == 99


def test_password_is_not_stored_in_session_default_headers():
    client, session = make_client(rows=[])

    client.list_monitoring()

    joined = " ".join(f"{k}={v}" for k, v in session.headers.items())
    assert "apipass" not in joined
