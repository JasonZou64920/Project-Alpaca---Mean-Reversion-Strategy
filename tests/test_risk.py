# each risk check on fixed synthetic positions
from risk import checks

LIMITS = {"max_position_pct": 0.15, "max_gross_pct": 1.00,
          "stop_loss_pct": 0.05, "min_order_notional": 200}


def test_min_notional_check():
    ok, why = checks.check_order("AAPL", 100, {}, {}, 100_000, LIMITS)
    assert not ok and "min notional" in why


def test_per_asset_cap_check():
    positions = {"AAPL": 100.0}          # 100 shares at 100 = 10k held
    prices = {"AAPL": 100.0}
    # 4k more is fine (14k < 15k cap), 6k more breaches it
    ok, _ = checks.check_order("AAPL", 4_000, positions, prices, 100_000, LIMITS)
    assert ok
    ok, why = checks.check_order("AAPL", 6_000, positions, prices, 100_000, LIMITS)
    assert not ok and "per-asset cap" in why


def test_gross_cap_check():
    # book already at 96k gross (incl. a short - exposure is absolute)
    positions = {"AAPL": 500.0, "TSLA": -460.0}
    prices = {"AAPL": 100.0, "TSLA": 100.0, "MSFT": 100.0}
    ok, why = checks.check_order("MSFT", 10_000, positions, prices, 100_000, LIMITS)
    assert not ok and "gross cap" in why
    ok, _ = checks.check_order("MSFT", 3_000, positions, prices, 100_000, LIMITS)
    assert ok


def test_stop_loss_long_and_short():
    positions = {"LONG1": 10.0, "SHORT1": -10.0, "OK1": 10.0}
    entries = {"LONG1": 100.0, "SHORT1": 100.0, "OK1": 100.0}
    prices = {"LONG1": 94.9, "SHORT1": 105.1, "OK1": 96.0}
    hits = checks.stop_hits(positions, entries, prices, 0.05)
    assert set(hits) == {"LONG1", "SHORT1"}   # OK1 is down 4%, inside the stop


def test_stop_loss_ignores_flat_and_unpriced():
    positions = {"FLAT": 0.0, "NOPRICE": 10.0}
    entries = {"FLAT": 100.0, "NOPRICE": 100.0}
    hits = checks.stop_hits(positions, entries, {"FLAT": 50.0}, 0.05)
    assert hits == []
