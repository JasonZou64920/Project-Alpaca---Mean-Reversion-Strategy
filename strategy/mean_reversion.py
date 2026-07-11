# cross-sectional mean reversion on hourly bars - see strategy/README.md
import numpy as np
import pandas as pd

# hourly bars per year, used to annualize realized vol for sizing
BARS_PER_YEAR_STOCK = 252 * 7    # 7 regular-session hourly bars a day
BARS_PER_YEAR_CRYPTO = 365 * 24  # crypto trades around the clock


def zscore(closes, lookback=20):
    """Rolling z-score of each price against its own trailing mean.

    z = (price - 20-bar mean) / 20-bar std. Negative z means the price is
    stretched below its recent average, positive z means stretched above.
    """
    mean = closes.rolling(lookback, min_periods=lookback).mean()
    std = closes.rolling(lookback, min_periods=lookback).std()
    return (closes - mean) / std.replace(0, np.nan)


def annual_vol(closes, crypto_symbols, lookback=20):
    """Annualized realized vol per symbol from hourly returns.

    Stocks and crypto get different annualization factors because crypto
    prints ~24/7 while stocks only print during the regular session.
    """
    vol = closes.pct_change().rolling(lookback, min_periods=lookback).std()
    factor = pd.Series({s: np.sqrt(BARS_PER_YEAR_CRYPTO if s in crypto_symbols
                                   else BARS_PER_YEAR_STOCK) for s in closes.columns})
    return vol * factor


def size_notional(equity, ann_vol, vol_target, max_position_pct):
    """Vol-scaled sizing: riskier assets get less money.

    notional = equity * vol_target / ann_vol, so every position contributes
    roughly the same vol_target of annualized volatility to the book. A 25%
    vol stock gets ~12% of equity, a 60% vol coin gets ~5%. Capped at
    max_position_pct of equity, and 0 if vol is missing or zero.
    """
    if ann_vol is None or not np.isfinite(ann_vol) or ann_vol <= 0:
        return 0.0
    return float(min(equity * vol_target / ann_vol, equity * max_position_pct))


def decide(z_now, z_prev, positions, crypto_symbols, entry_z=2.0, exit_z=0.5,
           trend_now=None, bail_z=None, allow_shorts=True):
    """Latest z-scores -> desired actions per symbol.

    Entries fire on a crossing (z was inside the band last bar, outside now),
    not on the level alone - otherwise a position closed by a stop-loss would
    re-open immediately on the very next bar while z is still extreme.
    Crypto never opens short because Alpaca does not support shorting crypto.
    allow_shorts=False disables shorts for stocks too: measured over Jul 2025 -
    Jul 2026, prices kept rising for 5-10 bars after a +2 sigma up-cross, so
    shorting rips at this horizon sold into continuation, and the stock short
    book lost -$3,707 while stock longs broke even.
    Exits fire when z has come back inside +/- exit_z, meaning the reversion
    the trade was betting on has mostly happened.

    Two optional filters guard against the strategy's worst case - a price that
    keeps trending away from its mean and rides to the hard -5% stop:

    - trend_now: a per-symbol sign (+1 uptrend / -1 downtrend / 0 or NaN flat)
      of price vs a long moving average. When supplied, longs (buy the dip) are
      only taken in an uptrend and shorts (sell the rip) only in a downtrend, so
      the strategy fades pullbacks with the bigger trend instead of catching
      falling knives. None disables the filter.
    - bail_z: when a held position's z blows out further past entry to this
      magnitude, the reversion thesis has failed - close early at a small loss
      instead of waiting for the -5% price stop. None disables it.
    """
    def trend_sign(symbol):
        if trend_now is None:
            return None
        s = trend_now.get(symbol, np.nan)
        return s if np.isfinite(s) else 0.0

    actions = []
    for symbol in z_now.index:
        zv, zp = z_now[symbol], z_prev[symbol]
        if not np.isfinite(zv) or not np.isfinite(zp):
            continue
        qty = positions.get(symbol, 0.0)
        if qty == 0:
            tr = trend_sign(symbol)
            if zp >= -entry_z and zv < -entry_z and (tr is None or tr >= 0):
                actions.append((symbol, "open_long", zv))
            elif (allow_shorts and zp <= entry_z and zv > entry_z
                  and symbol not in crypto_symbols and (tr is None or tr <= 0)):
                actions.append((symbol, "open_short", zv))
        elif abs(zv) < exit_z:
            actions.append((symbol, "close", zv))
        elif bail_z is not None and ((qty > 0 and zv <= -bail_z)
                                     or (qty < 0 and zv >= bail_z)):
            actions.append((symbol, "bail", zv))
    return actions
