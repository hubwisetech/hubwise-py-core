"""Teams Workflows webhook client — Adaptive Card posts, WriteGuard-gated.

Posts to a Power Automate "when a Teams webhook request is received" flow
(the Outbound standard's replacement for the banned classic O365 connector).
The webhook URL embeds a signature, so it is a secret: it is never logged —
guard messages and errors reference the card, not the URL.
"""
from __future__ import annotations

from .guards import WriteGuard
from .http import build_session

CARD_CONTENT_TYPE = "application/vnd.microsoft.card.adaptive"


class TeamsWebhookClient:
    def __init__(self, webhook_url, guard: WriteGuard, session=None):
        self._url = webhook_url
        self._guard = guard
        self._session = session if session is not None else build_session()

    def post_adaptive_card(self, card):
        """Post one Adaptive Card. Returns True if the write was issued,
        False if suppressed by the guard."""
        if not self._guard.check_write("post Teams Adaptive Card"):
            return False
        payload = {"type": "message",
                   "attachments": [{"contentType": CARD_CONTENT_TYPE,
                                    "contentUrl": None, "content": card}]}
        resp = self._session.post(self._url, json=payload)
        resp.raise_for_status()
        return True
