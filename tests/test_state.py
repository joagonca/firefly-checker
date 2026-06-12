from datetime import date

from checker.pace import evaluate
from checker.state import State, should_notify


def _decision(net, today):
    return evaluate(net=net, today=today, target=250)


def test_on_track_never_notifies():
    st = State()
    d = _decision(130, date(2026, 6, 15))  # band none
    assert should_notify(st, d, "2026-06") is False


def test_first_warning_fires_then_dedups_same_band():
    st = State()
    d = _decision(0, date(2026, 6, 15))  # behind
    assert should_notify(st, d, "2026-06") is True
    # Same band next day: no repeat.
    assert should_notify(st, d, "2026-06") is False


def test_escalation_fires_again():
    st = State()
    assert should_notify(st, _decision(0, date(2026, 6, 15)), "2026-06") is True  # behind
    # Later in month, escalate to urgent.
    assert should_notify(st, _decision(0, date(2026, 6, 24)), "2026-06") is True  # urgent
    assert st.last_band == "urgent"


def test_de_escalation_does_not_fire():
    st = State()
    assert should_notify(st, _decision(0, date(2026, 6, 24)), "2026-06") is True  # urgent
    # A lower-severity 'behind' decision afterwards should not re-fire.
    behind = _decision(0, date(2026, 6, 15))  # behind, severity below urgent
    assert should_notify(st, behind, "2026-06") is False
    assert st.last_band == "urgent"


def test_final_window_fires_daily_while_unmet():
    st = State()
    d28 = _decision(200, date(2026, 6, 28))  # final
    d29 = _decision(200, date(2026, 6, 29))  # final
    assert should_notify(st, d28, "2026-06") is True
    assert should_notify(st, d29, "2026-06") is True  # fires again next day


def test_met_fires_once():
    st = State()
    d = _decision(260, date(2026, 6, 20))  # met
    assert should_notify(st, d, "2026-06") is True
    assert should_notify(st, d, "2026-06") is False
    assert st.met_notified is True


def test_month_rollover_resets():
    st = State()
    should_notify(st, _decision(0, date(2026, 6, 15)), "2026-06")  # behind, fires
    assert st.last_band == "behind"
    # New month: state resets, so the same band fires again.
    assert should_notify(st, _decision(0, date(2026, 7, 15)), "2026-07") is True
    assert st.month == "2026-07"


def test_save_and_load_roundtrip(tmp_path):
    path = tmp_path / "state.json"
    st = State(month="2026-06", last_band="urgent", met_notified=False)
    st.save(path)
    loaded = State.load(path)
    assert loaded.month == "2026-06"
    assert loaded.last_band == "urgent"
    assert loaded.met_notified is False


def test_load_missing_file_returns_default(tmp_path):
    loaded = State.load(tmp_path / "nope.json")
    assert loaded.month == ""
    assert loaded.last_band == "none"
