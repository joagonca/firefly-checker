from datetime import date

from checker import pace
from checker.pace import evaluate


def test_target_met_is_celebratory_and_terminal():
    d = evaluate(net=260, today=date(2026, 6, 12), target=250)
    assert d.band == "met"
    assert d.on_track is True
    assert "🎉" in d.title


def test_met_exactly_at_target():
    d = evaluate(net=250, today=date(2026, 6, 15), target=250)
    assert d.band == "met"


def test_quiet_period_zero_spend_is_silent():
    # First 10 days: never warn, regardless of spend.
    d = evaluate(net=0, today=date(2026, 6, 5), target=250)
    assert d.band == "none"
    assert d.on_track is True


def test_quiet_period_last_day_is_silent():
    # Day 10 is still inside the quiet period.
    d = evaluate(net=0, today=date(2026, 6, 10), target=250)
    assert d.band == "none"


def test_first_warning_can_appear_on_day_11():
    # Day 11 of June (30 days): expected = 250*11/30 ≈ 91.7, factor 0.60 → threshold ≈ 55.
    d = evaluate(net=0, today=date(2026, 6, 11), target=250)
    assert d.band == "behind"


def test_met_fires_even_during_quiet_period():
    d = evaluate(net=250, today=date(2026, 6, 3), target=250)
    assert d.band == "met"


def test_mid_month_zero_spend_is_behind():
    # Day 15 of June (30 days): expected = 125, factor 0.60 → threshold 75. 0 < 75.
    d = evaluate(net=0, today=date(2026, 6, 15), target=250)
    assert d.band == "behind"


def test_late_month_under_eighty_percent_is_urgent():
    # Day 24 of June: expected = 200, factor 0.80 → threshold 160. 100 < 160.
    d = evaluate(net=100, today=date(2026, 6, 24), target=250)
    assert d.band == "urgent"


def test_final_window_unmet_is_final():
    # June has 30 days; final window = last 3 days (28, 29, 30). Day 29.
    d = evaluate(net=200, today=date(2026, 6, 29), target=250)
    assert d.band == "final"
    assert d.days_left == 1


def test_final_window_met_is_met_not_final():
    d = evaluate(net=250, today=date(2026, 6, 29), target=250)
    assert d.band == "met"


def test_on_track_mid_month_is_silent():
    # Day 15: threshold 75; 130€ clears it.
    d = evaluate(net=130, today=date(2026, 6, 15), target=250)
    assert d.band == "none"


def test_remaining_and_days_left_fields():
    d = evaluate(net=40, today=date(2026, 6, 10), target=250)
    assert d.remaining == 210
    assert d.days_in_month == 30
    assert d.days_left == 20


def test_band_order_is_strictly_increasing_severity():
    assert pace.BAND_ORDER.index("none") < pace.BAND_ORDER.index("behind")
    assert pace.BAND_ORDER.index("behind") < pace.BAND_ORDER.index("urgent")
    assert pace.BAND_ORDER.index("urgent") < pace.BAND_ORDER.index("final")
    assert pace.BAND_ORDER.index("final") < pace.BAND_ORDER.index("met")


def test_february_final_window():
    # 2026 Feb has 28 days; final window = 26, 27, 28. Day 26, unmet.
    d = evaluate(net=10, today=date(2026, 2, 26), target=250)
    assert d.band == "final"
