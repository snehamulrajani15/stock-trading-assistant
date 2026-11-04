"""Deterministic answers for fixed intents. Every number comes from the store or the price provider."""
import tools
from market import Quote, UnknownSymbolError

FALLBACK_NOTE = "Note: live prices unavailable, some values use sample prices."


def _quotes(symbols) -> dict[str, Quote]:
    return {s: tools.provider.get_quote(s) for s in symbols}


def _note(quotes: dict[str, Quote]) -> str:
    return f"\n{FALLBACK_NOTE}" if any(q.source != "live" for q in quotes.values()) else ""


def quote(symbol: str | None) -> str:
    if not symbol:
        return "Which stock? Please give a ticker symbol, e.g. AAPL."
    try:
        q = tools.provider.get_quote(symbol)
    except UnknownSymbolError as e:
        return str(e)
    return f"{q.symbol}: {q.price:.2f}" + _note({q.symbol: q})


def holdings() -> str:
    held = tools.store.get_holdings()
    if not held:
        return "You don't own any shares."
    quotes = _quotes(held)
    lines = [
        f"{h.symbol}: {h.quantity} shares, avg cost {h.avg_cost:.2f}, price {quotes[s].price:.2f}"
        for s, h in held.items()
    ]
    return "\n".join(lines) + _note(quotes)


def portfolio_value() -> str:
    held = tools.store.get_holdings()
    quotes = _quotes(held)
    cash = tools.store.get_cash()
    market_value = sum(h.quantity * quotes[s].price for s, h in held.items())
    return (
        f"Cash: {cash:.2f}\n"
        f"Holdings: {market_value:.2f}\n"
        f"Total portfolio value: {cash + market_value:.2f}" + _note(quotes)
    )


def trade_history(symbol: str | None = None, limit: int = 10) -> str:
    trades = tools.store.get_trades()
    if symbol:
        trades = [t for t in trades if t.symbol == symbol.upper()]
    if not trades:
        return "No trades found."
    lines = [
        f"{t.timestamp}  {t.side} {t.quantity} {t.symbol} @ {t.price_per_share:.2f} = {t.total:.2f}"
        for t in trades[-limit:][::-1]  # newest first
    ]
    return f"Last {len(lines)} trades:\n" + "\n".join(lines)


def pnl(symbol: str | None = None) -> str:
    """Unrealized P&L: current price versus average cost of shares still held."""
    held = tools.store.get_holdings()
    if symbol:
        symbol = symbol.upper()
        if symbol not in held:
            return f"You don't hold any {symbol}."
        held = {symbol: held[symbol]}
    if not held:
        return "You don't own any shares."

    quotes = _quotes(held)
    lines, total = [], 0.0
    for s, h in held.items():
        gain = (quotes[s].price - h.avg_cost) * h.quantity
        pct = (quotes[s].price / h.avg_cost - 1) * 100
        total += gain
        lines.append(f"{s}: {gain:+.2f} ({pct:+.1f}%)")
    if len(lines) > 1:
        lines.append(f"Total unrealized P&L: {total:+.2f}")
    return "\n".join(lines) + _note(quotes)
