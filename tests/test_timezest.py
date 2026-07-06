from urllib.parse import parse_qs, urlparse

from hubwise_py_core.timezest import TimeZestClient


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
    """Serves a scripted sequence of pages regardless of URL."""

    def __init__(self, pages):
        self.headers = {}
        self.calls = []  # (url, headers)
        self._pages = list(pages)

    def get(self, url, headers=None, **kwargs):
        self.calls.append((url, headers or {}))
        return FakeResponse(self._pages.pop(0))


def _client(pages):
    session = FakeSession(pages)
    return TimeZestClient(api_token="tz-token", session=session), session


def test_requests_window_via_tql_with_bearer_auth():
    client, session = _client([{"data": [{"id": "r1", "created_at": 500}], "next_page": None}])

    rows = client.list_scheduling_requests(from_epoch=100, to_epoch=900)

    assert [r["id"] for r in rows] == ["r1"]
    url, headers = session.calls[0]
    assert headers.get("Authorization") == "Bearer tz-token"
    assert url.startswith("https://api.timezest.com/v1/scheduling_requests")
    tql = parse_qs(urlparse(url).query)["tql"][0]
    assert "created_at GTE 100" in tql and "created_at LTE 900" in tql


def test_follows_next_page_until_exhausted():
    client, session = _client([
        {"data": [{"id": "r1", "created_at": 500}],
         "next_page": "https://api.timezest.com/v1/scheduling_requests?page=2"},
        {"data": [{"id": "r2", "created_at": 400}], "next_page": ""},
    ])

    rows = client.list_scheduling_requests(from_epoch=100, to_epoch=900)

    assert [r["id"] for r in rows] == ["r1", "r2"]
    assert session.calls[1][0] == "https://api.timezest.com/v1/scheduling_requests?page=2"


def test_relative_next_page_is_resolved_against_endpoint():
    client, session = _client([
        {"data": [{"id": "r1", "created_at": 500}], "next_page": "?page=2"},
        {"data": [], "next_page": None},
    ])

    client.list_scheduling_requests(from_epoch=100, to_epoch=900)

    assert session.calls[1][0] == "https://api.timezest.com/v1/scheduling_requests?page=2"


def test_filters_out_of_window_rows_and_stops_when_page_is_older_than_window():
    client, session = _client([
        {"data": [{"id": "in", "created_at": 500}, {"id": "old", "created_at": 50}],
         "next_page": "?page=2"},
    ])

    rows = client.list_scheduling_requests(from_epoch=100, to_epoch=900)

    # out-of-window row dropped, and no page 2 fetched (page hit older data)
    assert [r["id"] for r in rows] == ["in"]
    assert len(session.calls) == 1


def test_empty_data_returns_empty():
    client, _ = _client([{"data": [], "next_page": "?page=2"}])
    assert client.list_scheduling_requests(from_epoch=100, to_epoch=900) == []
