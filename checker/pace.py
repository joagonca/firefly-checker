"""Pure decision logic: given spend-so-far and the date, decide whether/how to warn.

This module has no I/O and no dependencies on config/Firefly/HA, so every branch is
trivially unit-testable. ``evaluate`` is the only entry point.

Bands, from least to most urgent:
    behind < urgent < final < met

The first ``QUIET_PERIOD_DAYS`` of the month are intentionally silent — no warnings, to
avoid pressuring early spending. After that we notify when actual net spend has dropped
below ``expected * factor`` for the current part of the month. The factor loosens earlier
in the month and tightens toward the end. ``met`` is a terminal, celebratory state once the
target is hit (it can fire at any time, including the quiet period — good news, not pressure).
"""

from __future__ import annotations

import calendar
from dataclasses import dataclass
from datetime import date

# Urgency ordering — index = severity. ``met`` sits at the top as a distinct happy path.
BAND_ORDER = ["none", "behind", "urgent", "final", "met"]

# (factor, band) selection happens in ``_band_and_factor``. Factors are the share of the
# linear pace target you must have reached to NOT trigger that band's warning.
BEHIND_FACTOR = 0.60
URGENT_FACTOR = 0.80
FINAL_FACTOR = 1.00

# No warnings at all for this many days at the start of the month.
QUIET_PERIOD_DAYS = 10

# How many days at the end of the month count as the "final push".
FINAL_WINDOW_DAYS = 3


@dataclass(frozen=True)
class Decision:
    band: str
    expected: float
    net: float
    deficit: float
    days_in_month: int
    day: int
    days_left: int
    remaining: float  # target - net, floored at 0
    on_track: bool
    title: str
    message: str

    @property
    def severity(self) -> int:
        return BAND_ORDER.index(self.band)


def _band_and_factor(day: int, days_in_month: int) -> tuple[str, float]:
    """Pick the active warning band/factor for a given day-of-month.

    Callers must first honour the quiet period (days 1..QUIET_PERIOD_DAYS stay silent).
    """
    days_left = days_in_month - day
    if days_left < FINAL_WINDOW_DAYS:
        return "final", FINAL_FACTOR
    if day <= 20:
        return "behind", BEHIND_FACTOR
    return "urgent", URGENT_FACTOR


def evaluate(net: float, today: date, target: float = 250.0, currency: str = "EUR") -> Decision:
    """Evaluate spend ``net`` against the pace target for ``today``.

    Returns a :class:`Decision`. ``band == "none"`` means on-track / nothing to say.
    """
    days_in_month = calendar.monthrange(today.year, today.month)[1]
    day = today.day
    days_left = days_in_month - day
    expected = target * day / days_in_month
    deficit = expected - net
    remaining = max(target - net, 0.0)
    sym = _symbol(currency)

    # Terminal happy path.
    if net >= target:
        return Decision(
            band="met",
            expected=expected,
            net=net,
            deficit=deficit,
            days_in_month=days_in_month,
            day=day,
            days_left=days_left,
            remaining=0.0,
            on_track=True,
            title="🎉 Monthly card target reached",
            message=(
                f"You've spent {net:.0f}{sym} on the card this month — the "
                f"{target:.0f}{sym} minimum is covered. Nothing more to do."
            ),
        )

    # Quiet period: no warnings for the first stretch of the month, regardless of pace.
    if day <= QUIET_PERIOD_DAYS:
        on_track = True
        band = "none"
    else:
        candidate_band, factor = _band_and_factor(day, days_in_month)
        on_track = net >= expected * factor
        band = "none" if on_track else candidate_band

    title, message = _compose_message(
        band=band,
        net=net,
        expected=expected,
        target=target,
        day=day,
        days_in_month=days_in_month,
        days_left=days_left,
        remaining=remaining,
        sym=sym,
    )
    return Decision(
        band=band,
        expected=expected,
        net=net,
        deficit=deficit,
        days_in_month=days_in_month,
        day=day,
        days_left=days_left,
        remaining=remaining,
        on_track=on_track,
        title=title,
        message=message,
    )


def _symbol(currency: str) -> str:
    return {"EUR": "€", "USD": "$", "GBP": "£"}.get(currency.upper(), f" {currency}")


def _compose_message(
    *,
    band: str,
    net: float,
    expected: float,
    target: float,
    day: int,
    days_in_month: int,
    days_left: int,
    remaining: float,
    sym: str,
) -> tuple[str, str]:
    pace = (
        f"You're at {net:.0f}{sym} of the {target:.0f}{sym} monthly card minimum; "
        f"to stay on pace you'd want about {expected:.0f}{sym} by day {day}."
    )
    runway = (
        f"Need {remaining:.0f}{sym} more in the next {days_left} day"
        f"{'s' if days_left != 1 else ''}."
    )
    if band == "none":
        return (
            "Card spend on track",
            f"On track: {net:.0f}{sym} spent, pace target ~{expected:.0f}{sym}. {runway}",
        )
    if band == "behind":
        return ("Card spend behind pace", f"{pace} You're falling behind. {runway}")
    if band == "urgent":
        return ("Card spend well behind", f"⚠️ {pace} {runway}")
    if band == "final":
        return (
            "Final days to hit card minimum",
            f"⏰ Month nearly over and you're short. {runway} (currently {net:.0f}{sym}).",
        )
    # Should not reach here for "met" (handled in evaluate) or unknown bands.
    return ("Card spend update", f"{pace} {runway}")
