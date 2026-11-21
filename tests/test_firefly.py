from datetime import date

from checker.firefly import FireflyClient, _in_range


def _group(*splits):
    return {"attributes": {"transactions": list(splits)}}


def _split(d, amount, tx_type="withdrawal", currency="EUR"):
    return {"date": f"{d}T12:00:00+00:00", "amount": str(amount), "type": tx_type, "currency_code": currency}


def test_in_range_inclusive_bounds():
    s, e = date(2026, 11, 1), date(2026, 11, 21)
    assert _in_range({"date": "2026-11-01T00:00:00+00:00"}, s, e)
    assert _in_range({"date": "2026-11-21T23:59:00+00:00"}, s, e)
    assert not _in_range({"date": "2026-10-31T23:59:00+00:00"}, s, e)
    assert not _in_range({"date": "2026-11-22T00:00:00+00:00"}, s, e)


def test_in_range_bad_date_is_excluded():
    assert not _in_range({"date": "garbage"}, date(2026, 11, 1), date(2026, 11, 2))
    assert not _in_range({}, date(2026, 11, 1), date(2026, 11, 2))


def test_first_of_month_queries_valid_range_and_filters(monkeypatch):
    """Day 1: start == end. Firefly needs start < end, so we query one extra day and filter."""
    client = FireflyClient("https://ff.example", "tok")
    calls = []

    def fake_get(path, params=None):
        calls.append(params)
        return {
            "data": [
                _group(
                    _split("2026-12-01", 40),
                    _split("2026-12-01", 5, tx_type="deposit"),
                    _split("2026-12-02", 999),  # extra day returned by the widened query
                    _split("2026-12-01", 7, tx_type="transfer"),
                    _split("2026-12-01", 100, currency="USD"),
                )
            ],
            "meta": {"pagination": {"current_page": 1, "total_pages": 1}},
        }

    monkeypatch.setattr(client, "_get", fake_get)
    net = client.net_spend("281", date(2026, 12, 1), date(2026, 12, 1))

    assert net == 35.0
    assert calls[0]["start"] == "2026-12-01"
    assert calls[0]["end"] == "2026-12-02"
    assert calls[0]["start"] < calls[0]["end"]


def test_pagination_still_followed(monkeypatch):
    client = FireflyClient("https://ff.example", "tok")
    pages = {
        1: {"data": [_group(_split("2026-11-05", 10))], "meta": {"pagination": {"current_page": 1, "total_pages": 2}}},
        2: {"data": [_group(_split("2026-11-06", 15))], "meta": {"pagination": {"current_page": 2, "total_pages": 2}}},
    }
    monkeypatch.setattr(client, "_get", lambda path, params=None: pages[params["page"]])
    assert client.net_spend("281", date(2026, 11, 1), date(2026, 11, 21)) == 25.0
