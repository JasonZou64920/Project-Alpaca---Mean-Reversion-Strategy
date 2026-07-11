# order manager - two brokers behind the same submit() interface
# SimBroker fills instantly for backtests, PaperBroker routes real orders to
# the Alpaca paper account and tracks their state until they settle
import time
from datetime import datetime, timezone

from alpaca.common.exceptions import APIError
from alpaca.trading.enums import AssetClass, OrderSide, TimeInForce
from alpaca.trading.requests import MarketOrderRequest

from data import alpaca_client
from data.logs import get_logger

log = get_logger("execution")

# order states we stop polling on - everything else is still in flight
TERMINAL = {"filled", "canceled", "rejected", "expired"}


class SimBroker:
    """Instant-fill broker for backtests.

    Fills at the price the caller passes in - the close of the bar the signal
    was computed on. That is fair (no lookahead): the signal only uses data up
    to that close, and the position earns the next bar's return, which is the
    move the strategy is trying to predict.

    cost_bps charges a proportional cost on every fill (half-spread plus
    fees, in basis points of notional) so backtest P&L is not flattered by
    free trading. 0 keeps the old frictionless behavior. Crypto symbols
    (containing "/") get crypto_cost_bps instead - Alpaca's crypto taker fee
    is ~25 bps, an order of magnitude above a liquid stock's half-spread.
    """

    def __init__(self, cash=100_000, cost_bps=0.0, crypto_cost_bps=None):
        self.cash = float(cash)
        self.cost_bps = float(cost_bps or 0.0)
        self.crypto_cost_bps = self.cost_bps if crypto_cost_bps is None \
            else float(crypto_cost_bps)
        self.costs_paid = 0.0  # cumulative dollars lost to the cost model
        self.positions = {}   # symbol -> signed qty
        self.entries = {}     # symbol -> entry price
        self.trades = []      # completed round trips, for hit rate
        self._n = 0

    def equity(self, prices):
        held = sum(q * prices.get(s, self.entries.get(s, 0.0))
                   for s, q in self.positions.items())
        return self.cash + held

    def submit(self, symbol, side, qty, price, ts=None, reason=""):
        signed = qty if side == "buy" else -qty
        old = self.positions.get(symbol, 0.0)
        new = old + signed
        self.cash -= signed * price
        rate = self.crypto_cost_bps if "/" in symbol else self.cost_bps
        if rate:
            cost = abs(signed) * price * rate / 1e4
            self.cash -= cost
            self.costs_paid += cost

        if old == 0 and new != 0:
            self.entries[symbol] = price
        elif old != 0 and new == 0:   # round trip closed - record it for hit rate
            entry = self.entries.pop(symbol, price)
            self.trades.append({"ts": str(ts), "symbol": symbol,
                                "side": "long" if old > 0 else "short",
                                "entry": entry, "exit": price,
                                "ret": (price / entry - 1) * (1 if old > 0 else -1),
                                "pnl": (price - entry) * old, "reason": reason})
        if new == 0:
            self.positions.pop(symbol, None)
        else:
            self.positions[symbol] = new

        self._n += 1
        return {"order_id": f"sim-{self._n}", "ts": ts, "symbol": symbol, "side": side,
                "qty": qty, "notional": qty * price, "status": "filled",
                "filled_qty": qty, "fill_price": price, "note": reason}


class PaperBroker:
    """Market orders against the Alpaca paper account (paper=True, always).

    After submitting, it polls the order until it reaches a terminal state
    (or ~10s pass) and reports the last status seen - so partial fills and
    rejections show up in the logs and the UI instead of disappearing.
    """

    def __init__(self):
        self.client = alpaca_client.trading_client()

    @staticmethod
    def _slash(position):
        """Alpaca reports crypto positions without the slash ("BTCUSD") but the
        rest of the system keys everything by the order form ("BTC/USD").
        Inferred from the position's asset class, not from any config snapshot,
        so tickers edited live in the UI can never desync the mapping."""
        if position.asset_class == AssetClass.CRYPTO and "/" not in position.symbol:
            return position.symbol[:-3] + "/" + position.symbol[-3:]
        return position.symbol

    def account(self):
        return alpaca_client.retry(self.client.get_account, what="get account")

    def clock(self):
        return alpaca_client.retry(self.client.get_clock, what="get clock")

    def positions(self):
        """(signed qty per symbol, entry price per symbol)."""
        raw = alpaca_client.retry(self.client.get_all_positions, what="get positions")
        qtys, entries = {}, {}
        for p in raw:
            symbol = self._slash(p)
            qtys[symbol] = float(p.qty)
            entries[symbol] = float(p.avg_entry_price)
        return qtys, entries

    def position_details(self):
        """Per-position view for the P&L snapshot, priced by Alpaca itself."""
        raw = alpaca_client.retry(self.client.get_all_positions, what="get positions")
        out = {}
        for p in raw:
            symbol = self._slash(p)
            out[symbol] = {"qty": float(p.qty), "entry": float(p.avg_entry_price),
                           "price": float(p.current_price or 0),
                           "market_value": float(p.market_value or 0),
                           "unrealized_pl": float(p.unrealized_pl or 0)}
        return out

    def submit(self, symbol, side, qty, price=None, ts=None, reason=""):
        ts = ts or datetime.now(timezone.utc)
        tif = TimeInForce.GTC if "/" in symbol else TimeInForce.DAY
        # deterministic id: if a network retry resubmits the same intent,
        # alpaca rejects the duplicate instead of placing the order twice
        dedup = f"{reason or 'order'}-{symbol.replace('/', '')}-{ts.strftime('%Y%m%d%H%M%S')}"
        req = MarketOrderRequest(symbol=symbol, qty=qty,
                                 side=OrderSide.BUY if side == "buy" else OrderSide.SELL,
                                 time_in_force=tif, client_order_id=dedup)
        try:
            order = alpaca_client.retry(lambda: self.client.submit_order(req),
                                        what=f"submit {symbol}")
        except APIError as e:
            log.error(f"order rejected on submit: {side} {qty} {symbol} - {e}")
            return {"order_id": f"rej-{ts.strftime('%H%M%S')}-{symbol}", "ts": ts,
                    "symbol": symbol, "side": side, "qty": qty, "notional": 0.0,
                    "status": "rejected", "filled_qty": 0.0, "fill_price": 0.0,
                    "note": f"{reason}: {str(e)[:160]}"}

        log.info(f"order submitted: {side} {qty} {symbol} (id {order.id})")
        status = order.status.value
        try:
            for _ in range(10):   # market orders settle fast; 10s is plenty for a poll
                if status in TERMINAL:
                    break
                time.sleep(1)
                order = alpaca_client.retry(lambda: self.client.get_order_by_id(order.id),
                                            what=f"poll order {symbol}")
                status = order.status.value
        except Exception as e:
            # losing the poll must not lose the order record or abort the
            # cycle's remaining orders - report the last status actually seen
            log.warning(f"lost track of order {order.id} while polling ({e}) - "
                        f"recording last known status '{status}'")

        filled_qty = float(order.filled_qty or 0)
        fill_price = float(order.filled_avg_price or 0)
        log.info(f"order {status}: {side} {symbol} filled {filled_qty} @ {fill_price}")
        return {"order_id": str(order.id), "ts": ts, "symbol": symbol, "side": side,
                "qty": qty, "notional": filled_qty * fill_price, "status": status,
                "filled_qty": filled_qty, "fill_price": fill_price, "note": reason}
