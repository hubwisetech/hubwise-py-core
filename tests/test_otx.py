from urllib.parse import parse_qs, urlparse

from hubwise_py_core.otx import OTXClient


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
    def __init__(self, pages):
        self.headers = {}
        self.calls = []  # (url, headers)
        self._pages = list(pages)

    def get(self, url, headers=None, **kwargs):
        self.calls.append((url, headers or {}))
        return FakeResponse(self._pages.pop(0))


def _client(pages):
    session = FakeSession(pages)
    return OTXClient(api_key="otx-key", session=session), session


def test_export_sends_api_key_types_and_modified_since():
    client, session = _client([{"results": [{"type": "IPv4", "indicator": "1.2.3.4"}],
                                "next": None}])

    results = client.export_indicators(modified_since="2026-07-04")

    assert [r["indicator"] for r in results] == ["1.2.3.4"]
    url, headers = session.calls[0]
    assert headers.get("X-OTX-API-KEY") == "otx-key"
    assert url.startswith("https://otx.alienvault.com/api/v1/indicators/export")
    q = parse_qs(urlparse(url).query)
    assert q["types"][0] == "IPv4,IPv6,domain"
    assert q["modified_since"][0] == "2026-07-04"


def test_export_follows_next_pagination():
    client, session = _client([
        {"results": [{"type": "IPv4", "indicator": "1.1.1.1"}],
         "next": "https://otx.alienvault.com/api/v1/indicators/export?page=2"},
        {"results": [{"type": "domain", "indicator": "evil.example"}], "next": None},
    ])

    results = client.export_indicators(modified_since="2026-07-04")

    assert [r["indicator"] for r in results] == ["1.1.1.1", "evil.example"]
    assert session.calls[1][0].endswith("page=2")


def test_export_stops_on_empty_next_string():
    client, session = _client([{"results": [{"type": "IPv4", "indicator": "9.9.9.9"}],
                                "next": ""}])
    assert len(client.export_indicators(modified_since="2026-07-04")) == 1
    assert len(session.calls) == 1


def test_export_handles_missing_results_key():
    client, _ = _client([{"next": None}])
    assert client.export_indicators(modified_since="2026-07-04") == []


def test_api_key_not_in_session_default_headers():
    client, session = _client([{"results": [], "next": None}])
    client.export_indicators(modified_since="2026-07-04")
    joined = " ".join(f"{k}={v}" for k, v in session.headers.items())
    assert "otx-key" not in joined
