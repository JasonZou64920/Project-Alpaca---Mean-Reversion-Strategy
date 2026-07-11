# entry and exit decisions on fixed z-scores
import pandas as pd

from strategy import mean_reversion as mr

CRYPTO = {"BTC/USD"}


def _decide(z_now, z_prev, positions):
    return mr.decide(pd.Series(z_now), pd.Series(z_prev), positions, CRYPTO,
                     entry_z=2.0, exit_z=0.5)


def test_long_entry_on_downward_cross():
    actions = _decide({"AAPL": -2.5}, {"AAPL": -1.5}, {})
    assert actions == [("AAPL", "open_long", -2.5)]


def test_no_reentry_without_a_fresh_cross():
    # z was already past the band last bar (e.g. right after a stop-loss);
    # staying extreme must not immediately re-open the position
    assert _decide({"AAPL": -2.6}, {"AAPL": -2.5}, {}) == []


def test_short_entry_on_upward_cross_stocks_only():
    actions = _decide({"AAPL": 2.5, "BTC/USD": 2.5},
                      {"AAPL": 1.0, "BTC/USD": 1.0}, {})
    assert actions == [("AAPL", "open_short", 2.5)]   # crypto never shorts


def test_exit_when_z_reverts_inside_band():
    actions = _decide({"AAPL": -0.3}, {"AAPL": -0.6}, {"AAPL": 10.0})
    assert actions == [("AAPL", "close", -0.3)]
    # still stretched -> keep holding
    assert _decide({"AAPL": -1.2}, {"AAPL": -1.5}, {"AAPL": 10.0}) == []


def test_nan_z_is_ignored():
    assert _decide({"AAPL": float("nan")}, {"AAPL": -1.0}, {}) == []


def test_allow_shorts_false_blocks_stock_shorts_but_not_longs_or_exits():
    actions = mr.decide(pd.Series({"AAPL": 2.5, "MSFT": -2.5}),
                        pd.Series({"AAPL": 1.0, "MSFT": -1.0}), {}, CRYPTO,
                        entry_z=2.0, exit_z=0.5, allow_shorts=False)
    assert actions == [("MSFT", "open_long", -2.5)]   # short suppressed, long fine
    # an existing short (e.g. opened before the setting changed) still exits
    actions = mr.decide(pd.Series({"AAPL": 0.2}), pd.Series({"AAPL": 0.8}),
                        {"AAPL": -10.0}, CRYPTO,
                        entry_z=2.0, exit_z=0.5, allow_shorts=False)
    assert actions == [("AAPL", "close", 0.2)]


def test_trend_filter_gates_entries_by_direction():
    trend = pd.Series({"AAPL": -1.0, "MSFT": 1.0})   # AAPL below its long SMA
    actions = mr.decide(pd.Series({"AAPL": -2.5, "MSFT": -2.5}),
                        pd.Series({"AAPL": -1.0, "MSFT": -1.0}), {}, CRYPTO,
                        entry_z=2.0, exit_z=0.5, trend_now=trend)
    assert actions == [("MSFT", "open_long", -2.5)]   # no dip-buying in a downtrend


def test_bail_exit_when_z_blows_out_against_position():
    actions = mr.decide(pd.Series({"AAPL": -3.6}), pd.Series({"AAPL": -3.2}),
                        {"AAPL": 10.0}, CRYPTO,
                        entry_z=2.0, exit_z=0.5, bail_z=3.5)
    assert actions == [("AAPL", "bail", -3.6)]
