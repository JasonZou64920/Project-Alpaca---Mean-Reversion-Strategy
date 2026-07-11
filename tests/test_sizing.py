# vol-scaled position sizing on fixed numbers
import numpy as np
import pandas as pd

from strategy import mean_reversion as mr


def test_size_scales_inverse_to_vol():
    # 30% vol asset with a 3% target: 100k * 0.03 / 0.30 = 10k
    assert np.isclose(mr.size_notional(100_000, 0.30, 0.03, 0.15), 10_000)
    # half the vol -> double the notional (cap lifted so scaling is visible)
    assert np.isclose(mr.size_notional(100_000, 0.15, 0.03, 0.25), 20_000)


def test_size_respects_cap():
    # 10% vol would want 30k, but the 15% per-asset cap holds it at 15k
    assert np.isclose(mr.size_notional(100_000, 0.10, 0.03, 0.15), 15_000)


def test_size_zero_when_vol_missing():
    assert mr.size_notional(100_000, float("nan"), 0.03, 0.15) == 0.0
    assert mr.size_notional(100_000, 0.0, 0.03, 0.15) == 0.0
    assert mr.size_notional(100_000, None, 0.03, 0.15) == 0.0


def test_annual_vol_crypto_factor():
    # same price path, but the crypto column annualizes with 24/7 bars
    path = 100 * np.cumprod(1 + 0.01 * np.sin(np.arange(50)))
    closes = pd.DataFrame({"AAPL": path, "BTC/USD": path})
    vol = mr.annual_vol(closes, crypto_symbols={"BTC/USD"}, lookback=20)
    ratio = vol["BTC/USD"].iloc[-1] / vol["AAPL"].iloc[-1]
    expected = np.sqrt(mr.BARS_PER_YEAR_CRYPTO / mr.BARS_PER_YEAR_STOCK)
    assert np.isclose(ratio, expected)
