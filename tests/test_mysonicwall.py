import pytest

from hubwise_py_core.mysonicwall import MySonicWallClient


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
    def __init__(self, inventory=None, service=None):
        self.headers = {}
        self.calls = []  # (method, url, params, headers, json)
        self._inventory = inventory if inventory is not None else []
        self._service = service or {}

    def post(self, url, json=None, headers=None, **kwargs):
        self.calls.append(("POST", url, None, headers or {}, json))
        if "generate-cscaccesscode" in url:
            return FakeResponse({"content": {"accessCode": "CSC-123"}})
        if "auth/sso" in url:
            return FakeResponse({"status": {"info": {"message": "nsm-bearer-xyz"}}})
        return FakeResponse({}, status=404)

    def get(self, url, params=None, headers=None, **kwargs):
        self.calls.append(("GET", url, dict(params or {}), headers or {}, None))
        if "inventory/tenant" in url:
            return FakeResponse(self._inventory)
        if "serviceInfo" in url:
            serial = (params or {}).get("serial")
            return FakeResponse(self._service.get(serial, {}))
        return FakeResponse({}, status=404)


def _client(inventory=None, service=None):
    session = FakeSession(inventory, service)
    return MySonicWallClient(api_key="msw-key", tenant_id="2367080",
                             tenant_serial="00401037ACAF", session=session), session


def test_list_managed_does_csc_then_sso_then_inventory():
    client, session = _client(
        inventory=[{"friendlyName": "MECH-FW", "serialNumber": "18B169ABCDEF"}])

    devices = client.list_managed_sonicwalls()

    assert [d["serialNumber"] for d in devices] == ["18B169ABCDEF"]
    csc = next(c for c in session.calls if "generate-cscaccesscode" in c[1])
    assert csc[3].get("x-api-key") == "msw-key"
    assert csc[4] == {"tenantId": 2367080, "tileName": "ISNSMSAFEENABLED"}
    sso = next(c for c in session.calls if "auth/sso" in c[1])
    assert sso[4] == {"tenantSerial": "00401037ACAF", "code": "CSC-123"}
    inv = next(c for c in session.calls if "inventory/tenant" in c[1])
    assert inv[3].get("Authorization") == "Bearer nsm-bearer-xyz"
    assert inv[3].get("x-gms-mode") == "True"
    assert inv[3].get("x-snwl-timer") == "no-reset"


def test_bearer_reused_across_calls():
    client, session = _client(inventory=[], service={"S1": {}})
    client.list_managed_sonicwalls()
    client.service_info("S1")  # uses x-api-key, but must not re-auth
    client.list_managed_sonicwalls()
    csc_calls = [c for c in session.calls if "generate-cscaccesscode" in c[1]]
    assert len(csc_calls) == 1


def test_inventory_error_envelope_raises():
    client, _ = _client(inventory={"status": {"info": {"level": "error",
                                                        "message": "bad"}}})
    with pytest.raises(RuntimeError):
        client.list_managed_sonicwalls()


def test_inventory_unwraps_list_under_data_key():
    client, _ = _client(inventory={"data": [{"serialNumber": "S9"}],
                                   "status": {"info": {"level": "ok"}}})
    assert [d["serialNumber"] for d in client.list_managed_sonicwalls()] == ["S9"]


def test_service_info_uses_api_key_and_serial_param():
    client, session = _client(service={"18B169ABCDEF": {
        "PSAAdditionsExpiryDate": "2027-01-01", "PSAConfigurationsExpiryDate": "2026-06-01"}})
    info = client.service_info("18B169ABCDEF")
    assert info["PSAAdditionsExpiryDate"] == "2027-01-01"
    call = next(c for c in session.calls if "serviceInfo" in c[1])
    assert call[2].get("serial") == "18B169ABCDEF"
    assert call[3].get("x-api-key") == "msw-key"


def test_api_key_not_in_session_default_headers():
    client, session = _client(inventory=[])
    client.list_managed_sonicwalls()
    joined = " ".join(f"{k}={v}" for k, v in session.headers.items())
    assert "msw-key" not in joined
