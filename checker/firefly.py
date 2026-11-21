"""Firefly III API client — fetch net credit-card spend for the current month.

Net spend = sum(withdrawals out of the card) - sum(deposits/refunds into the card),
restricted to the configured currency. Card payments and transfers are excluded because we
only query ``type=withdrawal`` and ``type=deposit``.
"""

from __future__ import annotations

from datetime import date, timedelta

import requests

_TIMEOUT = 30


class FireflyError(Exception):
    """Raised on any Firefly API failure (network, auth, bad account, etc.)."""


def _in_range(split: dict, start: date, end: date) -> bool:
    """True if the split's date (``YYYY-MM-DD...``) falls within ``[start, end]`` inclusive."""
    raw = str(split.get("date", ""))[:10]
    try:
        d = date.fromisoformat(raw)
    except ValueError:
        return False
    return start <= d <= end


class FireflyClient:
    def __init__(self, base_url: str, token: str, currency: str = "EUR"):
        self._base = base_url.rstrip("/")
        self._currency = currency.upper()
        self._session = requests.Session()
        self._session.headers.update(
            {
                "Authorization": f"Bearer {token}",
                "Accept": "application/json",
            }
        )

    def _get(self, path: str, params: dict | None = None) -> dict:
        url = f"{self._base}{path}"
        try:
            resp = self._session.get(url, params=params, timeout=_TIMEOUT)
        except requests.RequestException as exc:
            raise FireflyError(f"Request to Firefly failed: {exc}") from exc
        if resp.status_code == 401:
            raise FireflyError("Firefly rejected the PAT (401 Unauthorized).")
        if resp.status_code == 404:
            raise FireflyError(f"Firefly returned 404 for {path} — check the account ID.")
        if not resp.ok:
            raise FireflyError(f"Firefly returned HTTP {resp.status_code} for {path}: {resp.text[:200]}")
        try:
            return resp.json()
        except ValueError as exc:
            raise FireflyError(f"Firefly returned non-JSON for {path}") from exc

    def verify_account(self, account_id: str) -> str:
        """Confirm the account exists; return its display name. Fails loud on a bad ID."""
        data = self._get(f"/api/v1/accounts/{account_id}")
        attrs = data.get("data", {}).get("attributes", {})
        name = attrs.get("name")
        if not name:
            raise FireflyError(f"Account {account_id} has no name — unexpected response.")
        return name

    def _iter_splits(self, account_id: str, start: date, end: date):
        """Yield every transaction split for the account in the date range.

        We do NOT rely on the endpoint's ``type`` query parameter — on this endpoint it is
        unreliable (it can return withdrawals even when asked for deposits). Instead we
        fetch everything once and classify by each split's own ``type`` field.

        Firefly requires ``start`` to be strictly before ``end`` (it returns HTTP 422 when
        they are equal, e.g. on the 1st of the month). So we ask for one extra day and drop
        anything outside ``[start, end]`` client-side via :func:`_in_range`.
        """
        params = {
            "start": start.isoformat(),
            "end": (end + timedelta(days=1)).isoformat(),
            "type": "all",
            "limit": 100,
            "page": 1,
        }
        while True:
            payload = self._get(f"/api/v1/accounts/{account_id}/transactions", params=dict(params))
            for group in payload.get("data", []):
                for split in group.get("attributes", {}).get("transactions", []):
                    if _in_range(split, start, end):
                        yield split
            pagination = payload.get("meta", {}).get("pagination", {})
            current = pagination.get("current_page", params["page"])
            last = pagination.get("total_pages", current)
            if current >= last:
                break
            params["page"] = current + 1

    def net_spend(self, account_id: str, start: date, end: date) -> float:
        """Return net spend (withdrawals - refunds) on the account between dates inclusive.

        Withdrawals (purchases) add; deposits (refunds/credits into the card) subtract.
        Transfers (e.g. paying off the card) are ignored. Only the configured currency is
        counted.
        """
        net = 0.0
        for split in self._iter_splits(account_id, start, end):
            if split.get("currency_code", "").upper() != self._currency:
                continue
            try:
                amount = float(split.get("amount", 0))
            except (TypeError, ValueError):
                continue
            tx_type = split.get("type", "").lower()
            if tx_type == "withdrawal":
                net += amount
            elif tx_type == "deposit":
                net -= amount
            # transfers and anything else: ignored
        return net
