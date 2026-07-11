# one decision pass shared by backtest and paper mode
# both modes feed this the same inputs and route its orders through the same
# risk checks - the only difference between them is who fills the orders
import numpy as np
import pandas as pd

from risk import checks
from strategy import mean_reversion as mr


def inputs(closes, cfg, crypto_symbols):
    """Precompute the causal signal matrices once from a close-price matrix.

    The union hourly index has rows where only crypto trades, so each symbol's
    rolling stats are computed on its own bars (NaN hours dropped) and then
    aligned back. The forward-fill makes "the previous row's z" mean "z at this
    symbol's previous bar", which is what the crossing entry logic needs.
    Everything is a trailing rolling stat, so row t only ever uses data up to
    and including t - safe to precompute for a backtest with no lookahead.
    """
    p = cfg["strategy"]
    trend_lb = int(p.get("trend_lookback", 0) or 0)
    z, vol, trend = {}, {}, {}
    for s in closes.columns:
        col = closes[s].dropna().to_frame()
        z[s] = mr.zscore(col, p["lookback"])[s]
        vol[s] = mr.annual_vol(col, crypto_symbols, p["vol_lookback"])[s]
        if trend_lb > 0:
            ma = col[s].rolling(trend_lb, min_periods=trend_lb).mean()
            trend[s] = np.sign(col[s] - ma)   # +1 above long MA, -1 below
    out = {
        "z": pd.DataFrame(z).reindex(closes.index).ffill(),
        "vol": pd.DataFrame(vol).reindex(closes.index).ffill(),
        "prices": closes.ffill(),   # last known price (crypto trades while stocks sleep)
        "trend": None,
    }
    if trend_lb > 0:
        out["trend"] = pd.DataFrame(trend).reindex(closes.index).ffill()
    return out


def round_qty(symbol, qty, crypto_symbols):
    """Whole shares for stocks (shorts cannot be fractional), 6dp for crypto."""
    return round(qty, 6) if symbol in crypto_symbols else float(int(qty))


def step(z_now, z_prev, vol_now, prices, active, positions, entries, equity, cfg,
         crypto_symbols, allow_entries=True, trend_now=None):
    """One bar's decisions: stop-losses first, then strategy entries and exits.

    active is the set of symbols tradable on this pass - a symbol is only ever
    traded on a completed bar in a market that can fill the order.
    allow_entries=False (the UI Stop state) still closes and stops positions
    but opens nothing new, so risk keeps being managed while paused.
    Returns (orders, rejections): orders are dicts ready for a broker,
    rejections are (symbol, action, z, reason) for the log.
    """
    limits = cfg["risk"] | cfg["execution"]
    p = cfg["strategy"]
    orders, rejections = [], []
    closing = set()

    # book is a running copy of positions: every order accepted this bar
    # updates it, so the caps see pending same-bar exposure too - otherwise a
    # correlated selloff firing many entries at once could each individually
    # pass the gross cap and together blow far through it
    book = dict(positions)

    # 1. stop-losses override everything else
    live = {s: q for s, q in positions.items() if s in active}
    for symbol in checks.stop_hits(live, entries, prices, limits["stop_loss_pct"]):
        qty = positions[symbol]
        orders.append({"symbol": symbol, "side": "sell" if qty > 0 else "buy",
                       "qty": abs(qty), "reason": "stop_loss",
                       "z": float(z_now.get(symbol, np.nan))})
        closing.add(symbol)
        book[symbol] = 0.0

    # 2. strategy signals on tradable symbols only
    z_act = z_now[[s for s in z_now.index if s in active]]
    for symbol, action, zv in mr.decide(z_act, z_prev, positions, crypto_symbols,
                                        p["entry_z"], p["exit_z"], trend_now,
                                        p.get("bail_z"),
                                        p.get("allow_shorts", True)):
        if symbol in closing:
            continue
        if action in ("close", "bail"):
            qty = positions[symbol]
            orders.append({"symbol": symbol, "side": "sell" if qty > 0 else "buy",
                           "qty": abs(qty), "reason": "exit" if action == "close"
                           else "bail", "z": zv})
            book[symbol] = 0.0
            continue
        if not allow_entries:
            rejections.append((symbol, action, zv, "entries paused"))
            continue
        notional = mr.size_notional(equity, vol_now.get(symbol), p["vol_target"],
                                    limits["max_position_pct"])
        qty = round_qty(symbol, notional / prices[symbol], crypto_symbols)
        if qty <= 0:
            rejections.append((symbol, action, zv, "size rounds to zero"))
            continue
        notional = qty * prices[symbol]
        ok, why = checks.check_order(symbol, notional, book, prices, equity, limits)
        if not ok:
            rejections.append((symbol, action, zv, why))
            continue
        orders.append({"symbol": symbol, "side": "buy" if action == "open_long" else "sell",
                       "qty": qty, "reason": "entry_long" if action == "open_long"
                       else "entry_short", "z": zv})
        book[symbol] = book.get(symbol, 0.0) + (qty if action == "open_long" else -qty)
    return orders, rejections
