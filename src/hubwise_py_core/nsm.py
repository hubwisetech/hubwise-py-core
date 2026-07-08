"""SonicWall NSM per-device firewall-read client + parse helpers.

Replaces the direct-SonicOS half of the legacy HWTI-SonicWall.psm1: instead of
authenticating to each firewall's WAN IP with a shared basic-auth password, all
reads go through the NSM manager proxy addressed by serial
(``GET /api/manager/firewall/<subpath>`` + header ``X-DEVICE-ID: <serial>``).
Auth is the same CSC-accesscode -> NSM SSO -> bearer flow as MySonicWallClient.
Read-only — no WriteGuard.
"""
from __future__ import annotations

import ipaddress

from .http import build_session

MSW_BASE = "https://api.mysonicwall.com/api"
NSM_BASE = "https://nsm-uswest.sonicwall.com/api/manager"
CSC_TILE = "ISNSMSAFEENABLED"


class NSMClient:
    """Per-device SonicWall reads via the NSM manager proxy (addressed by
    serial, not WAN IP). Auth mirrors MySonicWallClient: CSC accesscode ->
    NSM SSO -> bearer. Read-only — no WriteGuard. The API key is sent
    per-request, never stored in the session's default headers."""

    def __init__(self, api_key, tenant_id, tenant_serial, session=None):
        self._api_key = api_key
        self._tenant_id = tenant_id
        self._tenant_serial = tenant_serial
        self._session = session if session is not None else build_session()
        self._token = None

    def _api_headers(self):
        return {"x-api-key": self._api_key, "Content-Type": "application/json"}

    def _bearer(self):
        if self._token is None:
            csc = self._session.post(
                f"{MSW_BASE}/generate-cscaccesscode", headers=self._api_headers(),
                json={"tenantId": int(self._tenant_id), "tileName": CSC_TILE})
            csc.raise_for_status()
            access_code = csc.json()["content"]["accessCode"]
            sso = self._session.post(
                f"{NSM_BASE}/auth/sso", headers=self._api_headers(),
                json={"tenantSerial": self._tenant_serial, "code": access_code})
            sso.raise_for_status()
            status = sso.json().get("status", {})
            info = status.get("info") or []
            if isinstance(info, dict):
                info = [info]
            entry = info[0] if info else {}
            if status.get("success") is False or entry.get("level") == "error":
                raise RuntimeError(f"NSM SSO auth failed: {entry.get('message')}")
            self._token = entry["message"]
        return self._token

    def list_firewalls(self):
        """Tenant device inventory array (friendlyName, serialNumber,
        liveStatus). Same endpoint MySonicWallClient uses."""
        headers = {"x-gms-mode": "True", "x-snwl-timer": "no-reset",
                   "Authorization": f"Bearer {self._bearer()}"}
        resp = self._session.get(f"{NSM_BASE}/v2/devices/inventory/tenant",
                                 headers=headers)
        resp.raise_for_status()
        data = resp.json()
        if isinstance(data, list):
            return data
        if isinstance(data, dict):
            for key in ("data", "devices", "content", "items"):
                if isinstance(data.get(key), list):
                    return data[key]
        return []

    def _device_get(self, serial, subpath):
        """GET /firewall/<subpath> for one device; raise on SonicOS error
        envelope, else return the parsed JSON."""
        headers = {"Authorization": f"Bearer {self._bearer()}", "X-DEVICE-ID": serial}
        resp = self._session.get(f"{NSM_BASE}/firewall/{subpath}", headers=headers)
        resp.raise_for_status()
        data = resp.json()
        if isinstance(data, dict) and data.get("status", {}).get("success") is False:
            info = data["status"].get("info") or []
            msg = info[0].get("message") if info else "unknown error"
            raise RuntimeError(f"NSM device read failed ({subpath}): {msg}")
        return data

    def get_interfaces(self, serial):
        """Raw ``/firewall/interfaces/ipv4`` payload. Pair with
        ``parse_interfaces`` to normalize."""
        return self._device_get(serial, "interfaces/ipv4")

    def get_dhcp_base(self, serial):
        """Raw ``/firewall/dhcp-server/ipv4/base`` payload (global DHCP state)."""
        return self._device_get(serial, "dhcp-server/ipv4/base")

    def get_dhcp_scopes(self, serial):
        """Raw ``/firewall/dhcp-server/ipv4/scopes/dynamic`` payload (dynamic
        DHCP ranges). NB: the path noun is plural ``scopes``. Pair with
        ``parse_dhcp_scopes``."""
        return self._device_get(serial, "dhcp-server/ipv4/scopes/dynamic")

    def get_ssl_vpn_server(self, serial):
        """Raw ``/firewall/ssl-vpn/server/base`` payload (for #9)."""
        return self._device_get(serial, "ssl-vpn/server/base")


def netmask_to_cidr(netmask):
    """Dotted-quad IPv4 netmask -> CIDR prefix length (int)."""
    return ipaddress.IPv4Network(f"0.0.0.0/{netmask}").prefixlen


def parse_dhcp_scopes(raw):
    """Normalize a ``/dhcp-server/ipv4/scopes/dynamic`` payload.

    Returns one dict per dynamic scope:
    ``{gateway, from, to, enable, netmask, comment, dns_inherit, dns_static}``.
    ``dns_static`` drops placeholder ``0.0.0.0`` entries.
    """
    scopes = (raw.get("dhcp_server", {}).get("ipv4", {})
              .get("scope", {}).get("dynamic", []))
    out = []
    for s in scopes:
        dns_server = s.get("dns", {}).get("server", {})
        static = dns_server.get("static", {})
        dns_static = [static[k] for k in ("primary", "secondary", "tertiary")
                      if static.get(k) and static[k] != "0.0.0.0"]
        out.append({
            "gateway": s.get("default_gateway"),
            "from": s.get("from"),
            "to": s.get("to"),
            "enable": bool(s.get("enable")),
            "netmask": s.get("netmask"),
            "comment": s.get("comment", ""),
            "dns_inherit": bool(dns_server.get("inherit")),
            "dns_static": dns_static,
        })
    return out


def parse_interfaces(raw):
    """Normalize a ``/firewall/interfaces/ipv4`` payload.

    Returns one dict per statically-assigned interface:
    ``{name, comment, zone, ip, netmask, gateway, vlan, wan_dns}``.
    Interfaces without a static IP (unassigned, portshield, dhcp) are dropped —
    they carry no network to document.
    """
    out = []
    for entry in raw.get("interfaces", []):
        ipv4 = entry.get("ipv4", {})
        assignment = ipv4.get("ip_assignment", {})
        static = assignment.get("mode", {}).get("static")
        if not static or not static.get("ip"):
            continue
        dns = static.get("dns", {})
        wan_dns = [dns[k] for k in ("primary", "secondary", "tertiary")
                   if dns.get(k) and dns[k] != "0.0.0.0"]
        out.append({
            "name": ipv4.get("name"),
            "comment": ipv4.get("comment", ""),
            "zone": assignment.get("zone"),
            "ip": static.get("ip"),
            "netmask": static.get("netmask"),
            "gateway": static.get("gateway"),
            "vlan": ipv4.get("vlan", 1),
            "wan_dns": wan_dns,
        })
    return out
