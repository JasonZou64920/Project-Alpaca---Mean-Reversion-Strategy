# Changelog

Authors: Jason Zou and Ignacio Lopez Amartino

All notable changes to the strategy and system, most recent first.
Returns are on a $100k paper book. "Net" means net of the modeled
transaction costs introduced in 2.0 (5 bps per stock fill).

## [2.0] - 2026-07-12 - The profitability overhaul

The 1.x strategy lost money in every window tested: -7.6% over the
Jan-Jul 2026 half-year before costs, roughly -26% over the full
Jul 2025 - Jul 2026 year after costs. A multi-stage empirical diagnostic
(trade-level autopsy, formal mean-reversion tests, factor analysis,
regime bucketing, walk-forward validation - every headline number
independently recomputed) found three root causes and led to the changes
below. Result: **+1.5% net on the same half-year that previously lost
-7.6%, +1.1% net on a held-out prior half-year the parameters never saw,
+1.8% net over the full year with a -1.4% max drawdown.**

### What the diagnostic found

1. **The raw entry signal had no edge.** After a -2 sigma z-score cross,
   forward returns over the next 1-20 bars were flat to negative (hit rate
   below 50% at every horizon, n=237 events). After a +2 sigma cross,
   prices kept RISING for 5-10 bars - shorts sold straight into
   continuation. Measured reversion half-lives on these names are 40-98
   trading days, 14-34x the 20-bar signal window.
2. **The -5% stop-loss was the loss engine, not the safety net.** 39 stops
   destroyed -$16,159 - more than twice the strategy's entire net loss -
   filling at -6.1% on average because hourly stop checks gap through the
   level overnight. 59% of stopped positions recovered immediately after
   the stop fired.
3. **The 5-name universe is really ~2 macro bets.** One principal
   component explains half the book's return variance (LYB/DVN/HAL are one
   oil bet; LEN is a rates bet). When oil rallied +52% in H1 2026, every
   z-score pinned at the same extreme simultaneously and the book
   concentrated exactly when it should have diversified.

### Added

- **Trend regime filter** (`strategy.trend_lookback`, default 100 bars):
  entries only fade dislocations that are pullbacks *within* the larger
  trend - long only above the 100-bar SMA, short only below it. This is
  the single load-bearing change: on the held-out Jul 2025 - Jan 2026
  window, every tested configuration with the filter on was profitable
  and every one with it off lost money, because it cuts stop-loss hits
  from 37 to 1 by refusing to fight real repricings.
- **Bail-out exit** (`strategy.bail_z`, default 3.0): if a held position's
  z-score blows out another full sigma against it, the reversion thesis is
  broken - exit at a small loss (bails averaged -1.2%) instead of riding
  to the price stop (stops averaged -6.1%).
- **Transaction cost model** (`execution.cost_bps` = 5,
  `execution.crypto_cost_bps` = 25): backtests no longer fill for free;
  every reported number is net of realistic frictions.
- **`strategy.allow_shorts` kill-switch**: unfiltered shorts lost -$3,707
  (they sold into post-cross continuation); trend-gated shorts earn their
  keep and the switch defaults to on, but the lever now exists and is
  tested.
- 7 new tests (28 total): trend gating, bail exit, shorts switch, cost
  model.

### Changed

- **Entry threshold 2.0 -> 2.5 sigma.** Marginal dislocations
  (2.0 < |z| < 2.5) had no better expectancy than deep ones and doubled
  the trade count. Note: 2.0-2.5 all sit on the profitable plateau once
  the trend filter is on - the exact value is not load-bearing, and 2.5
  is kept because it is the only setting positive in both halves of the
  tested year.
- README and strategy write-up rewritten to match the system as it now is,
  including honest statistical caveats (~40 trades/yr; the edge is real
  in both halves but thin - this demonstrates risk architecture, not
  proven alpha).

### Removed

- **BTC/USD and ETH/USD removed from the default universe** (config only -
  full crypto support remains in code, one line to re-enable). Over the
  tested year the crypto sleeve made +$221 gross and paid ~$1,860 in fees
  at Alpaca's ~25 bps taker rate; ETH alone was the single worst name in
  the 1.x book (-$3,375, 45% of the total loss).

### Tested and rejected (kept for the record)

Slower z lookbacks (40/60 bars) - beat the raw baseline but lose once the
trend filter exists; cross-sectional demeaned z - removes factor risk
beautifully but no net alpha yet; rank-based dollar-neutral - churns
itself to death on switch exits; 40-bar time stop - null, no trade ever
lived that long; daily-clock confirmation - anti-selects into multi-day
falling knives; long-only - correct without the trend filter, dominated
with it.

## [1.1] - 2026-07-12 - Universe change

- Replaced the 10 mega-cap universe (AAPL, MSFT, AMZN, GOOGL, META, NVDA,
  TSLA, JPM, V, XOM) with 5 cyclical names: **MOS, LEN, LYB, DVN, HAL**
  (fertilizer, homebuilding, petrochemicals, oil E&P, oilfield services).
- Consequence, discovered immediately: the 6-month backtest went from
  -1.1% (mega-caps) to -7.6% (cyclicals) under identical rules. Cyclical
  commodity names trend harder and longer than mega-caps, which is
  exactly what breaks naive mean reversion - this is what motivated the
  2.0 diagnostic.

## [1.0] - original system

- Hourly z-score mean reversion (20-bar lookback, enter at |z| > 2, exit
  at |z| < 0.5), vol-scaled sizing, 5% stop, 15% per-asset / 100% gross
  caps, one shared engine for backtest and live paper trading, Streamlit
  dashboard, SQLite + logging, frictionless backtest fills.
- 10 mega-caps + BTC/ETH: -1.1% over Jan-Jul 2026, 470 trades, 63% hit
  rate, -7.5% max drawdown.
