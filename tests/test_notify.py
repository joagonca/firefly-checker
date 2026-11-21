import pytest
import requests

from checker import notify
from checker.notify import NotifyError, NtfyNotifier


class _Resp:
    def __init__(self, status=200, text="{}"):
        self.status_code = status
        self.text = text

    @property
    def ok(self):
        return 200 <= self.status_code < 300


def _capture(monkeypatch, resp=None, exc=None):
    sent = {}

    def fake_post(url, headers=None, json=None, timeout=None):
        sent.update(url=url, headers=headers, json=json, timeout=timeout)
        if exc:
            raise exc
        return resp or _Resp()

    monkeypatch.setattr(notify.requests, "post", fake_post)
    return sent


def test_send_posts_json_to_server_root(monkeypatch):
    sent = _capture(monkeypatch)
    NtfyNotifier("https://ntfy.sh/", "my-topic").send("🎉 Title", "Body", priority=4, tags=["tada"])
    assert sent["url"] == "https://ntfy.sh/"
    assert sent["json"] == {"topic": "my-topic", "title": "🎉 Title", "message": "Body", "priority": 4, "tags": ["tada"]}
    assert "Authorization" not in sent["headers"]


def test_token_adds_bearer_header(monkeypatch):
    sent = _capture(monkeypatch)
    NtfyNotifier("https://ntfy.example", "t", token="tk_abc").send("x", "y")
    assert sent["headers"]["Authorization"] == "Bearer tk_abc"


def test_optional_fields_omitted():
    payload = NtfyNotifier("https://ntfy.sh", "t").build_payload("x", "y")
    assert "tags" not in payload and "click" not in payload
    assert payload["priority"] == 3


@pytest.mark.parametrize("status", [401, 403, 500])
def test_http_errors_raise(monkeypatch, status):
    _capture(monkeypatch, resp=_Resp(status, "nope"))
    with pytest.raises(NotifyError):
        NtfyNotifier("https://ntfy.sh", "t").send("x", "y")


def test_network_error_raises(monkeypatch):
    _capture(monkeypatch, exc=requests.ConnectionError("down"))
    with pytest.raises(NotifyError):
        NtfyNotifier("https://ntfy.sh", "t").send("x", "y")
