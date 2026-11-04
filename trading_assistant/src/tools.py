"""LLM tools: price lookup and a single-approval order tool. Prices and totals come from code only."""
from typing import Literal, TypedDict

from langchain_core.tools import tool
from langgraph.types import interrupt

from market import UnknownSymbolError, YFinanceProvider
from store import Store, TradeRejectedError

MAX_ORDER_SHARES = 1000

provider = YFinanceProvider()
store = Store()


class Order(TypedDict):
    symbol: str
    side: Literal["buy", "sell"]
    quantity: int


@tool
def get_stock_price(symbol: str) -> str:
    """Get the current price of one stock by ticker symbol."""
    try:
        quote = provider.get_quote(symbol)
    except UnknownSymbolError as e:
        return str(e)
    note = "" if quote.source == "live" else " (live price unavailable, using sample price)"
    return f"{quote.symbol}: {quote.price:.2f}{note}"


@tool
def place_orders(orders: list[Order]) -> str:
    """Place ALL buy/sell orders in ONE call. Asks the user for approval before anything is traded.

    Each order has a symbol, a side ("buy" or "sell") and a quantity. Do not pass prices.
    """
    priced = []
    lines = []
    try:
        for o in orders:
            if o["quantity"] > MAX_ORDER_SHARES:
                raise TradeRejectedError(f"Max {MAX_ORDER_SHARES} shares per order: {o['symbol']}")
            quote = provider.get_quote(o["symbol"])
            priced.append((quote.symbol, o["side"], o["quantity"], quote.price))
            note = "" if quote.source == "live" else " [sample price]"
            lines.append(f"{o['side']} {o['quantity']} {quote.symbol} @ {quote.price:.2f}{note}")
        trades, _ = store.check_orders(priced)  # reject impossible orders before asking
    except (UnknownSymbolError, TradeRejectedError) as e:
        return f"Order rejected: {e}"

    total = sum(t.total if t.side == "buy" else -t.total for t in trades)
    summary = "\n".join(lines) + f"\nNet {'cost' if total >= 0 else 'proceeds'}: {abs(total):.2f}"

    decision = interrupt(summary)
    if str(decision).strip().lower() != "yes":
        return "Order cancelled by the user. Nothing was traded."

    try:
        done = store.record_trades(priced)  # validates again before writing
    except TradeRejectedError as e:
        return f"Order rejected: {e}"
    return "Order executed:\n" + "\n".join(
        f"{t.side} {t.quantity} {t.symbol} @ {t.price_per_share:.2f} = {t.total:.2f}" for t in done)


tools = [get_stock_price, place_orders]
