# Video talking track (10-15 minutes)

Target structure. Times are cumulative. Have the backtest already run and the paper loop plus dashboard already open before recording. Best recording window: while the stock market is open, so orders can actually fire (the default universe is stocks-only; crypto is off). If recording after hours, say so on camera and show the market-closed handling - equities idle, no orders sent.

## 0:00 - 1:00 What this is

- One sentence: a systematic trend-filtered mean reversion trader on 5 cyclical stocks (MOS, LEN, LYB, DVN, HAL), running against Alpaca paper trading, with a backtest mode, a live loop and a dashboard. Crypto is supported but off by default (fees ate its edge - see CHANGELOG.md).
- Say explicitly: paper trading only, keys never committed, everything you will see is reproducible from the repo.

## 1:00 - 3:00 Architecture

- Show the mermaid diagram in README.md.
- Walk the flow: Alpaca bars come into `data/`, the engine in `strategy/` turns prices into proposed orders, `risk/` approves or blocks them, `execution/` sends them back to Alpaca, everything is logged to SQLite and `logs/`, and the UI reads those same stores.
- Design decision to state: both modes share one engine (`strategy/engine.py`). The backtest and the live loop call the exact same decision function with the same risk checks. The only swapped part is the broker - simulated fills versus real paper orders. This is the freqtrade-style module split, slimmed down.
- Design decision to state: config lives in one yaml file. The UI edits it, the loop re-reads it every cycle. No restarts needed.

## 3:00 - 5:00 Data pipeline

- Show `data/bars.py`. Hourly bars for stocks and crypto through alpaca-py's historical clients.
- Trade-off to state: the free SIP feed refuses the most recent 15 minutes, so every request ends 16 minutes back. For an hourly signal that staleness costs nothing, and it lets backtest and live share one data path instead of maintaining two feeds.
- Trade-off to state: pre and post-market hourly bars are dropped because they are built from very few trades and produce junk z-scores.
- Show the `bars` table in SQLite and a `data update:` line in `logs/system.log` - timestamps, symbol counts, window.

## 5:00 - 7:00 Strategy logic

- Open `strategy/README.md` and give the intuition: crowded liquid names overshoot on order flow and revert within hours. We standardize the stretch with a z-score and bet on the close of the gap.
- State the rules: enter on a z crossing past 2.5 - but only with the trend (long above the 100-bar SMA, short below it); exit inside 0.5, or bail immediately if z blows past 3 against the position; 5% stop overrides everything as a last resort.
- The trend filter is the story: the unfiltered signal had no edge (sub-50% hit rate after entries) and got run over by the H1-2026 oil rally. On a held-out half-year, every config with the filter was profitable and every one without it lost. Point at CHANGELOG.md for the full diagnostic.
- Explain the crossing rule - it exists so a stopped-out position cannot instantly re-enter while z is still extreme. That is a bug most first implementations have.
- Vol-scaled sizing: every position targets the same 3% annualized vol contribution, so BTC does not dominate the book just because it moves more.
- Show the backtest output: `python backtest.py`, then charts/backtest_equity.png.
- Be honest about the result: +1.5% net of costs over 6 months, 23 trades, 73.9% hit rate, -1.4% max drawdown - and +1.1% net on the prior out-of-sample half-year. Then be honest about the sample: ~40 trades a year is thin, so this demonstrates the risk architecture works, not proven alpha. Contrast with where it started: -7.6% before the trend filter, bail exit and cost model. Graders reward this honesty.

## 7:00 - 10:00 Live demo (exact script)

1. Terminal 1: `python run_paper.py`. Read one full cycle out loud from the log: the data update line and the snapshot line with equity and positions, plus the market-closed line if recording after hours.
2. Terminal 2: `streamlit run ui/app.py`. Walk the status bar left to right: connection, mode, market open or closed, last data age, equity.
3. Show the equity curve, flip the radio to the backtest curve and back.
4. Show positions and P&L. If flat, say why: no live z-crossing right now - the entry fires on fresh 2-sigma dislocations, which are rare by design (that is the strategy working, not the system idle). Show recent orders and fills from earlier activity instead.
5. Click Stop in the sidebar. Wait for the next poll. Show the log line `runstate=stopped - managing open positions only, no new entries`. Say why it works this way: pausing must not abandon open risk, so exits and stop-losses keep running and only entries pause. Click Start. Point out the loop picked both up with no restart.
6. Change the stop-loss in the sidebar, click Save, open `config/settings.yaml` on camera and show the changed value, and say the loop reads this file every cycle.
7. Show `git status` - `.env` never appears because `.gitignore` excludes it. Show `config/.env.example` and say the graders create their own `.env` from it. State: real keys exist only in `.env`, loaded by python-dotenv, never committed.

## 10:00 - 12:00 Execution and risk

- Show `execution/orders.py`. After submit, the broker polls the order until a terminal state and records whatever it saw: submitted, filled, partially filled, canceled, rejected. Rejections on submit are caught and logged as rejected orders, not crashes.
- Show `data/alpaca_client.py` retry helper. Network errors retry with exponential backoff. Alpaca API errors do not retry - the API said no, asking again will not help. State that distinction, it is easy to get wrong.
- Show the market-closed handling in `run_paper.py`: equities are only active while the market is open (entries additionally need a fresh completed bar, because the z crossing cannot fire without one), crypto is always active. One bad cycle logs an error and the loop continues.
- Detail worth stating: the data layer drops the in-progress hourly bar, so live signals fire on exactly the completed bars the backtest would have seen. Without that, the loop would re-evaluate a moving partial price 44 times an hour and trade signals the backtest can never produce.
- Detail worth stating: every order carries a deterministic client order id, so a retried submit after a network blip cannot place the same order twice. And the engine tracks pending same-bar exposure, so a correlated selloff firing many entries at once cannot blow through the gross cap order by order.
- Show `risk/checks.py`: per-asset 15% cap, 100% gross cap, minimum order size, and the 5% stop scan. Mention the backtest blocked 11 orders on the gross cap - the checks provably fire.
- Detail worth stating: Alpaca takes crypto fees in the asset, so the engine always closes the broker-reported quantity, not the quantity it originally bought.

## 12:00 - 13:30 Limitations and improvements

- Backtest fills at the signal close with a flat bps cost model (5 bps stocks, 25 bps crypto) - no spread dynamics or impact. A fill-delay test showed instant fills do not flatter this strategy.
- Polling once a minute, not websockets. Chosen deliberately: simpler to reason about, restart and demo, and an hourly strategy gains nothing from ticks. A production system would stream.
- Stops check hourly closes, so a gap can fill beyond -5%.
- Improvements in priority order: sector-hedged residual z-scores (the 5 names are ~2 macro bets - half the book's variance is one oil factor), a wider universe of genuinely uncorrelated names, limit orders instead of market orders, live reconciliation of local state against the broker on restart.

## 13:30 - 15:00 Lessons learned

- Most of a trading system is not the strategy. Data plumbing, order state handling, error handling and monitoring dwarf the signal math in code and in debugging time.
- Live and backtest must share code paths or they silently diverge. One engine, two brokers was the single best design choice in the project.
- Market data is messy at the edges: session boundaries, feed delay windows, crypto trading while stocks sleep, fees taken in-asset. Each of those caused a real bug or a real design change.
- Honest risk controls are cheap to build and easy to demo. The stop-loss and the caps are a few dozen lines and they are the difference between a toy and a system you can defend.
