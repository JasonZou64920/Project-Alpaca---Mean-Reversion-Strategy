# Strategy: trend-filtered mean reversion

Authors: Jason Zou and Ignacio Lopez Amartino

## The idea

Liquid large caps and major crypto pairs are crowded, heavily arbitraged assets. Over horizons of a few hours their prices often overshoot on order-flow imbalance - a large seller finishing a position, an overreaction to a headline, an index rebalance - and then drift back once the pressure passes. The strategy bets on that drift back. It does not predict direction from scratch. It waits for a price to be unusually far from its own recent average and bets the gap closes.

## The signal

For each asset, on hourly bars:

```
z = (close - 20-bar rolling mean) / 20-bar rolling std
```

The z-score standardizes "how stretched is this price" so one threshold works across a $60,000 coin and a $150 stock. 20 hourly bars is roughly three trading days for a stock and under a day for crypto - long enough to define a meaningful local mean, short enough that the mean tracks the current price regime instead of last quarter's.

## Rules and why the thresholds

- Enter long when z crosses below -2.5. Enter short when z crosses above +2.5 (stocks only).
  A 2+ standard deviation stretch is rare under normal conditions, so entries fire on genuine dislocations instead of noise. Tighter thresholds trade far more often and mostly collect noise. Wider ones almost never trade. (2.5 was chosen on the Jan-Jul 2026 window; 2.0-2.5 all sit on the profitable plateau once the trend filter is on, so the exact value is not load-bearing.)
- Entries require a crossing, not a level. z had to be inside the band on the previous bar and outside now.
  This prevents a position that was just closed by a stop-loss from immediately re-opening on the next bar while z is still extreme. The signal must reset and stretch again before the strategy will touch that asset.
- Trend filter: only buy dips when price is above its 100-bar moving average, only short rips when below it (`trend_lookback`, 0 disables).
  This is the single most valuable rule in the system. A z-score entry cannot tell an overshoot (noise, will revert) from a repricing (information, will continue), and formal tests show these tickers do not reliably mean-revert at the hourly horizon on their own. The long MA is a cheap regime proxy: fading pullbacks with the larger trend keeps the reversion bet, fading against it is catching a falling knife. Out-of-sample (Jul 2025 - Jan 2026, never used for tuning), every tested configuration with this filter on was profitable and every one with it off lost money - it cuts stop-loss hits from 37 to 1.
- Exit when |z| moves back inside 0.5.
  By then most of the reversion the trade was betting on has happened. Waiting for exactly z equal to 0 risks giving back profit while the last small drift completes. Exiting earlier leaves too much of the move on the table.
- Bail-out exit: if a held position's z blows out past 3.0 against it, close immediately (`bail_z`, null disables).
  When the dislocation deepens by another full sigma after entry, the reversion thesis is broken - take the small loss (bail exits averaged -1.2%) before the price stop takes a big one (stops averaged -6.1%, because hourly gap-through overshoots the -5% line).
- Crypto never opens short because Alpaca does not support shorting crypto. Stock shorts can be disabled with `allow_shorts: false`; unfiltered shorts sold into 5-10 bars of continuation after every +2 sigma up-cross and lost money, but gated by the trend filter they add about a point a year and stay on.
- A 5% stop-loss per position overrides everything.
  The worst case for mean reversion is a price that keeps trending away from its mean - the stretch was information, not noise. The stop caps that scenario. It is deliberately a last resort: it evaluates on hourly closes, so overnight and weekend gaps fill past -5% (worst observed -12.7%), and in the unfiltered strategy stops destroyed more than twice the total loss. The trend filter and bail exit exist to keep positions from ever reaching it - in the filtered strategy it fired twice in a year.

## Position sizing

Sizes scale inversely with realized volatility:

```
notional = equity * vol_target / annualized_vol
```

Each position targets the same volatility contribution (3% annualized by default). A 25% vol stock gets about 12% of equity. A 60% vol coin gets about 5%. Without this, BTC and ETH would dominate the book's risk simply because they move more. The per-asset notional is capped at 15% of equity regardless of how quiet the asset looks, because low measured vol can understate true risk.

## What breaks it

Trends. If prices trend hard, every entry is early and gets stopped. The unfiltered backtest showed exactly this shape: many small wins and a few -6% stops that more than consumed them. The trend filter above is the answer, and it is the one component of this system with out-of-sample evidence behind it.

A structural warning for this particular universe: MOS, LEN, LYB, DVN and HAL are all deep cyclicals. Three of them (LYB/DVN/HAL) are essentially one oil bet - about half the book's 3-year return variance is a single common factor, so the "5 names" behave like ~2 independent bets. When oil trends (it rallied 52% in H1 2026), all their z-scores pin at the same extreme at the same time and the book concentrates exactly when it should diversify. The per-name caps do not see this; only the trend filter stands the strategy down.
