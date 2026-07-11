# backtest mode: replay 6 months of hourly bars through the shared engine
import os

from dotenv import load_dotenv

load_dotenv()

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

import config
from data import bars, store
from data.logs import get_logger
from execution.orders import SimBroker
from strategy import engine

log = get_logger("backtest")

HERE = os.path.dirname(os.path.abspath(__file__))
CHARTS = os.path.join(HERE, "charts")
CAPITAL = 100_000


def run():
    cfg = config.load()
    stocks = cfg["tickers"]["stocks"]
    crypto = set(cfg["tickers"]["crypto"])
    days = int(cfg["backtest"]["months"] * 30.4)

    tidy = bars.history(stocks, sorted(crypto), days)
    store.save_bars(store.connect(), tidy)   # same data logging path as paper mode
    px = bars.closes(tidy)
    log.info(f"backtest: {len(px)} hourly rows, {px.shape[1]} symbols, "
             f"{px.index[0]} to {px.index[-1]}")

    inp = engine.inputs(px, cfg, crypto)
    broker = SimBroker(CAPITAL, cost_bps=cfg["execution"].get("cost_bps", 0),
                       crypto_cost_bps=cfg["execution"].get("crypto_cost_bps"))
    equity_ts, equity_val, rejections = [], [], 0

    for i in range(1, len(px)):
        ts = px.index[i]
        row = px.iloc[i]
        active = set(row.index[row.notna()])
        prices = inp["prices"].iloc[i]
        trend_now = inp["trend"].iloc[i] if inp["trend"] is not None else None
        orders, rejects = engine.step(inp["z"].iloc[i], inp["z"].iloc[i - 1],
                                      inp["vol"].iloc[i], prices, active,
                                      broker.positions, broker.entries,
                                      broker.equity(prices), cfg, crypto,
                                      trend_now=trend_now)
        for o in orders:
            broker.submit(o["symbol"], o["side"], o["qty"], float(prices[o["symbol"]]),
                          ts=ts, reason=o["reason"])
        rejections += len(rejects)
        equity_ts.append(ts)
        equity_val.append(broker.equity(prices))

    eq = pd.Series(equity_val, index=equity_ts, name="equity")
    trades = pd.DataFrame(broker.trades)
    drawdown = eq / eq.cummax() - 1

    stats = {
        "start": str(eq.index[0]), "end": str(eq.index[-1]),
        "cumulative_pnl": eq.iloc[-1] - CAPITAL,
        "total_return": eq.iloc[-1] / CAPITAL - 1,
        "max_drawdown": drawdown.min(),
        "trade_count": len(trades),
        "hit_rate": float((trades["ret"] > 0).mean()) if len(trades) else float("nan"),
        "open_positions_at_end": len(broker.positions),
        "orders_blocked_by_risk": rejections,
        "transaction_costs_paid": broker.costs_paid,
    }

    os.makedirs(CHARTS, exist_ok=True)
    eq.to_csv(os.path.join(CHARTS, "backtest_equity.csv"))
    trades.to_csv(os.path.join(CHARTS, "backtest_trades.csv"), index=False)
    pd.Series(stats).to_csv(os.path.join(CHARTS, "backtest_stats.csv"))

    # equity curve with drawdown underneath, quantconnect-report style
    fig, ax = plt.subplots(2, 1, figsize=(12, 7), sharex=True,
                           gridspec_kw={"height_ratios": [3, 1]})
    ax[0].plot(eq.index, eq, linewidth=1)
    ax[0].set_title("Mean Reversion - Backtest Equity ($100k start)")
    ax[0].set_ylabel("portfolio value ($)")
    ax[1].fill_between(drawdown.index, drawdown, 0, color="tab:red", alpha=0.5)
    ax[1].set_ylabel("drawdown")
    fig.tight_layout()
    fig.savefig(os.path.join(CHARTS, "backtest_equity.png"), dpi=120)
    plt.close(fig)

    print()
    for k, v in stats.items():
        print(f"{k:>24}: {v:,.4f}" if isinstance(v, float) else f"{k:>24}: {v}")
    log.info(f"backtest done: pnl ${stats['cumulative_pnl']:,.0f}, "
             f"{stats['trade_count']} trades, hit rate {stats['hit_rate']:.2%}, "
             f"max dd {stats['max_drawdown']:.2%}")
    print(f"\ncharts and csvs written to {CHARTS}")
    return stats


if __name__ == "__main__":
    run()
