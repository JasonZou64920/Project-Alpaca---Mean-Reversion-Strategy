# the shared engine step on fixed synthetic inputs
import pandas as pd

import config
from strategy import engine

CRYPTO = {"BTC/USD"}


def _cfg():
    cfg = config.load()
    cfg["strategy"]["entry_z"] = 2.0
    cfg["strategy"]["exit_z"] = 0.5
    cfg["strategy"]["vol_target"] = 0.03
    cfg["risk"] = {"max_position_pct": 0.15, "max_gross_pct": 1.00, "stop_loss_pct": 0.05}
    cfg["execution"] = {"poll_seconds": 60, "min_order_notional": 200}
    return cfg


def test_gross_cap_holds_when_many_entries_fire_on_one_bar():
    # 10 stocks all cross z < -2 on the same bar; each alone sizes to the 15%
    # cap, so unchecked the batch would open 150% gross - the cap must stop
    # the batch around 100%, counting same-bar pending orders
    symbols = [f"S{i}" for i in range(10)]
    z_now = pd.Series({s: -2.5 for s in symbols})
    z_prev = pd.Series({s: -1.0 for s in symbols})
    vol = pd.Series({s: 0.10 for s in symbols})   # low vol -> sizes want the cap
    prices = pd.Series({s: 100.0 for s in symbols})

    orders, rejections = engine.step(z_now, z_prev, vol, prices, set(symbols),
                                     {}, {}, 100_000, _cfg(), CRYPTO)

    gross = sum(o["qty"] * 100.0 for o in orders)
    assert gross <= 100_000 * 1.001
    assert len(orders) < len(symbols)          # some entries had to be blocked
    assert any("gross cap" in r[3] for r in rejections)


def test_entries_pause_but_exits_still_fire_when_stopped():
    z_now = pd.Series({"A": -2.5, "B": -0.2})
    z_prev = pd.Series({"A": -1.0, "B": -0.8})
    vol = pd.Series({"A": 0.20, "B": 0.20})
    prices = pd.Series({"A": 100.0, "B": 100.0})
    positions = {"B": 50.0}
    entries = {"B": 99.0}

    orders, rejections = engine.step(z_now, z_prev, vol, prices, {"A", "B"},
                                     positions, entries, 100_000, _cfg(), CRYPTO,
                                     allow_entries=False)

    assert [o["symbol"] for o in orders] == ["B"]       # the exit still runs
    assert orders[0]["reason"] == "exit"
    assert any(r[3] == "entries paused" for r in rejections)


def test_stop_loss_beats_exit_and_only_fires_once():
    # long from 100, price now 94: the stop fires and the |z| < 0.5 exit for
    # the same symbol must not produce a second closing order
    z_now = pd.Series({"A": -0.1})
    z_prev = pd.Series({"A": -0.3})
    vol = pd.Series({"A": 0.20})
    prices = pd.Series({"A": 94.0})

    orders, _ = engine.step(z_now, z_prev, vol, prices, {"A"},
                            {"A": 100.0}, {"A": 100.0}, 100_000, _cfg(), CRYPTO)

    assert len(orders) == 1
    assert orders[0]["reason"] == "stop_loss"
    assert orders[0]["side"] == "sell"
