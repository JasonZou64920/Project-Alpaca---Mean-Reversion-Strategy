# z-score math on fixed synthetic data
import numpy as np
import pandas as pd

from strategy import mean_reversion as mr


def test_zscore_known_values():
    # last 3 values are 2, 3, 4: mean 3, std 1 -> z of the 4 is exactly 1
    closes = pd.DataFrame({"A": [1.0, 2.0, 3.0, 4.0]})
    z = mr.zscore(closes, lookback=3)
    assert np.isclose(z["A"].iloc[-1], 1.0)


def test_zscore_symmetric():
    # a dip below the mean gives negative z, a spike above gives positive z
    base = [100.0] * 19
    dip = pd.DataFrame({"A": base + [90.0]})
    spike = pd.DataFrame({"A": base + [110.0]})
    assert mr.zscore(dip, 20)["A"].iloc[-1] < 0
    assert mr.zscore(spike, 20)["A"].iloc[-1] > 0


def test_zscore_warmup_is_nan():
    closes = pd.DataFrame({"A": np.linspace(100, 110, 30)})
    z = mr.zscore(closes, lookback=20)
    assert z["A"].iloc[:19].isna().all()
    assert np.isfinite(z["A"].iloc[19:]).all()


def test_zscore_flat_price_is_nan_not_inf():
    # constant prices have zero std - z must be NaN, never a divide-by-zero inf
    closes = pd.DataFrame({"A": [50.0] * 30})
    z = mr.zscore(closes, lookback=20)
    assert z["A"].iloc[-1] != z["A"].iloc[-1]   # NaN
