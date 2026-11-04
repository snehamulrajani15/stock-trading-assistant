"""CSV persistence: trades are the source of truth for holdings; cash lives in account.csv."""
import csv
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from filelock import FileLock

TRADE_COLUMNS = ["timestamp", "symbol", "side", "quantity", "price_per_share", "total"]


class TradeRejectedError(ValueError):
    pass


@dataclass(frozen=True)
class Trade:
    timestamp: str
    symbol: str
    side: str  # "buy" or "sell"
    quantity: int
    price_per_share: float
    total: float


@dataclass(frozen=True)
class Holding:
    symbol: str
    quantity: int
    avg_cost: float


class Store:
    def __init__(self, data_dir: Path = Path("data")):
        self.trades_path = data_dir / "trades.csv"
        self.account_path = data_dir / "account.csv"
        self.lock = FileLock(data_dir / ".store.lock")

    def get_cash(self) -> float:
        with self.account_path.open(newline="") as f:
            return float(next(csv.DictReader(f))["cash"])

    def get_trades(self) -> list[Trade]:
        with self.trades_path.open(newline="") as f:
            return [
                Trade(r["timestamp"], r["symbol"], r["side"], int(r["quantity"]),
                      float(r["price_per_share"]), float(r["total"]))
                for r in csv.DictReader(f)
            ]

    def get_holdings(self) -> dict[str, Holding]:
        """Net shares per symbol with average cost of what is still held."""
        qty: dict[str, int] = {}
        cost: dict[str, float] = {}  # total cost of shares currently held
        for t in self.get_trades():
            held = qty.get(t.symbol, 0)
            if t.side == "buy":
                qty[t.symbol] = held + t.quantity
                cost[t.symbol] = cost.get(t.symbol, 0.0) + t.total
            else:
                # A sell removes shares at the current average cost.
                avg = cost[t.symbol] / held
                qty[t.symbol] = held - t.quantity
                cost[t.symbol] -= avg * t.quantity
        return {
            s: Holding(s, q, round(cost[s] / q, 2)) for s, q in qty.items() if q > 0
        }

    def check_orders(self, orders: list[tuple[str, str, int, float]]) -> tuple[list[Trade], float]:
        """Validate orders (symbol, side, quantity, price_per_share) without writing.

        Returns the trades that would be written and the resulting cash.
        Raises TradeRejectedError if any order fails.
        """
        cash = self.get_cash()
        shares = {s: h.quantity for s, h in self.get_holdings().items()}
        stamp = datetime.now().isoformat(timespec="seconds")
        trades = []

        for symbol, side, quantity, price in orders:
            if side not in ("buy", "sell"):
                raise TradeRejectedError(f"Invalid side: {side}")
            if quantity <= 0:
                raise TradeRejectedError(f"Quantity must be positive: {symbol}")
            total = round(quantity * price, 2)
            if side == "buy":
                if total > cash:
                    raise TradeRejectedError(
                        f"Not enough cash for {quantity} {symbol}: need {total:.2f}, have {cash:.2f}")
                cash -= total
                shares[symbol] = shares.get(symbol, 0) + quantity
            else:
                if quantity > shares.get(symbol, 0):
                    raise TradeRejectedError(
                        f"Not enough shares of {symbol}: want to sell {quantity}, hold {shares.get(symbol, 0)}")
                cash += total
                shares[symbol] -= quantity
            trades.append(Trade(stamp, symbol, side, quantity, price, total))
        return trades, cash

    def record_trades(self, orders: list[tuple[str, str, int, float]]) -> list[Trade]:
        """Re-validate and append approved orders. All-or-nothing."""
        with self.lock:
            trades, cash = self.check_orders(orders)
            with self.trades_path.open("a", newline="") as f:
                writer = csv.writer(f)
                for t in trades:
                    writer.writerow([t.timestamp, t.symbol, t.side, t.quantity,
                                     f"{t.price_per_share:.2f}", f"{t.total:.2f}"])
            with self.account_path.open("w", newline="") as f:
                f.write(f"cash\n{cash:.2f}\n")
            return trades
