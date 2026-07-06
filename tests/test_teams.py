from hubwise_py_core.guards import WriteGuard
from hubwise_py_core.teams import TeamsWebhookClient


class FakeResponse:
    status_code = 202

    def json(self):
        return {}

    def raise_for_status(self):
        pass


class FakeSession:
    def __init__(self):
        self.headers = {}
        self.calls = []  # (url, json)

    def post(self, url, json=None, **kwargs):
        self.calls.append((url, json))
        return FakeResponse()


WEBHOOK = "https://prod.powerplatform.example/workflows/abc/triggers/manual?sig=SECRET"


def _client(guard=None):
    session = FakeSession()
    return TeamsWebhookClient(webhook_url=WEBHOOK,
                              guard=guard or WriteGuard(env={}),
                              session=session), session


def _open_guard():
    return WriteGuard(env={"DRY_RUN": "0", "ALLOW_PROD": "1"})


def test_post_adaptive_card_wraps_payload_and_posts_when_allowed():
    client, session = _client(guard=_open_guard())
    card = {"type": "AdaptiveCard", "version": "1.4", "body": []}

    result = client.post_adaptive_card(card)

    assert result is True
    assert len(session.calls) == 1
    url, payload = session.calls[0]
    assert url == WEBHOOK
    assert payload["type"] == "message"
    attachment = payload["attachments"][0]
    assert attachment["contentType"] == "application/vnd.microsoft.card.adaptive"
    assert attachment["content"] is card


def test_post_adaptive_card_suppressed_under_default_guard(caplog):
    client, session = _client()

    result = client.post_adaptive_card({"type": "AdaptiveCard"})

    assert result is False
    assert session.calls == []
    # the signed webhook URL must never appear in logs
    assert "SECRET" not in caplog.text and "sig=" not in caplog.text
