"""Home Assistant notification client.

Calls the HA REST API to invoke a notify service:
``POST {HA_URL}/api/services/notify/<service>`` with a long-lived access token.
"""

from __future__ import annotations

import requests

_TIMEOUT = 30


class NotifyError(Exception):
    """Raised when Home Assistant rejects or cannot receive the notification."""


class HomeAssistantNotifier:
    def __init__(self, base_url: str, token: str, service: str):
        self._base = base_url.rstrip("/")
        # Accept "notify.mobile_app_x", "mobile_app_x", or "notify/mobile_app_x".
        self._service = service.replace("notify.", "").replace("notify/", "").strip("/")
        self._token = token

    def send(self, title: str, message: str) -> None:
        url = f"{self._base}/api/services/notify/{self._service}"
        try:
            resp = requests.post(
                url,
                headers={
                    "Authorization": f"Bearer {self._token}",
                    "Content-Type": "application/json",
                },
                json={"title": title, "message": message},
                timeout=_TIMEOUT,
            )
        except requests.RequestException as exc:
            raise NotifyError(f"Request to Home Assistant failed: {exc}") from exc
        if resp.status_code == 401:
            raise NotifyError("Home Assistant rejected the token (401 Unauthorized).")
        if not resp.ok:
            raise NotifyError(
                f"Home Assistant returned HTTP {resp.status_code} for notify/"
                f"{self._service}: {resp.text[:200]}"
            )
