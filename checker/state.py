"""Per-month notification de-duplication.

Persists a tiny JSON record so the daily cron run doesn't nag with the same warning every
day. The rule (see :func:`should_notify`):

* Send when the band escalates to a *more urgent* level than the most urgent already sent
  this month.
* Always send during the ``final`` window if still unmet (the home-stretch push).
* Send ``met`` exactly once.
* Never send for band ``none`` (on track / nothing to say).

State resets automatically when the calendar month changes.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from .pace import BAND_ORDER, Decision


@dataclass
class State:
    month: str = ""  # "YYYY-MM"
    last_band: str = "none"  # most urgent band notified this month
    met_notified: bool = False

    @classmethod
    def load(cls, path: Path) -> "State":
        try:
            data = json.loads(path.read_text())
        except (FileNotFoundError, json.JSONDecodeError):
            return cls()
        return cls(
            month=str(data.get("month", "")),
            last_band=str(data.get("last_band", "none")),
            met_notified=bool(data.get("met_notified", False)),
        )

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(
                {
                    "month": self.month,
                    "last_band": self.last_band,
                    "met_notified": self.met_notified,
                },
                indent=2,
            )
        )

    def _roll_month(self, month: str) -> None:
        if self.month != month:
            self.month = month
            self.last_band = "none"
            self.met_notified = False


def _severity(band: str) -> int:
    return BAND_ORDER.index(band)


def should_notify(state: State, decision: Decision, month: str) -> bool:
    """Decide whether ``decision`` warrants a notification, mutating ``state`` to record it.

    ``month`` is the current "YYYY-MM" string. Call :meth:`State.save` afterwards if this
    returns True (or whenever you want to persist the month roll).
    """
    state._roll_month(month)

    if decision.band == "none":
        return False

    if decision.band == "met":
        if state.met_notified:
            return False
        state.met_notified = True
        state.last_band = "met"
        return True

    # Always push during the final window while still unmet.
    if decision.band == "final":
        state.last_band = "final"
        return True

    # Otherwise only fire on escalation to a more urgent band than already seen.
    if _severity(decision.band) > _severity(state.last_band):
        state.last_band = decision.band
        return True

    return False
