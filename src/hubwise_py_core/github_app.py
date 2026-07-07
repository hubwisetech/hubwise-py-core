"""GitHub App client — repo Contents API writes for the blocklist publisher.

Auth is the GitHub App flow: sign a short-lived RS256 JWT with the App's
private key, exchange it for an installation access token scoped to the
target repo, and use that token for Contents API calls. Content writes
(``put_file`` / ``delete_file``) are WriteGuard-gated. Neither the private
key nor the tokens are stored on the session or logged.
"""
from __future__ import annotations

import base64
import time

import jwt

from .guards import WriteGuard
from .http import build_session

API = "https://api.github.com"
_ACCEPT = "application/vnd.github+json"
_JWT_TTL = 540  # seconds (< GitHub's 10-min cap)


def _default_encoder(payload, private_key):
    return jwt.encode(payload, private_key, algorithm="RS256")


class GitHubAppClient:
    def __init__(self, app_id, private_key, owner, repo, guard: WriteGuard,
                 session=None, jwt_encoder=None, now=None):
        self._app_id = app_id
        self._private_key = private_key
        self._owner = owner
        self._repo = repo
        self._guard = guard
        self._session = session if session is not None else build_session()
        self._encode = jwt_encoder or _default_encoder
        self._now = now or time.time
        self._token = None

    # ---- auth ----
    def _app_jwt(self):
        issued = int(self._now())
        payload = {"iat": issued - 60, "exp": issued + _JWT_TTL, "iss": self._app_id}
        return self._encode(payload, self._private_key)

    def _auth(self):
        if self._token is None:
            jwt_headers = {"Authorization": f"Bearer {self._app_jwt()}", "Accept": _ACCEPT}
            inst = self._session.get(
                f"{API}/repos/{self._owner}/{self._repo}/installation",
                headers=jwt_headers)
            inst.raise_for_status()
            installation_id = inst.json()["id"]
            tok = self._session.post(
                f"{API}/app/installations/{installation_id}/access_tokens",
                headers=jwt_headers)
            tok.raise_for_status()
            self._token = tok.json()["token"]
        return {"Authorization": f"Bearer {self._token}", "Accept": _ACCEPT}

    def _contents_url(self, path):
        return f"{API}/repos/{self._owner}/{self._repo}/contents/{path}"

    # ---- reads ----
    def get_file(self, path):
        """Return (sha, decoded_text) for a file, or (None, None) if absent."""
        resp = self._session.get(self._contents_url(path), headers=self._auth())
        if resp.status_code == 404:
            return None, None
        resp.raise_for_status()
        body = resp.json()
        text = base64.b64decode(body.get("content", "")).decode()
        return body.get("sha"), text

    def get_file_sha(self, path):
        return self.get_file(path)[0]

    def list_dir(self, path):
        """List files in a repo directory: [{name, path, sha, type}]. [] if absent."""
        resp = self._session.get(self._contents_url(path), headers=self._auth())
        if resp.status_code == 404:
            return []
        resp.raise_for_status()
        body = resp.json()
        return body if isinstance(body, list) else []

    # ---- gated writes ----
    def put_file(self, path, text, message, sha=None):
        """Create or update a file (base64-encoded). Pass ``sha`` to update an
        existing file. Gated; returns the response JSON or None if suppressed."""
        if not self._guard.check_write(f"put GitHub file {self._owner}/{self._repo}:{path}"):
            return None
        if sha is None:  # updating an existing file requires its sha
            sha = self.get_file_sha(path)
        body = {"message": message,
                "content": base64.b64encode(text.encode()).decode()}
        if sha:
            body["sha"] = sha
        resp = self._session.put(self._contents_url(path), headers=self._auth(), json=body)
        resp.raise_for_status()
        return resp.json()

    def delete_file(self, path, sha, message):
        """Delete a file by sha. Gated; returns True if issued, False if suppressed."""
        if not self._guard.check_write(
                f"delete GitHub file {self._owner}/{self._repo}:{path}"):
            return False
        resp = self._session.delete(self._contents_url(path), headers=self._auth(),
                                    json={"message": message, "sha": sha})
        resp.raise_for_status()
        return True
