"""MSP360 Managed Backup (MBS) API client — monitoring reads only.

Auth is a form-encoded ``POST /api/Provider/Login`` (UserName/Password from
the console's API 2.0 settings) returning a bearer token, which is then sent
per-request rather than stored in the session's default headers so the
credential surface stays as small as possible. This client never writes to
MSP360, so no WriteGuard is involved. I/O via an injectable session.

Endpoint and payload shapes verified against the MSP360 PowerShell module
(the legacy job's transport) — ``Get-MBSApiUrl`` / ``Get-MBSAPIHeader``.
"""
from __future__ import annotations

from .http import build_session

BASE_URL = "https://api.mspbackups.com/api"

# MBS.API enum orders — the raw API returns numeric values for these.
STATUS_NAMES = (
    "Success", "Overdue", "Error", "Running",
    "Unknown", "Interrupted", "UnexpectedlyClosed", "Warning",
)
PLAN_TYPE_NAMES = (
    "NA", "Backup", "Restore", "BackupFiles", "RestoreFiles",
    "VMBackup", "VMRestore", "SQLBackup", "SQLResore",
    "ExchangeBackup", "ExchangeRestore", "BMSSBackup", "BMSSRestore",
    "ConsistencyCheck", "EC2Backup", "EC2Restore",
    "HyperVBackup", "HyperVRestore",
)


def _normalize(value, names):
    if isinstance(value, int) and 0 <= value < len(names):
        return names[value]
    return value


class MSP360Client:
    def __init__(self, username, password, session=None, base_url=BASE_URL):
        self._base = base_url.rstrip("/")
        self._username = username
        self._password = password
        self._session = session if session is not None else build_session()
        self._token = None

    def _bearer(self):
        if self._token is None:
            resp = self._session.post(
                f"{self._base}/Provider/Login",
                data={"UserName": self._username, "Password": self._password},
            )
            resp.raise_for_status()
            self._token = resp.json()["access_token"]
        return {"Authorization": f"Bearer {self._token}"}

    def list_monitoring(self):
        """All backup-plan monitoring rows, with numeric Status/PlanType
        enums normalized to their MBS.API names."""
        resp = self._session.get(f"{self._base}/Monitoring", headers=self._bearer())
        resp.raise_for_status()
        rows = resp.json()
        for row in rows:
            if "Status" in row:
                row["Status"] = _normalize(row["Status"], STATUS_NAMES)
            if "PlanType" in row:
                row["PlanType"] = _normalize(row["PlanType"], PLAN_TYPE_NAMES)
        return rows
