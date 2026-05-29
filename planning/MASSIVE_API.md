# Massive API Reference (Polygon.io)

The `massive` Python package is the Polygon.io REST client used in FinAlly for real market data. "Massive" is the SDK name; the underlying provider is **Polygon.io**. When reading official Polygon docs, look for Polygon.io REST API documentation.

---

## Installation and Auth

```bash
uv add massive   # or: pip install -U massive
```

```python
from massive import RESTClient

# Reads MASSIVE_API_KEY from environment automatically
client = RESTClient()

# Or pass the key explicitly
client = RESTClient(api_key="YOUR_KEY_HERE")
```

**Auth header**: `Authorization: Bearer <API_KEY>` — the client handles this automatically.

**Base URL**: `https://api.polygon.io` (the client targets this; "Massive" is the SDK wrapper name only).

---

## Rate Limits

| Tier | Limit | Recommended poll interval |
|------|-------|--------------------------|
| Free | 5 requests / minute | 15 s |
| Starter (paid) | Unlimited | 5 s |
| Developer+ (paid) | Unlimited | 2 s |

FinAlly polls on a timer. The default interval (`MASSIVE_POLL_INTERVAL_SECONDS=15`) is safe for the free tier. Lower it for paid tiers.

---

## Endpoints Used in FinAlly

### 1. Snapshot — All Tickers (Primary)

Fetches current prices for **multiple tickers in a single API call**. This is the only endpoint used for the live polling loop.

**REST**: `GET /v2/snapshot/locale/us/markets/stocks/tickers?tickers=AAPL,GOOGL,MSFT`

**Python client**:
```python
from massive import RESTClient
from massive.rest.models import SnapshotMarketType

client = RESTClient()

snapshots = client.get_snapshot_all(
    market_type=SnapshotMarketType.STOCKS,
    tickers=["AAPL", "GOOGL", "MSFT", "AMZN", "TSLA"],
)

for snap in snapshots:
    ticker = snap.ticker
    price = snap.last_trade.price
    # Timestamps are Unix milliseconds — convert to seconds for our cache
    ts_seconds = snap.last_trade.timestamp / 1000.0

    print(f"{ticker}: ${price:.2f} @ {ts_seconds}")
    print(f"  Day open: {snap.day.open}")
    print(f"  Day change: {snap.day.change_percent:.2f}%")
    print(f"  Volume: {snap.day.volume:,}")
```

**Response fields per ticker** (key fields only):

```
snap.ticker                   # "AAPL"
snap.last_trade.price         # Current/last trade price — used as live price
snap.last_trade.size          # Shares in last trade
snap.last_trade.timestamp     # Unix milliseconds
snap.last_quote.bid_price     # Best bid
snap.last_quote.ask_price     # Best ask
snap.day.open                 # Day open price  ← used as session_open
snap.day.high                 # Day high
snap.day.low                  # Day low
snap.day.close                # Day close (current if market open)
snap.day.volume               # Volume today
snap.day.change               # Absolute change from prev close
snap.day.change_percent       # Percentage change from prev close
snap.day.previous_close       # Previous session close price
```

**What FinAlly extracts**:
- `snap.last_trade.price` → live price, written to `PriceCache`
- `snap.last_trade.timestamp` → converted ms→s, written to `PriceCache`
- `snap.day.open` → `session_open` for daily change % calculation

**Why this endpoint**: It batches all tickers into one HTTP request, which is critical for staying within the free tier's 5 req/min limit.

---

### 2. Single Ticker Snapshot

For fetching detailed data on one specific ticker (e.g., when validating a user-requested symbol).

**REST**: `GET /v2/snapshot/locale/us/markets/stocks/tickers/{ticker}`

```python
from massive import RESTClient
from massive.rest.models import SnapshotMarketType

client = RESTClient()

snapshot = client.get_snapshot_ticker(
    market_type=SnapshotMarketType.STOCKS,
    ticker="AAPL",
)

if snapshot:
    print(f"Price: ${snapshot.last_trade.price}")
    print(f"Day open: ${snapshot.day.open}")
    print(f"Bid/Ask: ${snapshot.last_quote.bid_price} / ${snapshot.last_quote.ask_price}")
    print(f"Day range: ${snapshot.day.low} – ${snapshot.day.high}")
```

Used in Massive mode to **validate a ticker** before adding it to the watchlist. If Polygon returns no data (or raises), the ticker is unknown (hallucinated symbol, delisted, etc.) and the add is rejected.

---

### 3. Previous Close (EOD)

Gets the previous day's OHLCV bar for a ticker. Useful for seeding prices on startup or getting end-of-day reference prices.

**REST**: `GET /v2/aggs/ticker/{ticker}/prev`

```python
client = RESTClient()

prev = client.get_previous_close_agg(ticker="AAPL")

for agg in prev:
    print(f"Previous close: ${agg.close}")
    print(f"OHLCV: O={agg.open} H={agg.high} L={agg.low} C={agg.close} V={agg.volume}")
    print(f"Timestamp (ms): {agg.timestamp}")
```

**Response fields**:
```
agg.open       # Day open
agg.high       # Day high
agg.low        # Day low
agg.close      # Day close  ← use as previous_close reference
agg.volume     # Total volume
agg.timestamp  # Unix milliseconds for the bar
```

---

### 4. Aggregates / Historical Bars

Historical OHLCV bars over a date range. Not used in the current live polling loop but available for populating the main chart with historical data.

**REST**: `GET /v2/aggs/ticker/{ticker}/range/{multiplier}/{timespan}/{from}/{to}`

```python
client = RESTClient()

# Fetch 1-minute bars for AAPL over a date range
bars = []
for agg in client.list_aggs(
    ticker="AAPL",
    multiplier=1,
    timespan="minute",   # "second", "minute", "hour", "day", "week", "month", "quarter", "year"
    from_="2024-01-15",
    to="2024-01-16",
    limit=50000,         # max 50,000 results per call; iterator handles pagination
):
    bars.append(agg)

for bar in bars:
    print(f"t={bar.timestamp}ms  O={bar.open} H={bar.high} L={bar.low} C={bar.close} V={bar.volume}")
```

**Timespan values**: `second`, `minute`, `hour`, `day`, `week`, `month`, `quarter`, `year`

**Key fields**:
```
agg.timestamp  # Bar start time, Unix milliseconds
agg.open       # Open price
agg.high       # High price
agg.low        # Low price
agg.close      # Close price
agg.volume     # Volume
agg.vwap       # Volume-weighted average price (not always present)
```

`list_aggs` is an iterator that handles pagination automatically — no manual page/cursor management needed.

---

### 5. Last Trade / Last Quote

Point-in-time endpoints for the single most recent trade or NBBO quote on one ticker.

```python
client = RESTClient()

# Most recent trade
trade = client.get_last_trade(ticker="AAPL")
print(f"Last trade: ${trade.price} × {trade.size} shares")
print(f"Exchange: {trade.exchange}, timestamp (ns): {trade.participant_timestamp}")

# Most recent NBBO quote
quote = client.get_last_quote(ticker="AAPL")
print(f"Bid: ${quote.bid_price} × {quote.bid_size}")
print(f"Ask: ${quote.ask_price} × {quote.ask_size}")
```

These are not used in the main polling loop (the snapshot endpoint is more efficient), but they can be useful for validating a ticker is actively traded.

---

## How FinAlly Uses the API

The Massive poller (`MassiveDataSource`) runs as a background asyncio task. Flow per poll cycle:

1. Collect all tracked tickers (watchlist ∪ open positions) from the internal list.
2. Call `get_snapshot_all()` — one API call for all tickers.
3. For each snapshot: extract `last_trade.price` and `last_trade.timestamp`.
4. Call `price_cache.update(ticker, price, timestamp)` to write to the shared cache.
5. Sleep for `poll_interval` seconds, then repeat.

The Massive REST client is **synchronous** — all calls block the calling thread. FinAlly runs it via `asyncio.to_thread()` to keep the event loop unblocked:

```python
# Inside MassiveDataSource._poll_once()
snapshots = await asyncio.to_thread(self._fetch_snapshots)

# _fetch_snapshots is a plain synchronous method:
def _fetch_snapshots(self) -> list:
    return self._client.get_snapshot_all(
        market_type=SnapshotMarketType.STOCKS,
        tickers=self._tickers,
    )
```

**Ticker validation** (Massive mode only) — before adding an unknown ticker to the watchlist, the backend probes Polygon with `get_snapshot_ticker()` to confirm the symbol is valid. Timeout is 5 s. If no data is returned, the add is rejected with `code: "unknown_ticker"`.

---

## Error Handling

The Massive client raises exceptions on HTTP errors:

| HTTP Status | Meaning | FinAlly behavior |
|-------------|---------|-----------------|
| 401 | Invalid API key | Logged as error; poll loop continues and retries on next interval |
| 403 | Plan doesn't include endpoint | Logged as error |
| 429 | Rate limit exceeded | Logged as error; automatic retry on next interval |
| 5xx | Server error | Client has built-in retry (3 retries); logged if all retries fail |

FinAlly wraps the poll call in a broad `except Exception` block — poll failures are logged but don't crash the background task. The price cache retains the last known price until a successful poll updates it.

```python
try:
    snapshots = await asyncio.to_thread(self._fetch_snapshots)
    # ... process snapshots ...
except Exception as e:
    logger.error("Massive poll failed: %s", e)
    # Loop continues — retries on next interval
```

---

## Behavior Notes

- **After-hours prices**: During market closed hours, `last_trade.price` is the last traded price, which may include after-hours/pre-market activity.
- **Market open reset**: The `day` object (open, high, low, volume, change%) resets at the exchange's daily open boundary. During pre-market, values may reflect the previous session.
- **Timestamps**: All timestamps from Polygon are **Unix milliseconds** — always divide by 1000 to get seconds for the `PriceCache`.
- **Empty results**: `get_snapshot_all()` may return fewer results than tickers requested (e.g., if a symbol is delisted). The loop handles this gracefully by iterating what's returned.
- **Symbol format**: Tickers must be uppercase (e.g., `"AAPL"`, not `"aapl"`). The server normalizes before sending to Polygon.
