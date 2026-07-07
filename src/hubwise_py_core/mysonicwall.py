"""MySonicWall + NSM (us-west) client — managed-device + service-info reads.

Auth is a two-step MySonicWall flow (mirrors the legacy HWTI-SonicWall.psm1):
1. ``POST api.mysonicwall.com/api/generate-cscaccesscode`` (x-api-key +
   {tenantId, tileName}) -> a CSC access code;
2. ``POST nsm-uswest.sonicwall.com/api/manager/auth/sso`` (x-api-key +
   {tenantSerial, code}) -> an NSM bearer token (returned, oddly, at
   ``status.info.message``).
The bearer is then used for the device inventory; per-device service info is
read from MySonicWall with the x-api-key directly. Read-only — no WriteGuard.
The API key is sent per-request, never stored in session default headers.
"""
from __future__ import annotations

from .http import build_session

MSW_BASE = "https://api.mysonicwall.com/api"
NSM_BASE = "https://nsm-uswest.sonicwall.com/api/manager"
CSC_TILE = "ISNSMSAFEENABLED"


class MySonicWallClient:
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
            self._token = sso.json()["status"]["info"]["message"]
        return self._token

    def list_managed_sonicwalls(self):
        """All managed SonicWalls in the tenant inventory. Each record carries
        ``friendlyName`` and ``serialNumber`` (raw 12-hex)."""
        headers = {"x-gms-mode": "True", "x-snwl-timer": "no-reset",
                   "Authorization": f"Bearer {self._bearer()}"}
        resp = self._session.get(f"{NSM_BASE}/v2/devices/inventory/tenant",
                                 headers=headers)
        resp.raise_for_status()
        data = resp.json()
        if isinstance(data, list):
            return data
        # error envelope or wrapped list
        if isinstance(data, dict):
            status = data.get("status", {}).get("info", {})
            if status.get("level") == "error":
                raise RuntimeError(f"NSM inventory error: {status.get('message')}")
            for key in ("data", "devices", "content", "items"):
                if isinstance(data.get(key), list):
                    return data[key]
        return []

    def service_info(self, serial):
        """Product service/support info for one serial (support expiry dates)."""
        resp = self._session.get(f"{MSW_BASE}/product/serviceInfo",
                                 headers=self._api_headers(), params={"serial": serial})
        resp.raise_for_status()
        return resp.json()
