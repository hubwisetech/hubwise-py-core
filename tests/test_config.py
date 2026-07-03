import pytest

from hubwise_py_core.config import MissingConfigError, flag, optional, require


def test_require_returns_stripped_value():
    value = require("CW_SITE", env={"CW_SITE": " api-na.myconnectwise.net \r"})
    assert value == "api-na.myconnectwise.net"


def test_require_raises_on_missing_key():
    with pytest.raises(MissingConfigError):
        require("CW_SITE", env={})


def test_require_raises_on_empty_value():
    with pytest.raises(MissingConfigError):
        require("CW_SITE", env={"CW_SITE": "   "})


def test_require_error_names_the_missing_key():
    with pytest.raises(MissingConfigError, match="CW_SITE"):
        require("CW_SITE", env={})


def test_optional_returns_default_when_missing():
    assert optional("FOO", default="bar", env={}) == "bar"


def test_optional_returns_value_when_present():
    assert optional("FOO", default="bar", env={"FOO": "baz"}) == "baz"


def test_optional_returns_default_when_value_is_blank():
    assert optional("FOO", default="bar", env={"FOO": "   "}) == "bar"


def test_flag_true_only_for_literal_one():
    assert flag("DRY_RUN", env={"DRY_RUN": "1"}) is True
    assert flag("DRY_RUN", env={"DRY_RUN": "true"}) is False


def test_flag_uses_default_when_missing():
    assert flag("DRY_RUN", default="1", env={}) is True
    assert flag("DRY_RUN", default="0", env={}) is False
