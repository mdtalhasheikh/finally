# Code Review

_Generated: 2026-05-29 17:31:01_
_Base: `c529091` (Initial commit)_

---

## Code Review

**Base:** `c529091` (Initial commit) — reviewing all untracked files.

---

## 1. Summary

This is the initial project state. The market data subsystem (`backend/app/market/`) is complete and tested: GBM simulator, Massive/Polygon.io client, price cache, SSE streaming, and factory, with 73 tests at 84% coverage. The rest of the platform (database layer, portfolio/trade/chat routes, frontend, Dockerfile, scripts) is planned but not yet built.

---

## 2. Issues Found

### CRITICAL — Security

**`.env` contains a live API key.**
```
OPENROUTER_API_KEY = REDACTED_API_KEY
```
The file is currently untracked, which is the only thing preventing a leak. There is **no `.gitignore`** in the repo. A single `git add .` commits this key publicly. Rotate the key and create `.gitignore` before any further commits.

Minimum `.gitignore`:
```
.env
.DS_Store
__pycache__/
*.pyc
.pytest_cache/
.coverage
backend/.venv/
db/finally.db
```

---

### HIGH — `session_open` missing from `PriceUpdate` and `PriceCache`

`PLAN.md` Section 6 explicitly states:
> `session_open` is an explicit field on the `PriceUpdate` model and the `PriceCache`

`backend/app/market/models.py` has no `session_open` field. `cache.py:update()` doesn't capture or store it. `to_dict()` doesn't emit it.

Every downstream API (`GET /api/watchlist`, `GET /api/portfolio`, SSE events) is specified to return `session_open` and `daily_change_pct`. This requires retroactive patches to `models.py`, `cache.py`, `simulator.py`, and `massive_client.py` — catching it now costs an hour, catching it at API build time costs a day.

Recommended fix:
```python
# models.py
@dataclass(frozen=True, slots=True)
class PriceUpdate:
    ticker: str
    price: float
    previous_price: float
    session_open: float          # add this
    timestamp: float = field(default_factory=time.time)
```
```python
# cache.py - hold session_open on first insert, never overwrite it
def update(self, ticker: str, price: float, session_open: float | None = None, ...) -> PriceUpdate:
    prev = self._prices.get(ticker)
    captured_open = prev.session_open if prev else (session_open or price)
```

---

### MEDIUM — `stream.py` module-level router is a latent footgun

`stream.py:16` creates `router = APIRouter(...)` at module scope. `create_stream_router()` then registers the `/prices` route on it via closure. If the function is called twice (common in tests), the route registers twice on the same router object — undefined behavior. The router should be created inside `create_stream_router()`:

```python
def create_stream_router(price_cache: PriceCache) -> APIRouter:
    router = APIRouter(prefix="/api/stream", tags=["streaming"])  # ← create here
    
    @router.get("/prices")
    async def stream_prices(request: Request) -> StreamingResponse:
        ...
    
    return router
```

---

### MEDIUM — `SimulatorDataSource.get_tickers()` accesses private state

`simulator.py:254`:
```python
def get_tickers(self) -> list[str]:
    return list(self._sim._tickers) if self._sim else []
```
`GBMSimulator` already has a public `get_tickers()` method. Use it:
```python
return self._sim.get_tickers() if self._sim else []
```

---

### LOW — `_generate_events` return type annotation

`stream.py` annotates the async generator as `-> None`. The correct annotation is `-> AsyncGenerator[str, None]`. This misleads type checkers and readers.

---

### LOW — `conftest.py` `event_loop_policy` fixture shape

```python
@pytest.fixture
def event_loop_policy():
    return asyncio.DefaultEventLoopPolicy()  # returns object, not a generator
```
The lockfile pins `pytest-asyncio==1.3.0`. At this version, the recognized `event_loop_policy` fixture should yield or be a generator. Verify the shape against installed docs — this may silently have no effect.

---

### LOW — `DEFAULT_CORR` is dead code

`seed_prices.py:48` defines `DEFAULT_CORR = 0.3`, but `_pairwise_correlation()` falls through to `return CROSS_GROUP_CORR` (also 0.3). `DEFAULT_CORR` is never referenced. Remove it or rename `CROSS_GROUP_CORR` to `DEFAULT_CORR` to clarify intent.

---

## 3. Code Quality

**Strengths:**
- GBM math is correct: `exp((μ - 0.5σ²)dt + σ√dt·Z)` with Cholesky-decomposed correlated draws. Sector correlations (tech 0.6, finance 0.5, cross 0.3) are reasonable.
- `PriceCache` thread-safety with `threading.Lock` is necessary and correct — the Massive client runs in `asyncio.to_thread()`.
- Both data sources implement clean lifecycle (`start/stop/add/remove`) and are fully cancellable.
- Factory correctly `.strip()`s the API key before the empty-string check.
- Test suite uses `pytest.approx` for float comparisons; 84% coverage is solid.

**Gaps:**
- `stream.py` has 31% coverage. An integration test using `httpx.AsyncClient` with ASGI transport would validate the event format and disconnect detection with minimal effort.
- No `backend/app/main.py` — the subsystem is complete but has no FastAPI app to wire into (expected at this project stage).
- `litellm` and `pydantic` are not yet in `pyproject.toml`. They'll be needed for the chat feature; adding them early avoids a lockfile churn later.

---

## 4. Suggestions

**Immediate (before any further work):**

1. Create `.gitignore` (see above)
2. Rotate the OpenRouter API key — treat it as compromised given it appeared in shell output and review files
3. Add `session_open` to `PriceUpdate` and `PriceCache` now, while the cost is low

**Before API layer build:**

4. Fix `stream.py` router scope (move creation inside `create_stream_router()`)
5. Fix `SimulatorDataSource.get_tickers()` to use `self._sim.get_tickers()`
6. Fix `_generate_events` return type to `AsyncGenerator[str, None]`
7. Remove or consolidate `DEFAULT_CORR` vs `CROSS_GROUP_CORR`

---

## 5. Risk Assessment: **HIGH** (driven by the exposed API key)

Rotate the key first — everything else is medium or low. The `session_open` gap is the second priority; it will require touching 4+ already-written files and all their tests if deferred to the API build phase. The rest of the market data subsystem is solid and will integrate cleanly with the planned architecture.
ince the Massive client runs via `asyncio.to_thread`.
- Both data sources have clean cancellable lifecycle (`asyncio.Task.cancel()` + `CancelledError` handling).
- `PriceUpdate` is correctly `frozen=True, slots=True` — safe to share across threads without copying.
- SSE version-based change detection avoids duplicate sends.
- Exception resilience in both `_run_loop` and `_poll_once` — poll failures are logged and the loop continues.
- `pyproject.toml` has the `hatchling` build config (`packages = ["app"]`) — avoids a known `uv sync` failure.

**Test coverage gaps:**
- `stream.py` at 31% has no meaningful tests. At minimum, one test using `httpx.AsyncClient` + ASGI transport to verify SSE events are emitted would catch regressions.
- No concurrency test for `PriceCache` under simultaneous writes from multiple threads.
- No test with all 10 default tickers to confirm the Cholesky decomposition succeeds for the full correlation matrix.

**Minor style:**
- `massive_client.py` type-annotates `self._client: Any` — once the import moves to module level, annotate it as `RESTClient | None`.

---

## 4. Suggestions

**Highest priority — `session_open` (add now, before any API code is written):**

In `models.py`, add the field:
```python
@dataclass(frozen=True, slots=True)
class PriceUpdate:
    ticker: str
    price: float
    previous_price: float
    timestamp: float
    session_open: float  # First observed price this process lifetime (sim) / day open (Massive)
```

In `cache.py`, track it in `update()`:
```python
def update(self, ticker, price, timestamp=None, session_open=None):
    with self._lock:
        prev = self._prices.get(ticker)
        so = session_open if session_open is not None else (prev.session_open if prev else price)
        ...
        update = PriceUpdate(..., session_open=so)
```

In `simulator.py`, `start()` and `add_ticker()` need no changes — the cache will capture the first price as `session_open` automatically.

In `massive_client.py`, extract `snap.day.open` and pass it:
```python
self._cache.update(ticker=snap.ticker, price=price, timestamp=timestamp,
                   session_open=getattr(snap.day, 'open', None))
```

---

## 5. Risk Assessment

**Overall: HIGH**

- The `.env` API key leak is a hard blocker for any public-facing commit. Rotate immediately.
- The missing `session_open` field is a medium-severity architectural gap. It's the kind of thing that's trivial to add now but requires a multi-file retrofit after the portfolio/watchlist API routes are built. Fixing it in the model layer now is the right move.
- The Massive test failures and `stream.py` router scope issue are real bugs but localized — they won't block development, just need fixing before CI is set up.
- Everything else (annotations, dead code, conftest) is low-severity cleanup.

The market data subsystem itself is solid and production-quality. The issues listed above are the delta between "good code" and "ready to build on."
