# SimBroker transaction cost model
from execution.orders import SimBroker


def test_zero_cost_bps_preserves_frictionless_behavior():
    b = SimBroker(100_000, cost_bps=0)
    b.submit("A", "buy", 10, 100.0)
    assert b.cash == 100_000 - 1_000
    assert b.costs_paid == 0.0


def test_cost_bps_charged_on_every_fill_both_sides():
    # 5 bps on a $1,000 fill = $0.50 per side, $1.00 round trip
    b = SimBroker(100_000, cost_bps=5)
    b.submit("A", "buy", 10, 100.0)
    assert b.costs_paid == 0.50
    b.submit("A", "sell", 10, 100.0)   # flat exit at the same price
    assert b.costs_paid == 1.00
    # cash ends exactly one round trip of costs below start
    assert abs(b.cash - (100_000 - 1.00)) < 1e-9
    # trade record stays gross - the cost lives in cash, not in ret/pnl
    assert b.trades[0]["pnl"] == 0.0


def test_costs_hit_equity():
    b = SimBroker(100_000, cost_bps=10)
    b.submit("A", "buy", 10, 100.0)
    assert b.equity({"A": 100.0}) == 100_000 - 1.0   # 10bps of $1,000


def test_crypto_symbols_get_their_own_cost_rate():
    b = SimBroker(100_000, cost_bps=5, crypto_cost_bps=25)
    b.submit("AAPL", "buy", 10, 100.0)      # $1,000 at 5bps = $0.50
    b.submit("BTC/USD", "buy", 0.01, 100_000.0)   # $1,000 at 25bps = $2.50
    assert abs(b.costs_paid - 3.00) < 1e-9
