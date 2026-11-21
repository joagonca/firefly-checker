"""ntfy notification client.

Publishes via ntfy's JSON API: ``POST {NTFY_URL}/`` with a body like
``{"topic": ..., "title": ..., "message": ..., "priority": 1-5, "tags": [...]}``.

JSON publishing is used instead of the header-based API because titles contain emoji,
which can't be sent in HTTP headers. Works with https://ntfy.sh or a self-hosted server.
"""

from __future__ import annotations

import requests

_TIMEOUT = 30


class NotifyError(Exception):
    """Raised when the ntfy server rejects or cannot receive the notification."""


class NtfyNotifier:
    def __init__(self, base_url: str, topic: str, token: str | None = None):
        self._base = base_url.rstrip("/")
        self._topic = topic.strip("/")
        self._token = token or None

    def build_payload(
        self,
        title: str,
        message: str,
        *,
        priority: int = 3,
        tags: list[str] | None = None,
        click: str | None = None,
    ) -> dict:
        payload: dict = {
            "topic": self._topic,
            "title": title,
            "message": message,
            "priority": int(priority),
        }
        if tags:
            payload["tags"] = list(tags)
        if click:
            payload["click"] = click
        return payload

    def _headers(self) -> dict:
        headers = {"Content-Type": "application/json"}
        if self._token:
            headers["Authorization"] = f"Bearer {self._token}"
        return headers

    def send(
        self,
        title: str,
        message: str,
        *,
        priority: int = 3,
        tags: list[str] | None = None,
        click: str | None = None,
    ) -> None:
        payload = self.build_payload(title, message, priority=priority, tags=tags, click=click)
        try:
            resp = requests.post(
                f"{self._base}/", headers=self._headers(), json=payload, timeout=_TIMEOUT
            )
        except requests.RequestException as exc:
            raise NotifyError(f"Request to ntfy failed: {exc}") from exc
        if resp.status_code in (401, 403):
            raise NotifyError(
                f"ntfy rejected the request (HTTP {resp.status_code}) — check the token/topic access."
            )
        if not resp.ok:
            raise NotifyError(
                f"ntfy returned HTTP {resp.status_code} for topic {self._topic}: {resp.text[:200]}"
            )
