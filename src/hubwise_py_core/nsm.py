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
import re

from .guards import WriteGuard
from .http import build_session

MSW_BASE = "https://api.mysonicwall.com/api"
NSM_BASE = "https://nsm-uswest.sonicwall.com/api/manager"
CSC_TILE = "ISNSMSAFEENABLED"


class NSMClient:
    """Per-device SonicWall reads via the NSM manager proxy (addressed by
    serial, not WAN IP). Auth mirrors MySonicWallClient: CSC accesscode ->
    NSM SSO -> bearer. Read-only — no WriteGuard. The API key is sent
    per-request, never stored in the session's default headers."""

    def __init__(self, api_key, tenant_id, tenant_serial, session=None, guard=None):
        self._api_key = api_key
        self._tenant_id = tenant_id
        self._tenant_serial = tenant_serial
        self._session = session if session is not None else build_session()
        self._token = None
        # Writes (resync_device) are gated; reads never touch the guard, so a
        # missing guard leaves read-only callers unaffected.
        self._guard = guard if guard is not None else WriteGuard()

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

    def list_devices_firmware(self, page_size=50, max_pages=50):
        """Paged walk of ``GET /devices/tenant`` — the manager-scope device
        list whose records embed per-device firmware state AND the applicable
        ``availableVersions`` catalog (one endpoint = inventory + catalog for
        detect_firmware_releases). Read-only.

        The v2 inventory endpoint ignores paging and re-serves the whole
        fleet per call; this endpoint honors paging, but keep the serial
        de-dupe guard + hard page cap so a regression can never loop forever.
        Pair with ``parse_device_firmware``.
        """
        headers = {"x-gms-mode": "True", "x-snwl-timer": "no-reset",
                   "Authorization": f"Bearer {self._bearer()}"}
        out, seen = [], set()
        for page in range(1, max_pages + 1):
            resp = self._session.get(f"{NSM_BASE}/devices/tenant",
                                     params={"page": page, "limit": page_size},
                                     headers=headers)
            resp.raise_for_status()
            batch = resp.json() or []
            fresh = [r for r in batch if r.get("serialNumber") not in seen]
            if not fresh:
                break
            for record in fresh:
                seen.add(record.get("serialNumber"))
            out.extend(fresh)
            if len(batch) < page_size:
                break
        return out

    def resync_device(self, serial):
        """Trigger NSM to re-acquire (re-synchronize) a device's running config
        into the tenant. Gated write: ``PUT /api/manager/devices/{serial}/?
        acquire=true``. Returns True if the write was issued, False if the guard
        suppressed it. Keeping NSM's stored config fresh is what the NSM-backed
        syncs (#8, #9) read from.
        """
        if not self._guard.check_write(f"NSM re-acquire device {serial}"):
            return False
        headers = {"x-gms-mode": "True", "x-snwl-timer": "no-reset",
                   "Authorization": f"Bearer {self._bearer()}"}
        resp = self._session.put(f"{NSM_BASE}/devices/{serial}/",
                                 params={"acquire": "true"}, headers=headers)
        resp.raise_for_status()
        return True

    def reboot_devices(self, serials, scheduled_at_ms):
        """Restart one or more managed firewalls. Gated write:
        ``POST /api/manager/group-action/firewall/restart`` body
        ``{devices: [serials], scheduledAt: <Unix ms UTC>}`` (manager-scope;
        devices in the body, no X-DEVICE-ID). ``scheduled_at_ms`` is
        milliseconds — pass the intended reboot instant (immediate = now in
        ms). Returns True if the write was issued, False if the guard
        suppressed it. The exact scheduledAt unit is pinned at the canary
        reboot, not asserted here.
        """
        if not self._guard.check_write(
                f"NSM reboot devices {list(serials)}"):
            return False
        headers = {"x-gms-mode": "True", "x-snwl-timer": "no-reset",
                   "Authorization": f"Bearer {self._bearer()}"}
        resp = self._session.post(
            f"{NSM_BASE}/group-action/firewall/restart",
            json={"devices": list(serials), "scheduledAt": scheduled_at_ms},
            headers=headers)
        resp.raise_for_status()
        return True

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
        """Raw ``/firewall/ssl-vpn/server/base`` payload."""
        return self._device_get(serial, "ssl-vpn/server/base")

    def get_ssl_vpn_accesses(self, serial):
        """Raw ``/firewall/ssl-vpn/server/accesses`` payload (per-zone SSL VPN
        enable state). Pair with ``parse_ssl_vpn_accesses``."""
        return self._device_get(serial, "ssl-vpn/server/accesses")

    def get_local_user_groups(self, serial):
        """Raw ``/firewall/user/local/groups`` payload (local groups + members).
        Pair with ``parse_local_groups``."""
        return self._device_get(serial, "user/local/groups")


def netmask_to_cidr(netmask):
    """Dotted-quad IPv4 netmask -> CIDR prefix length (int)."""
    return ipaddress.IPv4Network(f"0.0.0.0/{netmask}").prefixlen


def parse_ssl_vpn_accesses(raw):
    """Normalize ``/ssl-vpn/server/accesses`` -> ``[{zone, enable}]``."""
    accesses = raw.get("ssl_vpn", {}).get("server", {}).get("access", [])
    return [{"zone": a.get("zone"), "enable": bool(a.get("enable"))} for a in accesses]


def parse_local_groups(raw):
    """Normalize ``/user/local/groups`` -> ``{group_name: [member_name, ...]}``."""
    groups = raw.get("user", {}).get("local", {}).get("group", [])
    out = {}
    for g in groups:
        name = g.get("name")
        if name is None:
            continue
        out[name] = [m.get("name") for m in g.get("member", []) if m.get("name")]
    return out


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


def parse_sonicos_version(text):
    """SonicOS version string -> comparable numeric tuple, or None.

    Accepts the inventory form (``"SonicOS 7.3.1-7013"``) and the catalog
    form (``"7.3.2-7010"``). Splits on ``.`` and ``-`` and keeps the leading
    run of numeric segments (a trailing ``R9691``-style build tag stops the
    run). Returns None when nothing numeric leads the string, so callers can
    skip-and-alert instead of guessing.
    """
    if not text:
        return None
    cleaned = text.strip()
    if cleaned.lower().startswith("sonicos"):
        cleaned = cleaned[len("sonicos"):].strip()
    core = cleaned.split()[0] if cleaned else ""
    numbers = []
    for segment in re.split(r"[.\-]", core):
        if not segment.isdigit():
            break
        numbers.append(int(segment))
    return tuple(numbers) if numbers else None


def parse_device_firmware(record):
    """Normalize one ``/devices/tenant`` record for firmware detection.

    ``firmware`` keeps NSM's raw string (``"SonicOS 7.3.1-7013"``) — feed it
    to ``parse_sonicos_version`` for comparisons. ``available_versions``
    preserves catalog order.
    """
    attrs = record.get("attributes") or {}
    model_info = record.get("modelInfo") or {}
    available = [
        {"version": v.get("version"), "release_type": v.get("releaseType"),
         "release_date": v.get("releaseDate")}
        for v in record.get("availableVersions") or []
    ]
    return {
        "serial": (record.get("serialNumber") or "").strip(),
        "name": record.get("friendlyName") or record.get("serialNumber") or "",
        "live": bool(record.get("liveStatus")),
        "model": attrs.get("model") or model_info.get("productName") or "",
        "product_code": model_info.get("productCode"),
        "firmware": attrs.get("firmware_version"),
        "available_versions": available,
        "scheduled_upgrade": bool(record.get("scheduledUpgrade")),
    }
