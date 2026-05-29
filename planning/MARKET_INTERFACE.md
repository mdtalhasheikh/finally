# Market Data Interface

Unified Python interface for market data in FinAlly. Two implementations — `SimulatorDataSource` and `MassiveDataSource` — behind one abstract interface. All downstream code (SSE streaming, trade execution, portfolio valuation) is source-agnostic and reads from a shared `PriceCache`.

---

## Architecture

```
MarketDataSource (ABC)
├── SimulatorDataSource   ← GBM simulator (default; no API key needed)
└── MassiveDataSource     ← Polygon.io REST poller (MASSIVE_API_KEY set)
         │
         ▼
    PriceCache  (thread-safe, in-memory, one per process)
         │
         ├──→ GET /api/stream/prices  (SSE streaming)
         ├──→ Portfolio valuation      (GET /api/portfolio)
         └──→ Trade execution          (POST /api/portfolio/trade)
```

**Key invariant**: only the active data source writes to the cache. All other code only reads. No component talks to the data source directly for prices.

---

## File Structure

```
backend/
  app/
    market/
      __init__.py          # Re-exports: PriceCache, PriceUpdate, MarketDataSource,
      │                    #             create_market_data_source, create_stream_router
      models.py            # PriceUpdate frozen dataclass
      cache.py             # PriceCache — thread-safe price store
      interface.py         # MarketDataSource — abstract base class
      factory.py           # create_market_data_source() — env-driven selection
      massive_client.py    # MassiveDataSource — Polygon.io REST poller
      simulator.py         # GBMSimulator + SimulatorDataSource
      seed_prices.py       # SEED_PRICES, TICKER_PARAMS, correlation constants
      stream.py            # create_stream_router() — FastAPI SSE endpoint factory
```

---

## Core Types

### PriceUpdate (`models.py`)

Immutable, frozen dataclass. The only price representation that leaves the market data layer.

```python
@dataclass(frozen=True, slots=True)
class PriceUpdate:
    ticker: str
    price: float           # Current price, rounded to 2 decimal places
    previous_price: float  # Price from the immediately preceding update
    timestamp: float       # Unix seconds

    # Computed properties (not stored)
    @property
    def change(self) -> float: ...          # price - previous_price, rounded to 4dp
    @property
    def change_percent(self) -> float: ... # (change / previous_price) * 100, rounded to 4dp
    @property
    def direction(self) -> str: ...         # "up", "down", or "flat"

    def to_dict(self) -> dict: ...          # JSON-serializable; used by SSE stream
```

`to_dict()` returns:
```json
{
  "ticker": "AAPL",
  "price": 190.50,
  "previous_price": 190.20,
  "timestamp": 1716998400.0,
  "change": 0.3,
  "change_percent": 0.1577,
  "direction": "up"
}
```

**Note on `previous_price`**: this is the previous *tick's* price (last `PriceCache.update()` call), not the previous day's close. For daily change %, use `session_open` from the portfolio/watchlist endpoints.

---

### PriceCache (`cache.py`)

Thread-safe in-memory store. One instance per process, shared by the data source (writer) and all consumers (readers).

```python
class PriceCache:
    # --- Writer API ---
    def update(self, ticker: str, price: float, timestamp: float | None = None) -> PriceUpdate:
        """Record a new price. If first update for ticker, previous_price == price (direction='flat').
        Increments the version counter."""

    def remove(self, ticker: str) -> None:
        """Remove a ticker from the cache (called when ticker removed from watchlist + positions)."""

    # --- Reader API ---
    def get(self, ticker: str) -> PriceUpdate | None:
        """Latest PriceUpdate for a ticker, or None if not tracked."""

    def get_price(self, ticker: str) -> float | None:
        """Convenience: current price float, or None."""

    def get_all(self) -> dict[str, PriceUpdate]:
        """Snapshot of all tracked tickers. Returns a shallow copy (safe to iterate)."""

    # --- SSE change detection ---
    @property
    def version(self) -> int:
        """Monotonically increasing counter. Increments on every update() call.
        SSE generator compares version before emitting to avoid duplicate events."""

    # --- Introspection ---
    def __len__(self) -> int: ...       # Number of tracked tickers
    def __contains__(self, ticker): ... # ticker in cache
```

**Concurrency model**: `update()`, `get()`, `get_all()`, `remove()` all acquire a `threading.Lock`. The data source writes from an asyncio task (which runs in the event loop thread or a thread pool); the SSE generator reads from the same event loop thread. The lock prevents torn reads.

---

## Abstract Interface (`interface.py`)

```python
class MarketDataSource(ABC):
    @abstractmethod
    async def start(self, tickers: list[str]) -> None:
        """Initialize with the given tickers and start the background update task.
        Call exactly once. Immediately seeds the PriceCache with initial prices
        so SSE and portfolio endpoints have data on first request."""

    @abstractmethod
    async def stop(self) -> None:
        """Cancel the background task and release resources.
        Safe to call multiple times."""

    @abstractmethod
    async def add_ticker(self, ticker: str) -> None:
        """Add a ticker to the active set. No-op if already present.
        The cache is seeded with an initial price immediately (simulator)
        or on the next poll cycle (Massive)."""

    @abstractmethod
    async def remove_ticker(self, ticker: str) -> None:
        """Remove a ticker from the active set and from the PriceCache.
        No-op if not present."""

    @abstractmethod
    def get_tickers(self) -> list[str]:
        """Return the current list of actively tracked tickers."""
```

---

## Factory (`factory.py`)

Selects the implementation at startup based on the environment variable.

```python
def create_market_data_source(price_cache: PriceCache) -> MarketDataSource:
    api_key = os.environ.get("MASSIVE_API_KEY", "").strip()

    if api_key:
        # Real market data via Polygon.io REST API
        return MassiveDataSource(api_key=api_key, price_cache=price_cache)
    else:
        # GBM simulation (default, no API key required)
        return SimulatorDataSource(price_cache=price_cache)
```

The returned source is **unstarted** — the caller must `await source.start(tickers)`.

---

## MassiveDataSource (`massive_client.py`)

Polls the Polygon.io snapshot endpoint on a configurable interval.

```python
class MassiveDataSource(MarketDataSource):
    def __init__(
        self,
        api_key: str,
        price_cache: PriceCache,
        poll_interval: float = 15.0,  # seconds; safe for Polygon free tier (5 req/min)
    ) -> None: ...
```

**Lifecycle**:
1. `start(tickers)` — creates the `RESTClient`, does one immediate poll to seed the cache, then starts the background `asyncio.Task`.
2. Background loop: `sleep(interval)` → `poll_once()` → repeat.
3. `poll_once()` calls `get_snapshot_all()` via `asyncio.to_thread()` (the Massive client is synchronous), then calls `cache.update()` for each snapshot.
4. `stop()` — cancels the task and clears the client reference.

**Error handling**: poll failures are caught and logged; the loop continues and retries on the next interval. Common failures: 401 (bad key), 429 (rate limit), network timeout.

**Ticker normalization**: `add_ticker()` and `remove_ticker()` call `.upper().strip()` before modifying the list.

**poll_interval override**: pass `MASSIVE_POLL_INTERVAL_SECONDS` env var and use it when constructing `MassiveDataSource`:
```python
interval = float(os.environ.get("MASSIVE_POLL_INTERVAL_SECONDS", "15"))
MassiveDataSource(api_key=key, price_cache=cache, poll_interval=interval)
```

---

## SimulatorDataSource (`simulator.py`)

Wraps `GBMSimulator` in an asyncio task that steps the simulation every 500 ms.

```python
class SimulatorDataSource(MarketDataSource):
    def __init__(
        self,
        price_cache: PriceCache,
        update_interval: float = 0.5,     # seconds between GBM steps
        event_probability: float = 0.001, # per-tick shock probability
    ) -> None: ...
```

**Lifecycle**:
1. `start(tickers)` — creates `GBMSimulator`, seeds the cache with initial prices (so SSE has data before the first step completes), starts the background task.
2. Background loop: `sim.step()` → `cache.update()` for each ticker → `sleep(0.5s)` → repeat.
3. `add_ticker(ticker)` — delegates to `GBMSimulator.add_ticker()`, then immediately seeds the cache with the new ticker's starting price.
4. `stop()` — cancels the task.

Any syntactically valid ticker (`^[A-Z]{1,8}$`) is accepted. Unknown tickers get a random seed price between $50–$300 and default GBM parameters (σ=0.25, μ=0.05).

---

## SSE Streaming (`stream.py`)

The SSE endpoint is created via a factory function that captures the `PriceCache` reference.

```python
from app.market import create_stream_router

router = create_stream_router(price_cache)
app.include_router(router)
# Registers: GET /api/stream/prices
```

**Streaming logic**:
- Sends `retry: 1000\n\n` on connect (1 s auto-reconnect if the connection drops).
- Checks `price_cache.version` every 500 ms. Only emits an event when the version has changed, avoiding duplicate sends when there are no new prices.
- Payload is a JSON object keyed by ticker: `{"AAPL": {...PriceUpdate.to_dict()...}, "GOOGL": {...}, ...}`.
- Detects client disconnect via `request.is_disconnected()` and exits the generator cleanly.
- Sets `X-Accel-Buffering: no` to disable nginx response buffering for SSE connections.

**Client-side** (EventSource API, no library needed):
```typescript
const source = new EventSource("/api/stream/prices");
source.onmessage = (event) => {
    const prices = JSON.parse(event.data);
    // prices["AAPL"].price, prices["AAPL"].direction, etc.
};
source.onerror = () => { /* EventSource auto-reconnects */ };
```

---

## Lifecycle in FastAPI

Wire the market data system into FastAPI's `lifespan` context manager. The sequence must be:

1. Create `PriceCache`
2. Compute initial tracked tickers: `watchlist ∪ open_positions` (from DB)
3. Create market data source via factory
4. `await source.start(tickers)` — cache is seeded before any request is served
5. Record an initial `portfolio_snapshots` row (cache is warm, valuation is valid)
6. Start the 30 s portfolio snapshot background task
7. Yield (app serves requests)
8. `await source.stop()` on shutdown

```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    cache = PriceCache()
    initial_tickers = await db.get_tracked_tickers()   # watchlist ∪ positions
    source = create_market_data_source(cache)
    await source.start(initial_tickers)

    # App is now ready — cache has prices for all tickers
    yield {"market_source": source, "price_cache": cache}

    await source.stop()
```

---

## Tracked Ticker Set

The set of tickers the market source actively prices is **`watchlist ∪ {tickers with non-zero open positions}`**, not just the watchlist.

- Removing a ticker from the watchlist while an open position exists does **not** stop pricing.
- `remove_ticker()` is only called when a ticker leaves **both** sets (removed from watchlist *and* position fully closed).
- On startup, the backend computes this union from the DB before calling `source.start()`.

---

## Usage Reference

```python
from app.market import PriceCache, PriceUpdate, create_market_data_source

# Startup (inside lifespan)
cache = PriceCache()
source = create_market_data_source(cache)
await source.start(["AAPL", "GOOGL", "MSFT", "AMZN", "TSLA", "NVDA", "META", "JPM", "V", "NFLX"])

# Reading prices (trade execution, portfolio valuation)
update: PriceUpdate | None = cache.get("AAPL")
price: float | None = cache.get_price("AAPL")
all_prices: dict[str, PriceUpdate] = cache.get_all()

# Dynamic watchlist changes
await source.add_ticker("PYPL")
await source.remove_ticker("NFLX")

# Shutdown
await source.stop()
```
