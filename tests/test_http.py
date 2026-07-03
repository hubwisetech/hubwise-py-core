import requests

from hubwise_py_core.http import (
    DEFAULT_MAX_RETRIES,
    RETRYABLE_STATUS_CODES,
    build_session,
)


def test_build_session_returns_requests_session():
    session = build_session()
    assert isinstance(session, requests.Session)


def test_build_session_mounts_retry_adapter_on_both_schemes():
    session = build_session()
    https_adapter = session.get_adapter("https://example.com")
    http_adapter = session.get_adapter("http://example.com")
    assert https_adapter.max_retries.total == DEFAULT_MAX_RETRIES
    assert http_adapter.max_retries.total == DEFAULT_MAX_RETRIES


def test_build_session_honors_custom_max_retries():
    session = build_session(max_retries=5)
    adapter = session.get_adapter("https://example.com")
    assert adapter.max_retries.total == 5


def test_retryable_status_codes_include_429_and_5xx():
    for code in (429, 500, 502, 503, 504):
        assert code in RETRYABLE_STATUS_CODES


def test_build_session_status_forcelist_matches_retryable_codes():
    session = build_session()
    adapter = session.get_adapter("https://example.com")
    assert set(adapter.max_retries.status_forcelist) == set(RETRYABLE_STATUS_CODES)


def test_build_session_respects_retry_after_header():
    session = build_session()
    adapter = session.get_adapter("https://example.com")
    assert adapter.max_retries.respect_retry_after_header is True


def test_build_session_does_not_retry_post_by_default():
    # POST is not idempotent by default; retrying it risks double-creation.
    # urllib3's default allowed_methods excludes POST/PATCH.
    session = build_session()
    adapter = session.get_adapter("https://example.com")
    assert "POST" not in adapter.max_retries.allowed_methods


def test_session_applies_default_timeout(monkeypatch):
    session = build_session(timeout=5)
    captured = {}

    def fake_send(self, request, **kwargs):
        captured["timeout"] = kwargs.get("timeout")
        response = requests.Response()
        response.status_code = 200
        return response

    monkeypatch.setattr(requests.Session, "send", fake_send)
    session.get("https://example.com")
    assert captured["timeout"] == 5


def test_session_explicit_timeout_overrides_default(monkeypatch):
    session = build_session(timeout=5)
    captured = {}

    def fake_send(self, request, **kwargs):
        captured["timeout"] = kwargs.get("timeout")
        response = requests.Response()
        response.status_code = 200
        return response

    monkeypatch.setattr(requests.Session, "send", fake_send)
    session.get("https://example.com", timeout=1)
    assert captured["timeout"] == 1
