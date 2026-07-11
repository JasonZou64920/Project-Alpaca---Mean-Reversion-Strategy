# hourly OHLCV bars from Alpaca for stocks and crypto
from datetime import datetime, timedelta, timezone

import pandas as pd
from alpaca.data.enums import Adjustment, DataFeed
from alpaca.data.requests import CryptoBarsRequest, StockBarsRequest
from alpaca.data.timeframe import TimeFrame

from data import alpaca_client
from data.logs import get_logger

log = get_logger("data")

COLUMNS = ["symbol", "ts", "open", "high", "low", "close", "volume"]


def _tidy(barset):
    """BarSet -> one row per (symbol, hour) with ohlcv columns."""
    df = barset.df
    if df.empty:
        return pd.DataFrame(columns=COLUMNS)
    df = df.reset_index().rename(columns={"timestamp": "ts"})
    return df[COLUMNS]


def _regular_hours(df):
    """Keep stock bars that start 9:00-15:00 ET (the 9:00 bar holds the open).

    Alpaca hourly bars include thin pre/post-market bars built from very few
    trades. Those prices are noisy and would throw spurious z-scores, so the
    strategy only ever sees regular-session bars.
    """
    if df.empty:
        return df
    hour = df["ts"].dt.tz_convert("America/New_York").dt.hour
    return df[(hour >= 9) & (hour <= 15)]


def history(stocks, crypto, days):
    """Hourly bars for the whole universe as one tidy frame.

    The end is clamped 16 minutes back because the free SIP feed refuses the
    most recent 15 minutes. For an hourly strategy that staleness is harmless,
    and it lets backtest and paper mode share the exact same data path.
    """
    end = datetime.now(timezone.utc) - timedelta(minutes=16)
    start = end - timedelta(days=days)
    frames = []

    if stocks:
        req = StockBarsRequest(symbol_or_symbols=list(stocks), timeframe=TimeFrame.Hour,
                               start=start, end=end, adjustment=Adjustment.ALL,
                               feed=DataFeed.SIP)
        client = alpaca_client.stock_client()
        bars = alpaca_client.retry(lambda: client.get_stock_bars(req), what="stock bars")
        frames.append(_regular_hours(_tidy(bars)))

    if crypto:
        req = CryptoBarsRequest(symbol_or_symbols=list(crypto), timeframe=TimeFrame.Hour,
                                start=start, end=end)
        client = alpaca_client.crypto_client()
        bars = alpaca_client.retry(lambda: client.get_crypto_bars(req), what="crypto bars")
        frames.append(_tidy(bars))

    tidy = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(columns=COLUMNS)
    if len(tidy):
        # drop bars still forming: a bar stamped 20:00 fetched at 20:44 is
        # partial and its close moves on every poll - the strategy must only
        # ever see completed hours, in live mode exactly as in the backtest
        tidy = tidy[tidy["ts"] + pd.Timedelta(hours=1) <= end]
    log.info(f"data update: {len(tidy)} bars for {tidy['symbol'].nunique() if len(tidy) else 0} "
             f"symbols, {days}d window")
    return tidy


def closes(tidy):
    """Wide close-price matrix: one row per hour, one column per symbol."""
    if tidy.empty:
        return pd.DataFrame()
    return tidy.pivot(index="ts", columns="symbol", values="close").sort_index()
