# pre-trade risk checks - every opening order passes through here first
# closing orders skip the caps on purpose: they reduce risk, never add it


def gross_exposure(positions, prices):
    """Sum of |qty * price| across the book, in dollars."""
    return sum(abs(q) * prices[s] for s, q in positions.items()
               if q != 0 and s in prices and prices[s] == prices[s])


def check_order(symbol, notional, positions, prices, equity, limits):
    """(ok, reason) for one opening order of the given dollar size.

    Three checks, in order:
    1. min notional  - skip dust orders not worth the commission-free fill
    2. per-asset cap - existing + new notional in this symbol <= 15% of equity
    3. gross cap     - total book notional + new <= 100% of equity (no leverage)
    """
    if notional < limits["min_order_notional"]:
        return False, f"below min notional (${notional:,.0f} < ${limits['min_order_notional']})"

    held = abs(positions.get(symbol, 0.0)) * prices.get(symbol, 0.0)
    cap = limits["max_position_pct"] * equity
    if held + notional > cap * 1.0001:   # tiny tolerance for float noise
        return False, f"per-asset cap (${held + notional:,.0f} > ${cap:,.0f})"

    gross = gross_exposure(positions, prices)
    gross_cap = limits["max_gross_pct"] * equity
    if gross + notional > gross_cap * 1.0001:
        return False, f"gross cap (${gross + notional:,.0f} > ${gross_cap:,.0f})"

    return True, "ok"


def stop_hits(positions, entries, prices, stop_loss_pct):
    """Symbols whose price has moved stop_loss_pct against the entry.

    Longs stop out when price falls 5% below entry, shorts when it rises 5%
    above. This is the hard backstop for the strategy's worst case: a price
    that keeps trending away from its mean instead of reverting.
    """
    hits = []
    for symbol, qty in positions.items():
        if qty == 0 or symbol not in prices or symbol not in entries:
            continue
        entry = entries[symbol]
        px = prices[symbol]
        if not entry or px != px:   # missing entry or NaN price
            continue
        move = px / entry - 1
        if (qty > 0 and move <= -stop_loss_pct) or (qty < 0 and move >= stop_loss_pct):
            hits.append(symbol)
    return hits
