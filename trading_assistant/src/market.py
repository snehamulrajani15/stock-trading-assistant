"""Market data: live prices via yfinance, with a CSV fallback."""
import csv
import time
from dataclasses import dataclass
from pathlib import Path

PRICES_CSV = Path("data/prices.csv")
CACHE_TTL_SECONDS = 60


class UnknownSymbolError(ValueError):
    pass


@dataclass(frozen=True)
class Quote:
    symbol: str
    price: float
    source: str  # "live" or "fallback"


class MockProvider:
    """Prices from the sample CSV. Also the supported-symbol list and the live fallback."""

    def __init__(self, path: Path = PRICES_CSV):
        with path.open(newline="") as f:
            self.prices = {r["symbol"]: float(r["price"]) for r in csv.DictReader(f)}

    def get_quote(self, symbol: str) -> Quote:
        symbol = symbol.upper()
        if symbol not in self.prices:
            raise UnknownSymbolError(f"Unknown symbol: {symbol}")
        return Quote(symbol, self.prices[symbol], "fallback")


class YFinanceProvider:
    """Live prices with a short cache; falls back to the CSV if the API fails."""

    def __init__(self, fallback: MockProvider | None = None):
        self.fallback = fallback or MockProvider()
        self._cache: dict[str, tuple[float, float]] = {}  # symbol -> (price, fetched_at)

    def get_quote(self, symbol: str) -> Quote:
        symbol = symbol.upper()
        if symbol not in self.fallback.prices:
            raise UnknownSymbolError(f"Unknown symbol: {symbol}")

        cached = self._cache.get(symbol)
        if cached and time.time() - cached[1] < CACHE_TTL_SECONDS:
            return Quote(symbol, cached[0], "live")

        try:
            import yfinance as yf

            price = round(float(yf.Ticker(symbol).fast_info["last_price"]), 2)
            if price <= 0:
                raise ValueError("non-positive price")
        except Exception:
            return self.fallback.get_quote(symbol)

        self._cache[symbol] = (price, time.time())
        return Quote(symbol, price, "live")

