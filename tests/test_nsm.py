"""Tests for the NSM per-device firewall-read client.

Response shapes are taken verbatim from live NSM manager-proxy reads captured
during the §5.2 coverage audit (device HWTI-OMA1, SonicOS 7.3.2).
"""
import pytest

from hubwise_py_core import nsm
from hubwise_py_core.nsm import (
    NSMClient,
    netmask_to_cidr,
    parse_dhcp_scopes,
    parse_interfaces,
)


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
    """Routes NSM auth + per-device firewall reads by URL suffix, recording
    every call so tests can assert headers (X-DEVICE-ID, bearer)."""

    def __init__(self, device_payloads=None, inventory=None, error_subpaths=()):
        self.headers = {}
        self.calls = []  # (method, url, headers, json)
        self._device_payloads = device_payloads or {}
        self._inventory = inventory if inventory is not None else []
        self._error_subpaths = set(error_subpaths)

    def post(self, url, json=None, headers=None, **kwargs):
        self.calls.append(("POST", url, headers or {}, json))
        if "generate-cscaccesscode" in url:
            return FakeResponse({"content": {"accessCode": "CSC-123"}})
        if "auth/sso" in url:
            return FakeResponse({"status": {"success": True, "info": [
                {"code": "E_OK", "level": "info", "message": "nsm-bearer-xyz"}]}})
        return FakeResponse({}, status=404)

    def put(self, url, params=None, headers=None, **kwargs):
        self.calls.append(("PUT", url, headers or {}, dict(params or {})))
        return FakeResponse({"status": {"success": True}})

    def get(self, url, params=None, headers=None, **kwargs):
        self.calls.append(("GET", url, headers or {}, None))
        if "inventory/tenant" in url:
            return FakeResponse(self._inventory)
        for subpath, payload in self._device_payloads.items():
            if subpath in url:
                if subpath in self._error_subpaths:
                    return FakeResponse({"status": {"success": False, "info": [
                        {"code": "E_FAIL", "level": "error",
                         "message": f"path /{subpath} was not found"}]}})
                return FakeResponse(payload)
        return FakeResponse({"status": {"success": False, "info": [
            {"code": "E_FAIL", "level": "error", "message": "not found"}]}})


def make_client(session):
    return NSMClient(api_key="k", tenant_id="2367080",
                     tenant_serial="00401037ACAF", session=session)


class TestNetmaskToCidr:
    def test_class_c(self):
        assert netmask_to_cidr("255.255.255.0") == 24

    def test_class_b(self):
        assert netmask_to_cidr("255.255.0.0") == 16

    def test_slash_27(self):
        # HWTI-OMA1 WAN was 255.255.255.224
        assert netmask_to_cidr("255.255.255.224") == 27

    def test_full_mask(self):
        assert netmask_to_cidr("255.255.255.255") == 32


class TestParseInterfaces:
    # Trimmed real /api/manager/firewall/interfaces/ipv4 payload.
    RAW = {
        "interfaces": [
            {"ipv4": {  # LAN static
                "name": "X0", "comment": "HWTI Internal",
                "ip_assignment": {"zone": "LAN", "mode": {"static": {
                    "ip": "10.100.0.1", "netmask": "255.255.255.0",
                    "gateway": "0.0.0.0"}}}}},
            {"ipv4": {  # WAN static with DNS
                "name": "X1", "comment": "Great Plains WAN",
                "ip_assignment": {"zone": "WAN", "mode": {"static": {
                    "ip": "24.72.219.123", "netmask": "255.255.255.224",
                    "gateway": "24.72.219.126",
                    "dns": {"primary": "8.8.8.8", "secondary": "1.1.1.1",
                            "tertiary": "208.67.222.222"}}}}}},
            {"ipv4": {  # unassigned — no ip_assignment mode
                "name": "X2", "ip_assignment": {}}},
            {"ipv4": {  # portshield — no static IP
                "name": "X3", "comment": "",
                "ip_assignment": {"zone": "LAN", "mode": {"portshield": "X0"}}}},
            {"ipv4": {  # VLAN sub-interface, static
                "name": "X0", "comment": "IoT", "vlan": 252,
                "ip_assignment": {"zone": "IoT", "mode": {"static": {
                    "ip": "172.16.252.1", "netmask": "255.255.255.0",
                    "gateway": "0.0.0.0"}}}}},
        ]
    }

    def test_returns_only_statically_assigned_interfaces(self):
        parsed = parse_interfaces(self.RAW)
        # X2 (unassigned) and X3 (portshield) are dropped
        names = [(p["name"], p.get("vlan")) for p in parsed]
        assert ("X2", None) not in names
        assert ("X3", None) not in names
        assert len(parsed) == 3

    def test_lan_interface_fields(self):
        lan = next(p for p in parse_interfaces(self.RAW) if p["comment"] == "HWTI Internal")
        assert lan["ip"] == "10.100.0.1"
        assert lan["netmask"] == "255.255.255.0"
        assert lan["zone"] == "LAN"
        assert lan["vlan"] == 1  # untagged physical interface defaults to VLAN 1

    def test_wan_interface_carries_dns(self):
        wan = next(p for p in parse_interfaces(self.RAW) if p["zone"] == "WAN")
        assert wan["ip"] == "24.72.219.123"
        assert wan["wan_dns"] == ["8.8.8.8", "1.1.1.1", "208.67.222.222"]

    def test_vlan_subinterface_reports_its_vlan(self):
        iot = next(p for p in parse_interfaces(self.RAW) if p["comment"] == "IoT")
        assert iot["vlan"] == 252
        assert iot["ip"] == "172.16.252.1"


class TestNSMClientAuth:
    def test_bearer_minted_once_and_reused_across_reads(self):
        session = FakeSession(device_payloads={
            "firewall/interfaces/ipv4": {"interfaces": []},
            "firewall/dhcp-server/ipv4/base": {"dhcp_server": {"ipv4": {"enable": True}}},
        })
        client = make_client(session)
        client.get_interfaces("SERIAL1")
        client.get_dhcp_base("SERIAL1")
        csc = [c for c in session.calls if c[0] == "POST" and "generate-cscaccesscode" in c[1]]
        sso = [c for c in session.calls if c[0] == "POST" and "auth/sso" in c[1]]
        assert len(csc) == 1
        assert len(sso) == 1


class TestNSMClientDeviceReads:
    def _client(self, error_subpaths=()):
        session = FakeSession(device_payloads={
            "firewall/interfaces/ipv4": {"interfaces": [{"ipv4": {"name": "X0"}}]},
            "firewall/dhcp-server/ipv4/base": {"dhcp_server": {"ipv4": {"enable": True}}},
            "firewall/ssl-vpn/server/base": {"ssl_vpn": {"server": {"port": 4433}}},
        }, error_subpaths=error_subpaths)
        return make_client(session), session

    def test_get_interfaces_endpoint_and_device_header(self):
        client, session = self._client()
        result = client.get_interfaces("2CB8EDAA45A0")
        get = next(c for c in session.calls if c[0] == "GET" and "interfaces/ipv4" in c[1])
        assert get[1].endswith("/api/manager/firewall/interfaces/ipv4")
        assert get[2]["X-DEVICE-ID"] == "2CB8EDAA45A0"
        assert get[2]["Authorization"] == "Bearer nsm-bearer-xyz"
        assert result["interfaces"][0]["ipv4"]["name"] == "X0"

    def test_get_dhcp_base_endpoint(self):
        client, session = self._client()
        result = client.get_dhcp_base("SER")
        get = next(c for c in session.calls if c[0] == "GET" and "dhcp-server" in c[1])
        assert get[1].endswith("/api/manager/firewall/dhcp-server/ipv4/base")
        assert result["dhcp_server"]["ipv4"]["enable"] is True

    def test_get_ssl_vpn_server_endpoint(self):
        client, session = self._client()
        result = client.get_ssl_vpn_server("SER")
        get = next(c for c in session.calls if c[0] == "GET" and "ssl-vpn" in c[1])
        assert get[1].endswith("/api/manager/firewall/ssl-vpn/server/base")
        assert result["ssl_vpn"]["server"]["port"] == 4433

    def test_error_envelope_raises(self):
        client, _ = self._client(error_subpaths={"firewall/interfaces/ipv4"})
        with pytest.raises(RuntimeError, match="not found"):
            client.get_interfaces("SER")


class TestNSMClientInventory:
    def test_list_firewalls_returns_inventory_array(self):
        session = FakeSession(inventory=[
            {"friendlyName": "GOLD - OMA1", "serialNumber": "2CB8EDA67620", "liveStatus": True},
        ])
        client = make_client(session)
        fw = client.list_firewalls()
        assert len(fw) == 1
        assert fw[0]["friendlyName"] == "GOLD - OMA1"
        get = next(c for c in session.calls if c[0] == "GET")
        assert "inventory/tenant" in get[1]


class TestParseDhcpScopes:
    # Real /firewall/dhcp-server/ipv4/scopes/dynamic payload (GOLD-OMA1).
    RAW = {"dhcp_server": {"ipv4": {"scope": {"dynamic": [
        {"default_gateway": "10.100.0.1", "from": "10.100.0.50", "to": "10.100.0.249",
         "enable": True, "netmask": "255.255.255.0", "comment": "",
         "dns": {"server": {"inherit": True}}},
        {"default_gateway": "192.168.1.1", "from": "192.168.1.50", "to": "192.168.1.167",
         "enable": True, "netmask": "255.255.255.0", "comment": "BMS",
         "dns": {"server": {"static": {"primary": "9.9.9.9", "secondary": "0.0.0.0",
                                       "tertiary": "0.0.0.0"}}}},
    ]}}}}

    def test_returns_one_entry_per_scope(self):
        assert len(parse_dhcp_scopes(self.RAW)) == 2

    def test_inherited_dns_scope(self):
        s = parse_dhcp_scopes(self.RAW)[0]
        assert s["gateway"] == "10.100.0.1"
        assert s["from"] == "10.100.0.50"
        assert s["to"] == "10.100.0.249"
        assert s["enable"] is True
        assert s["dns_inherit"] is True
        assert s["dns_static"] == []

    def test_static_dns_scope_drops_zero_addresses(self):
        s = parse_dhcp_scopes(self.RAW)[1]
        assert s["dns_inherit"] is False
        assert s["dns_static"] == ["9.9.9.9"]  # 0.0.0.0 secondary/tertiary dropped

    def test_empty_payload_is_empty_list(self):
        assert parse_dhcp_scopes({}) == []
        assert parse_dhcp_scopes({"dhcp_server": {"ipv4": {"scope": {"dynamic": []}}}}) == []


class TestNSMClientDhcpScopes:
    def test_get_dhcp_scopes_endpoint(self):
        session = FakeSession(device_payloads={
            "firewall/dhcp-server/ipv4/scopes/dynamic":
                {"dhcp_server": {"ipv4": {"scope": {"dynamic": []}}}},
        })
        client = make_client(session)
        client.get_dhcp_scopes("SER")
        get = next(c for c in session.calls if c[0] == "GET" and "scopes/dynamic" in c[1])
        assert get[1].endswith("/api/manager/firewall/dhcp-server/ipv4/scopes/dynamic")
        assert get[2]["X-DEVICE-ID"] == "SER"


class TestParseSslVpnAccesses:
    RAW = {"ssl_vpn": {"server": {"access": [
        {"zone": "LAN", "enable": False},
        {"zone": "WAN", "enable": True},
        {"zone": "DMZ", "enable": False},
    ]}}}

    def test_returns_zone_enable_pairs(self):
        from hubwise_py_core.nsm import parse_ssl_vpn_accesses
        out = parse_ssl_vpn_accesses(self.RAW)
        assert {"zone": "WAN", "enable": True} in out
        assert len(out) == 3

    def test_empty_payload(self):
        from hubwise_py_core.nsm import parse_ssl_vpn_accesses
        assert parse_ssl_vpn_accesses({}) == []


class TestParseLocalGroups:
    RAW = {"user": {"local": {"group": [
        {"name": "SSLVPN Services", "member": [{"name": "hwadmin_vpn"}, {"name": "jsmith"}]},
        {"name": "Guest Services"},  # no member key
        {"name": "Everyone", "member": [{"name": "domotz"}]},
    ]}}}

    def test_maps_group_to_member_names(self):
        from hubwise_py_core.nsm import parse_local_groups
        groups = parse_local_groups(self.RAW)
        assert groups["SSLVPN Services"] == ["hwadmin_vpn", "jsmith"]
        assert groups["Everyone"] == ["domotz"]

    def test_group_without_members_is_empty_list(self):
        from hubwise_py_core.nsm import parse_local_groups
        assert parse_local_groups(self.RAW)["Guest Services"] == []

    def test_empty_payload(self):
        from hubwise_py_core.nsm import parse_local_groups
        assert parse_local_groups({}) == {}


class TestNSMClientSslVpnReads:
    def _client(self):
        session = FakeSession(device_payloads={
            "firewall/ssl-vpn/server/accesses":
                {"ssl_vpn": {"server": {"access": [{"zone": "WAN", "enable": True}]}}},
            "firewall/user/local/groups":
                {"user": {"local": {"group": [{"name": "SSLVPN Services", "member": []}]}}},
        })
        return make_client(session), session

    def test_get_ssl_vpn_accesses_endpoint(self):
        client, session = self._client()
        result = client.get_ssl_vpn_accesses("2CB8EDAA45A0")
        get = next(c for c in session.calls if c[0] == "GET" and "accesses" in c[1])
        assert get[1].endswith("/api/manager/firewall/ssl-vpn/server/accesses")
        assert get[2]["X-DEVICE-ID"] == "2CB8EDAA45A0"
        assert result["ssl_vpn"]["server"]["access"][0]["zone"] == "WAN"

    def test_get_local_user_groups_endpoint(self):
        client, session = self._client()
        result = client.get_local_user_groups("SER")
        get = next(c for c in session.calls if c[0] == "GET" and "user/local/groups" in c[1])
        assert get[1].endswith("/api/manager/firewall/user/local/groups")
        assert result["user"]["local"]["group"][0]["name"] == "SSLVPN Services"


class TestNSMClientResyncDevice:
    def _client(self, env):
        from hubwise_py_core.guards import WriteGuard
        session = FakeSession(device_payloads={})
        return NSMClient(api_key="k", tenant_id="2367080", tenant_serial="00401037ACAF",
                         session=session, guard=WriteGuard(env=env)), session

    def test_resync_issues_put_when_guard_open(self):
        client, session = self._client({"DRY_RUN": "0", "ALLOW_PROD": "1"})
        result = client.resync_device("2CB8EDAA45A0")
        put = next(c for c in session.calls if c[0] == "PUT")
        assert put[1].endswith("/api/manager/devices/2CB8EDAA45A0/")
        assert put[3] == {"acquire": "true"}
        assert put[2]["Authorization"] == "Bearer nsm-bearer-xyz"
        assert put[2]["x-gms-mode"] == "True"
        assert result is True

    def test_resync_suppressed_when_guard_closed(self):
        client, session = self._client({"DRY_RUN": "1", "ALLOW_PROD": "0"})
        result = client.resync_device("SER")
        assert not any(c[0] == "PUT" for c in session.calls)
        assert result is False

    def test_read_only_callers_unaffected_without_guard(self):
        # No guard passed -> reads never touch the guard.
        session = FakeSession(device_payloads={
            "firewall/interfaces/ipv4": {"interfaces": []}})
        client = make_client(session)
        client.get_interfaces("SER")  # must not raise
        assert not any(c[0] == "PUT" for c in session.calls)


class TestParseSonicosVersion:
    def test_strips_sonicos_prefix(self):
        assert nsm.parse_sonicos_version("SonicOS 7.3.1-7013") == (7, 3, 1, 7013)

    def test_plain_version(self):
        assert nsm.parse_sonicos_version("7.3.2-7010") == (7, 3, 2, 7010)

    def test_trailing_non_numeric_segment_ignored(self):
        assert nsm.parse_sonicos_version("7.3.3-7015-R9691") == (7, 3, 3, 7015)

    def test_unparseable_returns_none(self):
        assert nsm.parse_sonicos_version("unknown") is None
        assert nsm.parse_sonicos_version("") is None
        assert nsm.parse_sonicos_version(None) is None

    def test_ordering(self):
        older = nsm.parse_sonicos_version("SonicOS 7.3.1-7013")
        ga = nsm.parse_sonicos_version("7.3.2-7010")
        newer = nsm.parse_sonicos_version("7.3.3-7015")
        assert older < ga < newer
