import logging

from hubwise_py_core.guards import WriteGuard


def test_default_env_blocks_writes():
    guard = WriteGuard(env={})
    assert guard.dry_run is True
    assert guard.allow_prod is False
    assert guard.writes_allowed is False


def test_dry_run_off_alone_does_not_allow_writes():
    guard = WriteGuard(env={"DRY_RUN": "0"})
    assert guard.writes_allowed is False


def test_allow_prod_alone_does_not_allow_writes():
    guard = WriteGuard(env={"ALLOW_PROD": "1"})
    assert guard.writes_allowed is False


def test_both_gates_open_allows_writes():
    guard = WriteGuard(env={"DRY_RUN": "0", "ALLOW_PROD": "1"})
    assert guard.writes_allowed is True


def test_check_write_returns_false_and_logs_when_blocked(caplog):
    caplog.set_level(logging.INFO)
    guard = WriteGuard(env={})
    assert guard.check_write("create ticket") is False
    assert "DRY_RUN" in caplog.text
    assert "create ticket" in caplog.text


def test_check_write_returns_true_when_allowed():
    guard = WriteGuard(env={"DRY_RUN": "0", "ALLOW_PROD": "1"})
    assert guard.check_write("create ticket") is True


def test_env_values_are_stripped_of_whitespace_and_cr():
    # az ... -o tsv under the WSL shim appends a trailing \r
    guard = WriteGuard(env={"DRY_RUN": "0 \r", "ALLOW_PROD": "1\r"})
    assert guard.writes_allowed is True
