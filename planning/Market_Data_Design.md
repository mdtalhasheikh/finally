# Market Data Backend — Implementation Design

Complete implementation guide for `backend/app/market/`. The subsystem is **already built and tested** (73 tests, 84% coverage). This document explains every design decision, shows the actual code, and gives copy-paste examples for every integration point.

---

## Table of Contents

1. [Architecture Overview](#1-architecture-overview)
2. [Data Model — `PriceUpdate`](#2-data-model--priceupdate)
3. [Price Cache](#3-price-cache)
4. [Unified Interface — `MarketDataSource`](#4-unified-interface--marketdatasource)
5. [Simulator — GBM Engine](#5-simulator--gbm-engine)
6. [Simulator — `SimulatorDataSource`](#6-simulator--simulatordatasource)
7. [Seed Prices and Correlation Data](#7-seed-prices-and-correlation-data)
8. [Massive API — `MassiveDataSource`](#8-massive-api--massivedatasource)
9. [Factory — Source Selection](#9-factory--source-selection)
10. [SSE Streaming Endpoint](#10-sse-streaming-endpoint)
11. [FastAPI Lifecycle Integration](#11-fastapi-lifecycle-integration)
12. [Downstream Usage Patterns](#12-downstream-usage-patterns)
13. [Testing Strategy](#13-testing-strategy)
14. [Module Map and File Reference](#14-module-map-and-file-reference)

---

## 1. Architecture Overview

```
Environment variable MASSIVE_API_KEY
         │
         ▼
  create_market_data_source(cache)          ← factory.py
         │
         ├── (key absent) SimulatorDataSource  ← simulator.py
         │                    │
         │                    │ GBMSimulator.step() every 500ms
         │                    │
         └── (key present) MassiveDataSource   ← massive_client.py
                              │
                              │ Polygon.io REST poll every 15s
                              │
                              ▼
                        PriceCache                    ← cache.py
                        (thread-safe, in-process)
                              │
              ┌───────────────┼───────────────┐
              ▼               ▼               ▼
  GET /api/stream/prices  portfolio       trade execution
  (SSE, stream.py)        valuation       order fill price
```

**One invariant drives everything**: only the active data source writes to `PriceCache`. All other code — SSE, portfolio, trade execution — only reads. No component talks to the data source directly for prices.

---

## 2. Data Model — `PriceUpdate`

**File**: `backend/app/market/models.py`

The only price representation that leaves the market data layer. Immutable frozen dataclass — safe to share across threads without copying.

```python
# backend/app/market/models.py
from __future__ import annotations

import time
from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class PriceUpdate:
    """Immutable snapshot of a single ticker's price at a point in time."""

    ticker: str
    price: float           # Current price, rounded to 2 decimal places
    previous_price: float  # Price from the immediately preceding cache.update() call
    timestamp: float = field(default_factory=time.time)  # Unix seconds

    @property
    def change(self) -> float:
        """Absolute price change from previous update, rounded to 4dp."""
        return round(self.price - self.previous_price, 4)

    @property
    def change_percent(self) -> float:
        """Percentage change from previous update, rounded to 4dp."""
        if self.previous_price == 0:
            return 0.0
        return round((self.price - self.previous_price) / self.previous_price * 100, 4)

    @property
    def direction(self) -> str:
        """'up', 'down', or 'flat'."""
        if self.price > self.previous_price:
            return "up"
        elif self.price < self.previous_price:
            return "down"
        return "flat"

    def to_dict(self) -> dict:
        """Serialize for JSON / SSE. All fields are JSON-safe primitives."""
        return {
            "ticker": self.ticker,
            "price": self.price,
            "previous_price": self.previous_price,
            "timestamp": self.timestamp,
            "change": self.change,
            "change_percent": self.change_percent,
            "direction": self.direction,
        }
```

**SSE wire format** — what `to_dict()` produces for a single ticker:

```json
{
  "ticker": "AAPL",
  "price": 190.50,
  "previous_price": 190.20,
  "timestamp": 1716998400.123,
  "change": 0.3,
  "change_percent": 0.1577,
  "direction": "up"
}
```

**Design notes**:
- `previous_price` is the previous *tick's* price, not the previous day's close. Use `session_open` from the watchlist/portfolio endpoints for daily change %.
- `slots=True` reduces per-instance memory. Each tick creates one new `PriceUpdate`; the old one is immediately eligible for GC.
- `frozen=True` makes the object hashable and safe to read from multiple threads without locking.

---

## 3. Price Cache

**File**: `backend/app/market/cache.py`

Thread-safe in-memory store. One instance per process, injected into both the data source (writer) and all consumers (readers).

```python
# backend/app/market/cache.py
from __future__ import annotations

import time
from threading import Lock

from .models import PriceUpdate


class PriceCache:
    def __init__(self) -> None:
        self._prices: dict[str, PriceUpdate] = {}
        self._lock = Lock()
        self._version: int = 0

    # ── Writer API ────────────────────────────────────────────────────────────

    def update(self, ticker: str, price: float, timestamp: float | None = None) -> PriceUpdate:
        """Record a new price. First update for a ticker sets previous_price == price
        (direction = 'flat'). Increments the version counter every call."""
        with self._lock:
            ts = timestamp or time.time()
            prev = self._prices.get(ticker)
            previous_price = prev.price if prev else price

            update = PriceUpdate(
                ticker=ticker,
                price=round(price, 2),
                previous_price=round(previous_price, 2),
                timestamp=ts,
            )
            self._prices[ticker] = update
            self._version += 1
            return update

    def remove(self, ticker: str) -> None:
        """Remove a ticker. Called when ticker leaves both watchlist and open positions."""
        with self._lock:
            self._prices.pop(ticker, None)

    # ── Reader API ────────────────────────────────────────────────────────────

    def get(self, ticker: str) -> PriceUpdate | None:
        """Latest PriceUpdate, or None if the ticker is not tracked."""
        with self._lock:
            return self._prices.get(ticker)

    def get_price(self, ticker: str) -> float | None:
        """Convenience: current price float, or None."""
        update = self.get(ticker)
        return update.price if update else None

    def get_all(self) -> dict[str, PriceUpdate]:
        """Shallow copy of all tracked tickers. Safe to iterate after the lock releases."""
        with self._lock:
            return dict(self._prices)

    # ── SSE change detection ──────────────────────────────────────────────────

    @property
    def version(self) -> int:
        """Monotonically increasing counter. Bumped on every update() call.
        SSE generator compares versions to avoid sending duplicate events."""
        return self._version

    # ── Introspection ─────────────────────────────────────────────────────────

    def __len__(self) -> int:
        with self._lock:
            return len(self._prices)

    def __contains__(self, ticker: str) -> bool:
        with self._lock:
            return ticker in self._prices
```

**Concurrency model**: The data source writes from an asyncio Task (event loop thread or thread pool worker). The SSE generator and HTTP handlers read from the event loop thread. `threading.Lock` protects every read and write — no torn reads possible.

**Version counter pattern**: instead of sending every 500 ms regardless, the SSE generator checks `version` before yielding:

```python
# Only emit an event if prices have actually changed since last send
if current_version != last_version:
    last_version = current_version
    yield f"data: {json.dumps(price_cache.get_all())}\n\n"
```

This prevents duplicate events during quiet periods and reduces unnecessary client-side re-renders.

---

## 4. Unified Interface — `MarketDataSource`

**File**: `backend/app/market/interface.py`

Abstract base class. All downstream code is typed against this interface — swapping simulator for real data requires zero changes to consumers.

```python
# backend/app/market/interface.py
from __future__ import annotations

from abc import ABC, abstractmethod


class MarketDataSource(ABC):
    """Contract for market data providers.

    Implementations push price updates into a shared PriceCache on their own
    schedule. Downstream code never calls the data source for prices; it reads
    from the cache.

    Lifecycle (must be followed in order):
        source = create_market_data_source(cache)   # unstarted
        await source.start(["AAPL", "GOOGL", ...])  # starts background task
        await source.add_ticker("TSLA")              # dynamic add
        await source.remove_ticker("GOOGL")          # dynamic remove
        await source.stop()                          # cleanup on shutdown
    """

    @abstractmethod
    async def start(self, tickers: list[str]) -> None:
        """Initialize with the given tickers and start the background update task.
        Must be called exactly once. Seeds PriceCache before returning so the
        first HTTP request already has prices."""

    @abstractmethod
    async def stop(self) -> None:
        """Cancel the background task and release resources.
        Safe to call multiple times."""

    @abstractmethod
    async def add_ticker(self, ticker: str) -> None:
        """Add a ticker to the active set. No-op if already present.
        In simulator mode, seeds the cache immediately.
        In Massive mode, ticker appears on the next poll cycle."""

    @abstractmethod
    async def remove_ticker(self, ticker: str) -> None:
        """Remove a ticker from the active set and from the PriceCache.
        No-op if not present."""

    @abstractmethod
    def get_tickers(self) -> list[str]:
        """Return the current list of actively tracked tickers."""
```

**Why an ABC over a protocol**: `ABC` gives `@abstractmethod` enforcement at class definition time (missing method raises `TypeError` at import, not at runtime). A `Protocol` would be fine too, but the ABC makes the contract explicit for agents reading the code.

---

## 5. Simulator — GBM Engine

**File**: `backend/app/market/simulator.py` (`GBMSimulator` class)

The pure mathematical engine. No asyncio, no FastAPI, no cache — just math. This makes it independently testable.

### GBM Formula

At each time step, a price evolves as:

```
S(t+dt) = S(t) × exp( (μ - σ²/2) × dt  +  σ × √dt × Z )
```

| Symbol | Meaning | Typical value |
|--------|---------|---------------|
| `μ` (mu) | Annualized drift (expected return) | 0.05 (5%) |
| `σ` (sigma) | Annualized volatility | 0.20–0.50 |
| `dt` | Time step as fraction of a trading year | ~8.48 × 10⁻⁸ |
| `Z` | Correlated standard normal random variable | from Cholesky decomposition |

**Choosing dt for 500 ms ticks**:
```
252 trading days × 6.5 hours/day × 3600 s/hour = 5,896,800 s/year
dt = 0.5 / 5,896,800 ≈ 8.48e-8
```

**Per-tick move magnitude** for a $190 AAPL with σ=0.22:
```
σ × √dt × price ≈ 0.22 × 0.000291 × 190 ≈ $0.012 per tick
```
Imperceptible individually, but produces realistic-looking trends over minutes.

### Correlated Moves via Cholesky Decomposition

Real stocks move together within sectors. The simulator replicates this:

```python
# 1. Build the n×n correlation matrix from pairwise sector rules
corr = np.eye(n)
for i in range(n):
    for j in range(i + 1, n):
        rho = _pairwise_correlation(tickers[i], tickers[j])
        corr[i, j] = corr[j, i] = rho

# 2. Compute lower triangular Cholesky factor L such that L @ L.T == corr
cholesky = np.linalg.cholesky(corr)

# 3. Each tick: generate independent normals, multiply by L to correlate them
z_independent = np.random.standard_normal(n)
z_correlated = cholesky @ z_independent

# 4. Use z_correlated[i] for ticker i in the GBM formula
```

**Sector groupings** (defined in `seed_prices.py`):

| Group | Tickers | Intra-group ρ |
|-------|---------|---------------|
| Tech | AAPL, GOOGL, MSFT, AMZN, META, NVDA, NFLX | 0.6 |
| Finance | JPM, V | 0.5 |
| TSLA | standalone | 0.3 with everything |
| Cross-sector / unknown | any other pair | 0.3 |

### Complete `GBMSimulator` Implementation

```python
class GBMSimulator:
    TRADING_SECONDS_PER_YEAR = 252 * 6.5 * 3600  # 5,896,800
    DEFAULT_DT = 0.5 / TRADING_SECONDS_PER_YEAR  # ~8.48e-8

    def __init__(
        self,
        tickers: list[str],
        dt: float = DEFAULT_DT,
        event_probability: float = 0.001,
    ) -> None:
        self._dt = dt
        self._event_prob = event_probability
        self._tickers: list[str] = []
        self._prices: dict[str, float] = {}
        self._params: dict[str, dict[str, float]] = {}
        self._cholesky: np.ndarray | None = None

        for ticker in tickers:
            self._add_ticker_internal(ticker)  # batch init without rebuilding
        self._rebuild_cholesky()               # single rebuild after all added

    def step(self) -> dict[str, float]:
        """Advance all tickers one dt. Hot path — called every 500ms."""
        n = len(self._tickers)
        if n == 0:
            return {}

        z_independent = np.random.standard_normal(n)
        z_correlated = self._cholesky @ z_independent if self._cholesky is not None else z_independent

        result: dict[str, float] = {}
        for i, ticker in enumerate(self._tickers):
            mu = self._params[ticker]["mu"]
            sigma = self._params[ticker]["sigma"]

            drift = (mu - 0.5 * sigma**2) * self._dt
            diffusion = sigma * math.sqrt(self._dt) * z_correlated[i]
            self._prices[ticker] *= math.exp(drift + diffusion)

            # Random shock: 0.1% per tick per ticker → ~1 event per 50s across 10 tickers
            if random.random() < self._event_prob:
                shock_magnitude = random.uniform(0.02, 0.05)
                shock_sign = random.choice([-1, 1])
                self._prices[ticker] *= (1 + shock_magnitude * shock_sign)
                logger.debug("Random event on %s: %.1f%% %s", ticker,
                             shock_magnitude * 100, "up" if shock_sign > 0 else "down")

            result[ticker] = round(self._prices[ticker], 2)

        return result

    def add_ticker(self, ticker: str) -> None:
        if ticker in self._prices:
            return
        self._add_ticker_internal(ticker)
        self._rebuild_cholesky()

    def remove_ticker(self, ticker: str) -> None:
        if ticker not in self._prices:
            return
        self._tickers.remove(ticker)
        del self._prices[ticker]
        del self._params[ticker]
        self._rebuild_cholesky()

    def get_price(self, ticker: str) -> float | None:
        return self._prices.get(ticker)

    def get_tickers(self) -> list[str]:
        return list(self._tickers)

    def _add_ticker_internal(self, ticker: str) -> None:
        """Add without rebuilding Cholesky — for batch init."""
        if ticker in self._prices:
            return
        self._tickers.append(ticker)
        self._prices[ticker] = SEED_PRICES.get(ticker, random.uniform(50.0, 300.0))
        self._params[ticker] = TICKER_PARAMS.get(ticker, dict(DEFAULT_PARAMS))

    def _rebuild_cholesky(self) -> None:
        """Recompute L = chol(C). O(n²), called only on watchlist changes."""
        n = len(self._tickers)
        if n <= 1:
            self._cholesky = None
            return
        corr = np.eye(n)
        for i in range(n):
            for j in range(i + 1, n):
                rho = self._pairwise_correlation(self._tickers[i], self._tickers[j])
                corr[i, j] = corr[j, i] = rho
        self._cholesky = np.linalg.cholesky(corr)

    @staticmethod
    def _pairwise_correlation(t1: str, t2: str) -> float:
        tech = CORRELATION_GROUPS["tech"]
        finance = CORRELATION_GROUPS["finance"]
        if t1 == "TSLA" or t2 == "TSLA":
            return TSLA_CORR
        if t1 in tech and t2 in tech:
            return INTRA_TECH_CORR
        if t1 in finance and t2 in finance:
            return INTRA_FINANCE_CORR
        return CROSS_GROUP_CORR
```

**Key properties**:
- Prices are always positive — `exp()` of any real number is > 0.
- Resets to seed prices on container restart (in-memory state).
- Unknown tickers (dynamically added, not in `SEED_PRICES`) get `random.uniform(50, 300)` and `DEFAULT_PARAMS`. No error is ever raised in simulator mode.
- `_rebuild_cholesky()` is O(n²) but n is always < 50; runs only on `add_ticker`/`remove_ticker`, never on the hot `step()` path.

---

## 6. Simulator — `SimulatorDataSource`

**File**: `backend/app/market/simulator.py` (`SimulatorDataSource` class)

The asyncio wrapper around `GBMSimulator`. Drives the math engine from a background task and writes results to `PriceCache`.

```python
class SimulatorDataSource(MarketDataSource):
    def __init__(
        self,
        price_cache: PriceCache,
        update_interval: float = 0.5,      # seconds between GBM steps
        event_probability: float = 0.001,  # per-tick shock probability
    ) -> None:
        self._cache = price_cache
        self._interval = update_interval
        self._event_prob = event_probability
        self._sim: GBMSimulator | None = None
        self._task: asyncio.Task | None = None

    async def start(self, tickers: list[str]) -> None:
        self._sim = GBMSimulator(tickers=tickers, event_probability=self._event_prob)

        # ── Critical: seed the cache before the loop starts ──────────────────
        # SSE clients connecting during startup get real prices immediately,
        # not None/blank. Without this, the first SSE event might be empty.
        for ticker in tickers:
            price = self._sim.get_price(ticker)
            if price is not None:
                self._cache.update(ticker=ticker, price=price)

        self._task = asyncio.create_task(self._run_loop(), name="simulator-loop")
        logger.info("Simulator started with %d tickers", len(tickers))

    async def stop(self) -> None:
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        self._task = None
        logger.info("Simulator stopped")

    async def add_ticker(self, ticker: str) -> None:
        if self._sim:
            self._sim.add_ticker(ticker)
            # Seed cache immediately — the UI gets a price before the next loop tick
            price = self._sim.get_price(ticker)
            if price is not None:
                self._cache.update(ticker=ticker, price=price)
            logger.info("Simulator: added ticker %s", ticker)

    async def remove_ticker(self, ticker: str) -> None:
        if self._sim:
            self._sim.remove_ticker(ticker)
        self._cache.remove(ticker)
        logger.info("Simulator: removed ticker %s", ticker)

    def get_tickers(self) -> list[str]:
        return self._sim.get_tickers() if self._sim else []

    async def _run_loop(self) -> None:
        while True:
            try:
                if self._sim:
                    prices = self._sim.step()
                    for ticker, price in prices.items():
                        self._cache.update(ticker=ticker, price=price)
            except Exception:
                logger.exception("Simulator step failed")
            await asyncio.sleep(self._interval)
```

**Immediate seeding on `add_ticker`**: When a user adds a new ticker to the watchlist, `add_ticker()` calls `cache.update()` before returning. The watchlist `GET /api/watchlist` response includes current prices; without the immediate seed, the new ticker would return `null` price until the next 500 ms loop tick.

---

## 7. Seed Prices and Correlation Data

**File**: `backend/app/market/seed_prices.py`

All static parameters for the simulator live here — separated from the logic so they can be changed without touching any algorithms.

```python
# backend/app/market/seed_prices.py

# Starting prices for the default 10-ticker watchlist
SEED_PRICES: dict[str, float] = {
    "AAPL":  190.00,
    "GOOGL": 175.00,
    "MSFT":  420.00,
    "AMZN":  185.00,
    "TSLA":  250.00,
    "NVDA":  800.00,
    "META":  500.00,
    "JPM":   195.00,
    "V":     280.00,
    "NFLX":  600.00,
}

# Per-ticker GBM parameters
# sigma: annualized volatility. Higher = more dramatic intraday swings.
# mu: annualized drift. Positive = upward bias over time.
TICKER_PARAMS: dict[str, dict[str, float]] = {
    "AAPL":  {"sigma": 0.22, "mu": 0.05},
    "GOOGL": {"sigma": 0.25, "mu": 0.05},
    "MSFT":  {"sigma": 0.20, "mu": 0.05},
    "AMZN":  {"sigma": 0.28, "mu": 0.05},
    "TSLA":  {"sigma": 0.50, "mu": 0.03},  # High vol; does its own thing
    "NVDA":  {"sigma": 0.40, "mu": 0.08},  # High vol + strong upward drift
    "META":  {"sigma": 0.30, "mu": 0.05},
    "JPM":   {"sigma": 0.18, "mu": 0.04},  # Bank — low volatility
    "V":     {"sigma": 0.17, "mu": 0.04},  # Payments — low volatility
    "NFLX":  {"sigma": 0.35, "mu": 0.05},
}

DEFAULT_PARAMS: dict[str, float] = {"sigma": 0.25, "mu": 0.05}

# Sector groups for Cholesky correlation
CORRELATION_GROUPS: dict[str, set[str]] = {
    "tech":    {"AAPL", "GOOGL", "MSFT", "AMZN", "META", "NVDA", "NFLX"},
    "finance": {"JPM", "V"},
}

INTRA_TECH_CORR    = 0.6  # Tech stocks move together
INTRA_FINANCE_CORR = 0.5  # Finance stocks move together
CROSS_GROUP_CORR   = 0.3  # Between sectors / unknown tickers
TSLA_CORR          = 0.3  # TSLA is in the tech group but ignores it
```

**Tuning guidance**:
- Increase `sigma` for more dramatic intraday swings (good for demos).
- Increase `INTRA_TECH_CORR` toward 1.0 for more "market crash" synchronized moves.
- Add new tickers to `SEED_PRICES` and `TICKER_PARAMS` for realistic behavior; omitting them means random seed price + default params.

---

## 8. Massive API — `MassiveDataSource`

**File**: `backend/app/market/massive_client.py`

Polls [Polygon.io](https://polygon.io) via the `massive` Python SDK. One API call fetches all tracked tickers at once.

### Installation

```bash
uv add massive   # or: pip install -U massive
```

### Snapshot Endpoint — The Core Call

All live polling uses a single batched endpoint:

```python
from massive import RESTClient
from massive.rest.models import SnapshotMarketType

client = RESTClient(api_key="YOUR_KEY")

# One call for ALL tickers — critical for staying within free-tier rate limits
snapshots = client.get_snapshot_all(
    market_type=SnapshotMarketType.STOCKS,
    tickers=["AAPL", "GOOGL", "MSFT", "AMZN", "TSLA"],
)

for snap in snapshots:
    ticker    = snap.ticker
    price     = snap.last_trade.price          # live/last trade price
    timestamp = snap.last_trade.timestamp / 1000.0  # ms → seconds
    day_open  = snap.day.open                  # session_open for daily % calc
    day_high  = snap.day.high
    day_low   = snap.day.low
    day_vol   = snap.day.volume
    day_chg   = snap.day.change_percent        # % change from prev close
```

### Ticker Validation (Massive mode only)

Before adding an unknown ticker to the watchlist, validate it exists on Polygon:

```python
from massive import RESTClient
from massive.rest.models import SnapshotMarketType

def validate_ticker(client: RESTClient, ticker: str) -> bool:
    """Returns True if Polygon has current data for this ticker."""
    try:
        snapshot = client.get_snapshot_ticker(
            market_type=SnapshotMarketType.STOCKS,
            ticker=ticker.upper(),
        )
        return snapshot is not None and snapshot.last_trade is not None
    except Exception:
        return False
```

This prevents users (or the LLM) from adding hallucinated or delisted symbols in real-data mode.

### Historical Bars (for charts)

```python
# Fetch 1-minute OHLCV bars for a date range (paginated automatically)
bars = []
for agg in client.list_aggs(
    ticker="AAPL",
    multiplier=1,
    timespan="minute",       # "second" | "minute" | "hour" | "day" | "week"
    from_="2024-01-15",
    to="2024-01-16",
    limit=50000,
):
    bars.append({
        "t": agg.timestamp / 1000,  # ms → seconds
        "o": agg.open,
        "h": agg.high,
        "l": agg.low,
        "c": agg.close,
        "v": agg.volume,
    })
```

### Previous Close

```python
# Seed prices on startup from previous day's close
prev = client.get_previous_close_agg(ticker="AAPL")
for agg in prev:
    print(f"Previous close: ${agg.close}")
```

### Rate Limits

| Tier | Limit | Default poll interval |
|------|-------|-----------------------|
| Free | 5 req/min | 15 s (`MASSIVE_POLL_INTERVAL_SECONDS=15`) |
| Starter (paid) | Unlimited | 5 s |
| Developer+ (paid) | Unlimited | 2 s |

Override via environment variable:
```bash
MASSIVE_POLL_INTERVAL_SECONDS=5  # for paid tier
```

### Complete `MassiveDataSource` Implementation

```python
# backend/app/market/massive_client.py
class MassiveDataSource(MarketDataSource):
    def __init__(
        self,
        api_key: str,
        price_cache: PriceCache,
        poll_interval: float = 15.0,
    ) -> None:
        self._api_key = api_key
        self._cache = price_cache
        self._interval = poll_interval
        self._tickers: list[str] = []
        self._task: asyncio.Task | None = None
        self._client: RESTClient | None = None

    async def start(self, tickers: list[str]) -> None:
        self._client = RESTClient(api_key=self._api_key)
        self._tickers = list(tickers)
        await self._poll_once()  # ← immediate first poll seeds the cache
        self._task = asyncio.create_task(self._poll_loop(), name="massive-poller")
        logger.info("Massive poller started: %d tickers, %.1fs interval",
                    len(tickers), self._interval)

    async def stop(self) -> None:
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        self._task = None
        self._client = None
        logger.info("Massive poller stopped")

    async def add_ticker(self, ticker: str) -> None:
        ticker = ticker.upper().strip()
        if ticker not in self._tickers:
            self._tickers.append(ticker)
            logger.info("Massive: added ticker %s (appears on next poll)", ticker)

    async def remove_ticker(self, ticker: str) -> None:
        ticker = ticker.upper().strip()
        self._tickers = [t for t in self._tickers if t != ticker]
        self._cache.remove(ticker)
        logger.info("Massive: removed ticker %s", ticker)

    def get_tickers(self) -> list[str]:
        return list(self._tickers)

    async def _poll_loop(self) -> None:
        while True:
            await asyncio.sleep(self._interval)
            await self._poll_once()

    async def _poll_once(self) -> None:
        """One poll cycle: fetch snapshots, update cache."""
        if not self._tickers or not self._client:
            return
        try:
            # RESTClient is synchronous — run in thread pool to keep event loop free
            snapshots = await asyncio.to_thread(self._fetch_snapshots)
            processed = 0
            for snap in snapshots:
                try:
                    price = snap.last_trade.price
                    timestamp = snap.last_trade.timestamp / 1000.0  # ms → seconds
                    self._cache.update(ticker=snap.ticker, price=price, timestamp=timestamp)
                    processed += 1
                except (AttributeError, TypeError) as e:
                    logger.warning("Skipping snapshot for %s: %s",
                                   getattr(snap, "ticker", "???"), e)
            logger.debug("Massive poll: updated %d/%d tickers", processed, len(self._tickers))
        except Exception as e:
            # Log and continue — retries automatically on next interval
            logger.error("Massive poll failed: %s", e)

    def _fetch_snapshots(self) -> list:
        """Synchronous REST call. Runs in asyncio.to_thread()."""
        return self._client.get_snapshot_all(
            market_type=SnapshotMarketType.STOCKS,
            tickers=self._tickers,
        )
```

**Error handling**:

| HTTP Status | Meaning | Behavior |
|------------|---------|----------|
| 401 | Invalid API key | Logged as error; loop continues |
| 429 | Rate limit | Logged as error; retries next interval |
| 5xx | Server error | Client retries 3×; logged if all fail |
| Network timeout | Connectivity issue | Logged; retries next interval |

The cache retains the last known price until a successful poll updates it — stale prices are visible in the UI but the app doesn't crash.

---

## 9. Factory — Source Selection

**File**: `backend/app/market/factory.py`

The single decision point. Reads `MASSIVE_API_KEY` from environment and returns the appropriate source.

```python
# backend/app/market/factory.py
import os
import logging
from .cache import PriceCache
from .interface import MarketDataSource
from .massive_client import MassiveDataSource
from .simulator import SimulatorDataSource

logger = logging.getLogger(__name__)


def create_market_data_source(price_cache: PriceCache) -> MarketDataSource:
    """Returns an unstarted MarketDataSource.

    - MASSIVE_API_KEY set → MassiveDataSource (real Polygon.io data)
    - Otherwise           → SimulatorDataSource (GBM simulation)

    poll_interval can be overridden via MASSIVE_POLL_INTERVAL_SECONDS.
    """
    api_key = os.environ.get("MASSIVE_API_KEY", "").strip()

    if api_key:
        interval = float(os.environ.get("MASSIVE_POLL_INTERVAL_SECONDS", "15"))
        logger.info("Market data source: Massive API (real data), %.0fs poll", interval)
        return MassiveDataSource(api_key=api_key, price_cache=price_cache,
                                 poll_interval=interval)
    else:
        logger.info("Market data source: GBM Simulator")
        return SimulatorDataSource(price_cache=price_cache)
```

**Environment variables**:

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `MASSIVE_API_KEY` | No | (absent) | Polygon.io API key; omit to use simulator |
| `MASSIVE_POLL_INTERVAL_SECONDS` | No | `15` | Poll interval in seconds for Massive mode |

---

## 10. SSE Streaming Endpoint

**File**: `backend/app/market/stream.py`

FastAPI router that streams all tracked prices to connected clients via Server-Sent Events.

```python
# backend/app/market/stream.py
import asyncio
import json
import logging
from collections.abc import AsyncGenerator

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from .cache import PriceCache

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/stream", tags=["streaming"])


def create_stream_router(price_cache: PriceCache) -> APIRouter:
    """Factory that captures the PriceCache reference without globals."""

    @router.get("/prices")
    async def stream_prices(request: Request) -> StreamingResponse:
        return StreamingResponse(
            _generate_events(price_cache, request),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",  # Disable nginx buffering for SSE
            },
        )

    return router


async def _generate_events(
    price_cache: PriceCache,
    request: Request,
    interval: float = 0.5,
) -> AsyncGenerator[str, None]:
    yield "retry: 1000\n\n"  # Client auto-reconnects after 1s on disconnect

    last_version = -1
    client_ip = request.client.host if request.client else "unknown"
    logger.info("SSE client connected: %s", client_ip)

    try:
        while True:
            if await request.is_disconnected():
                logger.info("SSE client disconnected: %s", client_ip)
                break

            current_version = price_cache.version
            if current_version != last_version:
                last_version = current_version
                prices = price_cache.get_all()
                if prices:
                    data = {ticker: update.to_dict() for ticker, update in prices.items()}
                    yield f"data: {json.dumps(data)}\n\n"

            await asyncio.sleep(interval)
    except asyncio.CancelledError:
        logger.info("SSE stream cancelled for: %s", client_ip)
```

### Wire Format

The SSE event payload is a JSON object keyed by ticker symbol:

```
data: {"AAPL": {"ticker": "AAPL", "price": 190.50, "previous_price": 190.20, "timestamp": 1716998400.123, "change": 0.3, "change_percent": 0.1577, "direction": "up"}, "GOOGL": {...}, ...}

```
(Two newlines end the event.)

### Client-Side Integration (TypeScript)

```typescript
const source = new EventSource("/api/stream/prices");

source.onmessage = (event) => {
  const prices: Record<string, PriceUpdate> = JSON.parse(event.data);

  for (const [ticker, update] of Object.entries(prices)) {
    // update.price        → current price (number)
    // update.direction    → "up" | "down" | "flat"
    // update.change       → absolute change (number)
    // update.change_percent → % change (number)
    updateTickerUI(ticker, update);
  }
};

// EventSource auto-reconnects on error (using the retry: 1000 directive)
source.onerror = () => console.warn("SSE reconnecting...");

// Clean up
source.close();
```

**Why SSE over WebSockets**: one-way push is all we need; SSE is universally supported without a library; EventSource handles reconnection automatically; no need for a separate WS upgrade handshake.

---

## 11. FastAPI Lifecycle Integration

Wire the market data subsystem into FastAPI's `lifespan` context manager. This is the correct place — it guarantees the data source is started before the first request and stopped after the last.

```python
# backend/app/main.py (abridged)
from contextlib import asynccontextmanager
from fastapi import FastAPI

from app.market import PriceCache, create_market_data_source, create_stream_router

DEFAULT_TICKERS = ["AAPL", "GOOGL", "MSFT", "AMZN", "TSLA", "NVDA", "META", "JPM", "V", "NFLX"]


@asynccontextmanager
async def lifespan(app: FastAPI):
    # ── 1. Create cache ───────────────────────────────────────────────────────
    cache = PriceCache()

    # ── 2. Compute initial ticker set: watchlist ∪ open positions ─────────────
    # (db module not shown — substitute your actual DB layer)
    initial_tickers = await db.get_tracked_tickers()  # returns list[str]
    if not initial_tickers:
        initial_tickers = DEFAULT_TICKERS

    # ── 3. Create and start the data source ───────────────────────────────────
    source = create_market_data_source(cache)
    await source.start(initial_tickers)
    # Cache is now seeded — all prices are available immediately

    # ── 4. Make source and cache available to route handlers ──────────────────
    app.state.market_source = source
    app.state.price_cache = cache

    yield  # ← app serves requests

    # ── 5. Cleanup ────────────────────────────────────────────────────────────
    await source.stop()


app = FastAPI(lifespan=lifespan)

# Register the SSE router — factory captures the cache reference
# This must run before lifespan, so cache is passed at router-creation time.
# Use app.state or a module-level variable depending on your startup order.
```

**Startup order matters**:

1. Create `PriceCache`
2. Compute `watchlist ∪ open_positions` from DB
3. `create_market_data_source(cache)` → returns unstarted source
4. `await source.start(tickers)` → **cache is warm before yield**
5. Record initial portfolio snapshot (prices are available)
6. `yield` — requests are now served

**Tracked ticker set rule**: actively priced tickers = `watchlist ∪ {tickers with non-zero open positions}`. Removing a ticker from the watchlist while an open position exists does **not** stop pricing. `remove_ticker()` is only called when a ticker leaves both sets.

---

## 12. Downstream Usage Patterns

### Reading a single price (trade execution, order fill)

```python
from app.market import PriceCache

async def execute_trade(cache: PriceCache, ticker: str, qty: float) -> dict:
    price = cache.get_price(ticker)
    if price is None:
        raise ValueError(f"No price available for {ticker}")

    fill_value = round(price * qty, 2)
    # ... write trade to DB ...
    return {"ticker": ticker, "qty": qty, "price": price, "total": fill_value}
```

### Portfolio valuation

```python
def calculate_portfolio_value(
    positions: list[dict],  # [{ticker, qty, avg_cost}, ...]
    cache: PriceCache,
) -> dict:
    total_market_value = 0.0
    enriched = []

    for pos in positions:
        price = cache.get_price(pos["ticker"]) or pos["avg_cost"]
        market_value = round(price * pos["qty"], 2)
        pnl = round((price - pos["avg_cost"]) * pos["qty"], 2)
        total_market_value += market_value
        enriched.append({**pos, "price": price, "market_value": market_value, "pnl": pnl})

    return {"positions": enriched, "total_market_value": round(total_market_value, 2)}
```

### Dynamic watchlist add/remove

```python
# In a watchlist route handler
async def add_to_watchlist(
    ticker: str,
    source: MarketDataSource,
    cache: PriceCache,
    db,
) -> dict:
    ticker = ticker.upper().strip()

    # In Massive mode: validate before inserting
    # (simulator mode accepts any syntactically valid ticker)
    if isinstance(source, MassiveDataSource):
        if not await validate_ticker_massive(ticker):
            raise HTTPException(status_code=422, detail={"code": "unknown_ticker"})

    await db.insert_watchlist(ticker)
    await source.add_ticker(ticker)  # seeds cache immediately (sim) or next poll (massive)

    # Price is already available (simulator) or will be on next poll (massive)
    update = cache.get(ticker)
    return {"ticker": ticker, "price": update.price if update else None}


async def remove_from_watchlist(ticker: str, source: MarketDataSource, db) -> None:
    await db.delete_watchlist(ticker)
    has_open_position = await db.has_open_position(ticker)

    if not has_open_position:
        await source.remove_ticker(ticker)  # also removes from cache
```

### Getting a snapshot for the watchlist endpoint

```python
def build_watchlist_response(tickers: list[str], cache: PriceCache) -> list[dict]:
    result = []
    for ticker in tickers:
        update = cache.get(ticker)
        if update:
            result.append({
                "ticker": ticker,
                "price": update.price,
                "change": update.change,
                "change_percent": update.change_percent,
                "direction": update.direction,
                "timestamp": update.timestamp,
            })
        else:
            result.append({"ticker": ticker, "price": None})
    return result
```

---

## 13. Testing Strategy

The test suite lives in `backend/tests/market/`. 73 tests, all passing.

### Module Coverage

| Test file | What it covers | Tests |
|-----------|----------------|-------|
| `test_models.py` | `PriceUpdate` properties, `to_dict()`, edge cases | 11 |
| `test_cache.py` | Thread safety, version counter, all CRUD ops | 13 |
| `test_simulator.py` | `GBMSimulator.step()`, Cholesky, shock events | 17 |
| `test_simulator_source.py` | `SimulatorDataSource` start/stop/add/remove | 10 |
| `test_factory.py` | Env var selection, both modes | 7 |
| `test_massive.py` | `MassiveDataSource` poll loop, error handling | 13 |

### Example Test Patterns

**Testing `PriceUpdate` direction**:
```python
def test_direction_up():
    u = PriceUpdate(ticker="AAPL", price=100.0, previous_price=99.0, timestamp=0.0)
    assert u.direction == "up"
    assert u.change == 1.0
    assert u.change_percent == pytest.approx(1.0101, rel=1e-3)

def test_first_update_is_flat():
    u = PriceUpdate(ticker="AAPL", price=100.0, previous_price=100.0, timestamp=0.0)
    assert u.direction == "flat"
    assert u.change == 0.0
```

**Testing `PriceCache` thread safety**:
```python
import threading

def test_concurrent_writes():
    cache = PriceCache()
    errors = []

    def writer(ticker):
        for i in range(100):
            try:
                cache.update(ticker, float(100 + i))
            except Exception as e:
                errors.append(e)

    threads = [threading.Thread(target=writer, args=(t,)) for t in ["AAPL", "GOOGL", "MSFT"]]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert not errors
    assert len(cache) == 3
```

**Testing the simulator produces valid prices**:
```python
def test_prices_always_positive():
    sim = GBMSimulator(["AAPL", "TSLA", "NVDA"])
    for _ in range(1000):
        prices = sim.step()
        for ticker, price in prices.items():
            assert price > 0, f"{ticker} went negative: {price}"
```

**Testing the factory reads env vars**:
```python
def test_factory_returns_simulator_without_key(monkeypatch):
    monkeypatch.delenv("MASSIVE_API_KEY", raising=False)
    cache = PriceCache()
    source = create_market_data_source(cache)
    assert isinstance(source, SimulatorDataSource)

def test_factory_returns_massive_with_key(monkeypatch):
    monkeypatch.setenv("MASSIVE_API_KEY", "test-key-123")
    cache = PriceCache()
    source = create_market_data_source(cache)
    assert isinstance(source, MassiveDataSource)
```

**Testing `MassiveDataSource` poll with mocked client**:
```python
import pytest
from unittest.mock import MagicMock, patch

@pytest.mark.asyncio
async def test_poll_updates_cache():
    cache = PriceCache()
    source = MassiveDataSource(api_key="test", price_cache=cache)

    mock_snap = MagicMock()
    mock_snap.ticker = "AAPL"
    mock_snap.last_trade.price = 191.50
    mock_snap.last_trade.timestamp = 1716998400000  # ms

    # Set _client before calling _poll_once (bypasses start())
    source._client = MagicMock()
    source._tickers = ["AAPL"]

    with patch.object(source, "_fetch_snapshots", return_value=[mock_snap]):
        await source._poll_once()

    assert cache.get_price("AAPL") == 191.50
```

### Running Tests

```bash
cd backend
uv run pytest tests/market/ -v
uv run pytest tests/market/ --cov=app/market --cov-report=term-missing
```

---

## 14. Module Map and File Reference

```
backend/
├── app/
│   └── market/
│       ├── __init__.py        Public API re-exports
│       ├── models.py          PriceUpdate frozen dataclass
│       ├── cache.py           PriceCache — thread-safe price store
│       ├── interface.py       MarketDataSource — abstract base class
│       ├── seed_prices.py     SEED_PRICES, TICKER_PARAMS, correlation constants
│       ├── simulator.py       GBMSimulator + SimulatorDataSource
│       ├── massive_client.py  MassiveDataSource — Polygon.io REST poller
│       ├── factory.py         create_market_data_source() — env-driven selection
│       └── stream.py          create_stream_router() — FastAPI SSE endpoint
├── tests/
│   └── market/
│       ├── test_models.py
│       ├── test_cache.py
│       ├── test_simulator.py
│       ├── test_simulator_source.py
│       ├── test_factory.py
│       └── test_massive.py
└── market_data_demo.py        Rich terminal dashboard demo (uv run market_data_demo.py)
```

### Public API (`app/market/__init__.py`)

```python
from app.market import (
    PriceUpdate,               # Immutable price snapshot
    PriceCache,                # Thread-safe in-memory store
    MarketDataSource,          # Abstract interface
    create_market_data_source, # Factory: simulator or Massive
    create_stream_router,      # FastAPI SSE router factory
)
```

### Environment Variables Summary

| Variable | Required | Default | Effect |
|----------|----------|---------|--------|
| `MASSIVE_API_KEY` | No | (absent) | Set to enable real Polygon.io data |
| `MASSIVE_POLL_INTERVAL_SECONDS` | No | `15` | Poll frequency; lower for paid Polygon tiers |

### Quick Start — Demo

```bash
cd backend
uv run market_data_demo.py
```

Displays a live Rich terminal dashboard with all 10 tickers, sparklines, color-coded direction arrows, and an event log for notable price moves. Runs 60 seconds or until Ctrl+C. No API key required.
