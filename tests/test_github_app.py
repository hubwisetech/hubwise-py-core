import base64

from hubwise_py_core.github_app import GitHubAppClient
from hubwise_py_core.guards import WriteGuard


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
    def __init__(self, contents=None):
        self.headers = {}
        self.calls = []  # (method, url, headers, json)
        # contents: {path: {"sha":..., "text":...}} for existing files
        self._contents = contents or {}

    def get(self, url, headers=None, **kwargs):
        self.calls.append(("GET", url, headers or {}, None))
        if url.endswith("/installation"):
            return FakeResponse({"id": 42})
        if "/contents/" in url:
            path = url.split("/contents/", 1)[1]
            if path in self._contents:
                f = self._contents[path]
                return FakeResponse({"name": path.split("/")[-1], "path": path,
                                     "sha": f["sha"],
                                     "content": base64.b64encode(
                                         f["text"].encode()).decode()})
            # directory listing?
            listing = [{"name": p.split("/")[-1], "path": p, "sha": v["sha"],
                        "type": "file"}
                       for p, v in self._contents.items() if p.startswith(path + "/")]
            if listing:
                return FakeResponse(listing)
            return FakeResponse({"message": "Not Found"}, status=404)
        return FakeResponse({}, status=404)

    def post(self, url, headers=None, json=None, **kwargs):
        self.calls.append(("POST", url, headers or {}, json))
        if "/access_tokens" in url:
            return FakeResponse({"token": "inst-token"})
        return FakeResponse({}, status=404)

    def put(self, url, headers=None, json=None, **kwargs):
        self.calls.append(("PUT", url, headers or {}, json))
        return FakeResponse({"content": {"path": url.split("/contents/", 1)[1]}})

    def delete(self, url, headers=None, json=None, **kwargs):
        self.calls.append(("DELETE", url, headers or {}, json))
        return FakeResponse({})


def _client(guard=None, contents=None):
    session = FakeSession(contents)
    return GitHubAppClient(app_id="123", private_key="KEY", owner="hubwisetech",
                           repo="public", guard=guard or WriteGuard(env={}),
                           session=session,
                           jwt_encoder=lambda payload, key: "fake.jwt"), session


def _open():
    return WriteGuard(env={"DRY_RUN": "0", "ALLOW_PROD": "1"})


def test_installation_token_flow_uses_jwt_then_token():
    client, session = _client(guard=_open())
    client.put_file("blocklists/x.txt", "1.2.3.4", "msg")

    inst = next(c for c in session.calls if c[1].endswith("/installation"))
    assert inst[2].get("Authorization") == "Bearer fake.jwt"
    tok = next(c for c in session.calls if "/access_tokens" in c[1])
    assert "/app/installations/42/access_tokens" in tok[1]
    put = next(c for c in session.calls if c[0] == "PUT")
    assert put[2].get("Authorization") == "Bearer inst-token"


def test_token_reused_across_calls():
    client, session = _client(guard=_open())
    client.put_file("blocklists/a.txt", "a", "m")
    client.put_file("blocklists/b.txt", "b", "m")
    assert len([c for c in session.calls if "/access_tokens" in c[1]]) == 1


def test_get_file_sha_returns_sha_or_none():
    client, _ = _client(contents={"blocklists/a.txt": {"sha": "abc", "text": "x"}})
    assert client.get_file_sha("blocklists/a.txt") == "abc"
    assert client.get_file_sha("blocklists/missing.txt") is None


def test_get_file_returns_sha_and_decoded_text():
    client, _ = _client(contents={"blocklists/a.txt": {"sha": "abc", "text": "1.1.1.1\n"}})
    sha, text = client.get_file("blocklists/a.txt")
    assert sha == "abc" and text == "1.1.1.1\n"
    assert client.get_file("blocklists/none.txt") == (None, None)


def test_list_dir_returns_name_sha_pairs():
    client, _ = _client(contents={"blocklists/a_1.txt": {"sha": "s1", "text": "x"},
                                  "blocklists/a_2.txt": {"sha": "s2", "text": "y"}})
    files = client.list_dir("blocklists")
    assert {f["name"] for f in files} == {"a_1.txt", "a_2.txt"}


def test_put_file_suppressed_under_default_guard():
    client, session = _client()
    assert client.put_file("blocklists/a.txt", "data", "msg") is None
    assert not any(c[0] == "PUT" for c in session.calls)


def test_put_file_issued_under_open_guard_base64_and_sha():
    client, session = _client(guard=_open(),
                              contents={"blocklists/a.txt": {"sha": "old", "text": "old"}})
    result = client.put_file("blocklists/a.txt", "1.2.3.4\n", "update")
    assert result is not None
    put = next(c for c in session.calls if c[0] == "PUT")
    body = put[3]
    assert base64.b64decode(body["content"]).decode() == "1.2.3.4\n"
    assert body["message"] == "update"
    assert body["sha"] == "old"  # includes existing sha for update


def test_put_file_new_file_omits_sha():
    client, session = _client(guard=_open())
    client.put_file("blocklists/new.txt", "data", "create")
    put = next(c for c in session.calls if c[0] == "PUT")
    assert "sha" not in put[3] or put[3].get("sha") is None


def test_delete_file_gated():
    client, session = _client()
    assert client.delete_file("blocklists/a.txt", "sha1", "del") is False
    assert not any(c[0] == "DELETE" for c in session.calls)

    client2, session2 = _client(guard=_open())
    assert client2.delete_file("blocklists/a.txt", "sha1", "del") is True
    d = next(c for c in session2.calls if c[0] == "DELETE")
    assert d[3]["sha"] == "sha1" and d[3]["message"] == "del"


def test_private_key_not_in_session_default_headers():
    client, session = _client(guard=_open())
    client.put_file("blocklists/a.txt", "x", "m")
    joined = " ".join(f"{k}={v}" for k, v in session.headers.items())
    assert "KEY" not in joined
