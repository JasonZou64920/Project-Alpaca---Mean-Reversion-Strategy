# paper trading mode: poll bars every minute, trade the shared engine's orders
# polling (not websockets) on purpose - one simple loop is easier to reason
# about, restart and demo, and an hourly strategy gains nothing from ticks
import argparse
import time
from datetime import datetime, timezone

from dotenv import load_dotenv

load_dotenv()

import config
from data import bars, store
from data.logs import get_logger
from execution.orders import PaperBroker
from strategy import engine

log = get_logger("paper")


def cycle(con, broker, cfg, allow_entries=True):
    """One polling pass: data -> signals -> risk -> orders -> snapshot.

    With allow_entries=False (the UI Stop state) the pass still runs exits,
    stop-losses and snapshots - pausing must not leave open positions
    unmanaged - it just opens nothing new.
    """
    crypto = set(cfg["tickers"]["crypto"])
    stocks = cfg["tickers"]["stocks"]
    now = datetime.now(timezone.utc)

    clock = broker.clock()
    market_open = bool(clock.is_open)
    store.set_control(con, "market_open", "open" if market_open else "closed")
    if not market_open:
        log.info("stock market closed - equities idle, crypto still trading")

    tidy = bars.history(stocks, sorted(crypto), days=30)
    store.save_bars(con, tidy)
    store.set_control(con, "last_update", now.isoformat())
    px = bars.closes(tidy)
    if len(px) < cfg["strategy"]["lookback"] + 2:
        log.warning(f"only {len(px)} bars - not enough history to trade yet")
        return

    inp = engine.inputs(px, cfg, crypto)
    prices = inp["prices"].iloc[-1]
    positions, entries = broker.positions()
    equity = float(broker.account().equity)

    # a position outside the configured universe has no prices and no signals -
    # the strategy cannot manage it, so say so instead of silently ignoring it
    for symbol in positions:
        if symbol not in crypto and symbol not in stocks:
            log.warning(f"position in {symbol} is outside the configured universe - "
                        "not managed by the strategy")

    # crypto is always tradable; stocks only while the market is open
    # (entries also need a fresh completed bar - without one, z cannot cross)
    active = crypto & set(px.columns)
    if market_open:
        active |= set(stocks) & set(px.columns)

    trend_now = inp["trend"].iloc[-1] if inp["trend"] is not None else None
    orders, rejects = engine.step(inp["z"].iloc[-1], inp["z"].iloc[-2],
                                  inp["vol"].iloc[-1], prices, active,
                                  positions, entries, equity, cfg, crypto,
                                  allow_entries=allow_entries, trend_now=trend_now)

    for symbol, action, zv, why in rejects:
        store.log_signal(con, now, symbol, zv, action, f"blocked: {why}")
        log.info(f"signal blocked: {action} {symbol} z={zv:.2f} ({why})")

    for o in orders:
        store.log_signal(con, now, o["symbol"], o["z"], o["reason"], "sent to broker")
        log.info(f"signal: {o['reason']} {o['symbol']} z={o['z']:.2f} qty={o['qty']}")
        result = broker.submit(o["symbol"], o["side"], o["qty"], ts=now,
                               reason=o["reason"])
        store.log_order(con, result)
        if result["filled_qty"] > 0:
            store.log_fill(con, now, result["order_id"], o["symbol"], o["side"],
                           result["filled_qty"], result["fill_price"])

    # position and P&L snapshot - this is what the UI charts
    details = broker.position_details()
    acct = broker.account()
    gross = sum(abs(d["market_value"]) for d in details.values())
    store.log_snapshot(con, now, float(acct.equity), float(acct.cash), gross, details)
    log.info(f"snapshot: equity ${float(acct.equity):,.0f}, "
             f"{len(details)} positions, gross ${gross:,.0f}")


def main():
    ap = argparse.ArgumentParser(description="Alpaca paper trading loop")
    ap.add_argument("--once", action="store_true", help="run one cycle and exit")
    args = ap.parse_args()

    con = store.connect()
    cfg = config.load()
    broker = PaperBroker()
    store.set_control(con, "mode", "paper")
    if store.get_control(con, "runstate") == "":
        store.set_control(con, "runstate", "running")
    log.info("paper loop starting (ctrl-c to stop)")

    while True:
        try:
            cfg = config.load()   # re-read every cycle so UI edits apply live
        except Exception as e:
            log.error(f"could not reload settings ({e}) - keeping previous values")
        try:
            if store.get_control(con, "runstate") == "stopped":
                log.info("runstate=stopped - managing open positions only, no new entries")
                cycle(con, broker, cfg, allow_entries=False)
            else:
                cycle(con, broker, cfg)
            store.set_control(con, "connection", "ok")
        except KeyboardInterrupt:
            raise
        except Exception as e:
            # one bad cycle (network blip, api hiccup) must not kill the loop
            store.set_control(con, "connection", f"error: {str(e)[:120]}")
            log.error(f"cycle failed: {e}")
        if args.once:
            break
        time.sleep(cfg["execution"]["poll_seconds"])


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        log.info("stopped by user")
