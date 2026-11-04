"""Generate synthetic sample data for the paper-trading assistant.

Writes three CSVs to data/ (all values are fictional):
  prices.csv   symbol, name, price      -> mock market provider
  trades.csv   timestamp, symbol, side, quantity, price_per_share, total
  account.csv  cash                     -> consistent with the trades

The trade history respects the same guardrails the app enforces: cash never
goes negative, shares never go negative and orders stay under the per-order cap.

Usage: python scripts/generate_sample_data.py [--seed 42]
"""
import argparse
import csv
import random
from datetime import datetime, timedelta
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent / "data"

STARTING_CASH = 100_000.00
MAX_ORDER_SHARES = 1_000
N_SESSIONS = 9  # trading sessions with at least one approved order

# symbol -> (company name, current mock price). Fictional prices.
UNIVERSE = {
    "AAPL": ("Apple Inc.", 187.42),
    "MSFT": ("Microsoft Corporation", 412.18),
    "GOOG": ("Alphabet Inc.", 168.35),
    "AMZN": ("Amazon.com, Inc.", 183.77),
    "NVDA": ("NVIDIA Corporation", 126.54),
    "TSLA": ("Tesla, Inc.", 242.91),
    "META": ("Meta Platforms, Inc.", 497.26),
    "NFLX": ("Netflix, Inc.", 641.08),
    "AMD": ("Advanced Micro Devices, Inc.", 158.63),
    "JPM": ("JPMorgan Chase & Co.", 203.49),
}

TRADE_COLUMNS = ["timestamp", "symbol", "side", "quantity", "price_per_share", "total"]


def trading_days(end: datetime, n: int) -> list[datetime]:
    """The n most recent weekdays up to and including `end`, oldest first."""
    days, day = [], end
    while len(days) < n:
        if day.weekday() < 5:
            days.append(day)
        day -= timedelta(days=1)
    return days[::-1]


def historical_price(rng: random.Random, current: float, days_ago: int) -> float:
    """A past price: current price with a random walk and small drift back in time."""
    drift = rng.uniform(-0.002, 0.002) * days_ago
    noise = rng.gauss(0, 0.012)
    return round(current * (1 + drift + noise), 2)


def generate_trades(rng: random.Random) -> tuple[list[dict], float]:
    cash = STARTING_CASH
    holdings: dict[str, int] = {}
    trades: list[dict] = []
    days = trading_days(datetime(2026, 10, 30), N_SESSIONS * 2)
    session_days = sorted(rng.sample(days, N_SESSIONS))

    for i, day in enumerate(session_days):
        stamp = day.replace(hour=rng.randint(9, 15), minute=rng.randint(0, 59), second=0)
        days_ago = (days[-1] - day).days
        # The first sessions are buys only so there is something to sell later.
        n_orders = rng.choice([1, 2, 2, 3])
        symbols = rng.sample(list(UNIVERSE), n_orders)

        for symbol in symbols:
            owned = holdings.get(symbol, 0)
            can_sell = owned > 0 and i >= 3
            side = "sell" if can_sell and rng.random() < 0.3 else "buy"
            price = historical_price(rng, UNIVERSE[symbol][1], days_ago)

            if side == "sell":
                qty = max(1, int(owned * rng.uniform(0.25, 1.0)))
            else:
                budget = min(cash, rng.uniform(0.02, 0.06) * STARTING_CASH)
                qty = min(int(budget // price), MAX_ORDER_SHARES)
            if qty < 1:
                continue

            total = round(qty * price, 2)
            if side == "buy":
                if total > cash:
                    continue
                cash -= total
                holdings[symbol] = owned + qty
            else:
                cash += total
                holdings[symbol] = owned - qty

            trades.append({
                "timestamp": stamp.isoformat(timespec="seconds"),
                "symbol": symbol,
                "side": side,
                "quantity": qty,
                "price_per_share": f"{price:.2f}",
                "total": f"{total:.2f}",
            })

    return trades, round(cash, 2)


def write_csv(path: Path, columns: list[str], rows: list[dict]) -> None:
    with path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    rng = random.Random(args.seed)
    DATA_DIR.mkdir(exist_ok=True)

    prices = [{"symbol": s, "name": n, "price": f"{p:.2f}"} for s, (n, p) in UNIVERSE.items()]
    trades, cash = generate_trades(rng)

    write_csv(DATA_DIR / "prices.csv", ["symbol", "name", "price"], prices)
    write_csv(DATA_DIR / "trades.csv", TRADE_COLUMNS, trades)
    write_csv(DATA_DIR / "account.csv", ["cash"], [{"cash": f"{cash:.2f}"}])

    print(f"Wrote {len(prices)} prices, {len(trades)} trades, cash={cash:.2f} to {DATA_DIR}")


if __name__ == "__main__":
    main()
