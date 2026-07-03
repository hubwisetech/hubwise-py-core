import logging

from hubwise_py_core.logging import SecretRedactionFilter, alert, redact, summary


def test_summary_emits_structured_line(caplog):
    caplog.set_level(logging.INFO)
    summary("sync_cw_sites_to_hudu", read=42, written=5, skipped=1, errors=0)
    assert "job=sync_cw_sites_to_hudu" in caplog.text
    assert "read=42" in caplog.text
    assert "written=5" in caplog.text
    assert "skipped=1" in caplog.text
    assert "errors=0" in caplog.text


def test_summary_defaults_all_counts_to_zero(caplog):
    caplog.set_level(logging.INFO)
    summary("noop_job")
    assert "read=0" in caplog.text
    assert "written=0" in caplog.text
    assert "skipped=0" in caplog.text
    assert "errors=0" in caplog.text


def test_alert_emits_marker_and_detail(caplog):
    caplog.set_level(logging.ERROR)
    alert("SYNC_DEGRADED", "Hudu unreachable after 3 retries")
    assert "SYNC_DEGRADED" in caplog.text
    assert "Hudu unreachable after 3 retries" in caplog.text


def test_redact_replaces_nonempty_value():
    assert redact("sk-abc123") == "***REDACTED***"


def test_redact_leaves_empty_value_alone():
    assert redact("") == ""


def test_secret_redaction_filter_redacts_api_key_pairs():
    record = logging.LogRecord(
        name="test", level=logging.INFO, pathname=__file__, lineno=1,
        msg="calling Hudu api_key=abcdef123456 ok", args=(), exc_info=None,
    )
    SecretRedactionFilter().filter(record)
    assert "abcdef123456" not in record.getMessage()
    assert "***REDACTED***" in record.getMessage()


def test_secret_redaction_filter_redacts_password_and_token():
    record = logging.LogRecord(
        name="test", level=logging.INFO, pathname=__file__, lineno=1,
        msg="login password=hunter2 token: eyJhbGciOi", args=(), exc_info=None,
    )
    SecretRedactionFilter().filter(record)
    text = record.getMessage()
    assert "hunter2" not in text
    assert "eyJhbGciOi" not in text


def test_secret_redaction_filter_leaves_non_secret_pairs_alone():
    record = logging.LogRecord(
        name="test", level=logging.INFO, pathname=__file__, lineno=1,
        msg="job=sync read=42 written=5", args=(), exc_info=None,
    )
    SecretRedactionFilter().filter(record)
    assert record.getMessage() == "job=sync read=42 written=5"
