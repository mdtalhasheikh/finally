# Market Simulator

Approach and code structure for simulating realistic stock prices in FinAlly when no `MASSIVE_API_KEY` is configured.

---

## Overview

The simulator uses **Geometric Brownian Motion (GBM)** to generate continuous, realistic-looking stock price paths. GBM is the mathematical model underlying Black-Scholes option pricing. Key properties:

- Prices are always positive (multiplicative process — no negative prices possible).
- Returns are normally distributed (lognormal price distribution).
- Variance scales with time (larger moves over longer periods).
- Per-ticker volatility and drift are configurable.

The simulator also adds:
- **Correlated moves** across tickers (tech stocks move together, etc.) via Cholesky decomposition.
- **Random shock events** — sudden 2–5% moves on a single ticker (~once per 50 seconds across 10 tickers) for visual drama.

---

## GBM Mathematics

At each time step, a price evolves as:

```
S(t+dt) = S(t) × exp( (μ - σ²/2) × dt  +  σ × √dt × Z )
```

| Variable | Meaning | Typical value |
|----------|---------|---------------|
| `S(t)` | Current price | varies |
| `μ` (mu) | Annualized drift (expected return) | 0.05 (5%) |
| `σ` (sigma) | Annualized volatility | 0.20–0.50 |
| `dt` | Time step as fraction of a trading year | ~8.48 × 10⁻⁸ |
| `Z` | Standard normal random variable N(0,1) | drawn each step |

**Choosing dt for 500 ms ticks**:

```
Trading year ≈ 252 days × 6.5 hours/day × 3600 s/hour = 5,896,800 s
dt = 0.5 s / 5,896,800 s ≈ 8.48e-8
```

This tiny `dt` produces sub-cent moves per tick that accumulate naturally over time into realistic intraday and multi-day ranges.

**Per-tick move magnitude**: With σ = 0.25 and dt = 8.48e-8, the typical per-tick price move is approximately:
```
σ × √dt × price ≈ 0.25 × 0.000291 × 190 ≈ $0.014 per tick for a $190 stock
```
That is about 0.007% per tick — imperceptible individually, but visible as a streaming trend.

---

## Correlated Moves

Real stocks do not move independently — tech stocks tend to move together. The simulator uses **Cholesky decomposition** of a correlation matrix to generate correlated random draws.

**Algorithm**:
1. Build an n×n correlation matrix `C` from the pairwise correlations of all active tickers.
2. Compute the lower triangular Cholesky factor `L = cholesky(C)`.
3. At each step, draw `n` independent standard normals `Z_independent`.
4. Compute correlated draws: `Z_correlated = L @ Z_independent`.
5. Use `Z_correlated[i]` for ticker `i` in the GBM formula.

**Correlation groups** (defined in `seed_prices.py`):

| Group | Tickers | Intra-group correlation |
|-------|---------|------------------------|
| Tech | AAPL, GOOGL, MSFT, AMZN, META, NVDA, NFLX | 0.6 |
| Finance | JPM, V | 0.5 |
| TSLA | standalone | 0.3 with everything |
| Cross-sector / unknown | any other pair | 0.3 |

These values are defined as named constants in `seed_prices.py`:
```python
INTRA_TECH_CORR    = 0.6
INTRA_FINANCE_CORR = 0.5
CROSS_GROUP_CORR   = 0.3
TSLA_CORR          = 0.3
```

TSLA is listed in the tech group but has its own correlation constant — it "does its own thing."

**Dynamic rebuilding**: When a ticker is added or removed, `_rebuild_cholesky()` is called to recompute the decomposition. This is O(n²) but n is always small (< 50 tickers in any realistic session).

---

## Random Shock Events

Each tick, every ticker has a small independent probability of a sudden shock:

```python
if random.random() < 0.001:  # 0.1% chance per tick per ticker
    shock_magnitude = random.uniform(0.02, 0.05)  # 2–5% move
    shock_sign = random.choice([-1, 1])
    price *= (1 + shock_magnitude * shock_sign)
```

With 10 tickers at 2 ticks/second: expected ~1 event every 50 seconds across the watchlist. This produces the dramatic flash moves seen on real terminals and makes the dashboard visually engaging.

Shock events are logged at DEBUG level with the ticker, magnitude, and direction.

---

## Seed Prices and Per-Ticker Parameters

**`seed_prices.py`** contains all static data for the simulator.

### Starting Prices

```python
SEED_PRICES: dict[str, float] = {
    "AAPL": 190.00,
    "GOOGL": 175.00,
    "MSFT": 420.00,
    "AMZN": 185.00,
    "TSLA": 250.00,
    "NVDA": 800.00,
    "META": 500.00,
    "JPM": 195.00,
    "V": 280.00,
    "NFLX": 600.00,
}
```

Tickers not in this dict (dynamically added) start at `random.uniform(50.0, 300.0)`.

### Per-Ticker GBM Parameters

```python
TICKER_PARAMS: dict[str, dict[str, float]] = {
    "AAPL":  {"sigma": 0.22, "mu": 0.05},
    "GOOGL": {"sigma": 0.25, "mu": 0.05},
    "MSFT":  {"sigma": 0.20, "mu": 0.05},
    "AMZN":  {"sigma": 0.28, "mu": 0.05},
    "TSLA":  {"sigma": 0.50, "mu": 0.03},  # High volatility
    "NVDA":  {"sigma": 0.40, "mu": 0.08},  # High vol + strong drift
    "META":  {"sigma": 0.30, "mu": 0.05},
    "JPM":   {"sigma": 0.18, "mu": 0.04},  # Low volatility (bank)
    "V":     {"sigma": 0.17, "mu": 0.04},  # Low volatility (payments)
    "NFLX":  {"sigma": 0.35, "mu": 0.05},
}

DEFAULT_PARAMS: dict[str, float] = {"sigma": 0.25, "mu": 0.05}
```

**Design rationale**: TSLA (σ=0.50) produces roughly realistic intraday ranges; JPM/V (σ≤0.18) are much calmer. NVDA (μ=0.08) has a stronger upward drift for the demo. The daily drift effect at 500 ms ticks is negligible per tick but visible over a full simulated session.

---

## Code Structure

### `GBMSimulator` (in `simulator.py`)

The pure mathematical engine. Has no asyncio, no dependencies on FastAPI or the cache — just math.

```python
class GBMSimulator:
    DEFAULT_DT = 0.5 / (252 * 6.5 * 3600)  # ~8.48e-8

    def __init__(
        self,
        tickers: list[str],
        dt: float = DEFAULT_DT,
        event_probability: float = 0.001,
    ) -> None: ...

    def step(self) -> dict[str, float]:
        """Advance all tickers by one dt. Returns {ticker: new_price}.
        Hot path — called every 500ms. Uses numpy for the random draws."""

    def add_ticker(self, ticker: str) -> None:
        """Add a ticker. Rebuilds the Cholesky matrix."""

    def remove_ticker(self, ticker: str) -> None:
        """Remove a ticker. Rebuilds the Cholesky matrix."""

    def get_price(self, ticker: str) -> float | None:
        """Current price for a ticker, or None if not tracked."""

    def get_tickers(self) -> list[str]:
        """Current list of tracked tickers (in order)."""

    # --- Private ---
    def _add_ticker_internal(self, ticker: str) -> None: ...  # batch init without rebuild
    def _rebuild_cholesky(self) -> None: ...                  # recomputes L = chol(C)
    @staticmethod
    def _pairwise_correlation(t1: str, t2: str) -> float: ... # returns rho from groups
```

**Internal state**:
- `_tickers: list[str]` — ordered list; index `i` maps to `z_correlated[i]`
- `_prices: dict[str, float]` — current price per ticker (mutable, updated by `step()`)
- `_params: dict[str, dict[str, float]]` — mu/sigma per ticker
- `_cholesky: np.ndarray | None` — lower triangular Cholesky factor; `None` when n ≤ 1

`step()` implementation:
```python
def step(self) -> dict[str, float]:
    n = len(self._tickers)
    if n == 0:
        return {}

    z_independent = np.random.standard_normal(n)
    z_correlated = self._cholesky @ z_independent if self._cholesky is not None else z_independent

    result = {}
    for i, ticker in enumerate(self._tickers):
        mu, sigma = self._params[ticker]["mu"], self._params[ticker]["sigma"]
        drift = (mu - 0.5 * sigma**2) * self._dt
        diffusion = sigma * math.sqrt(self._dt) * z_correlated[i]
        self._prices[ticker] *= math.exp(drift + diffusion)

        if random.random() < self._event_prob:
            shock = random.uniform(0.02, 0.05) * random.choice([-1, 1])
            self._prices[ticker] *= (1 + shock)

        result[ticker] = round(self._prices[ticker], 2)
    return result
```

### `SimulatorDataSource` (in `simulator.py`)

The `MarketDataSource` wrapper that drives `GBMSimulator` from an asyncio background task and writes to `PriceCache`.

```python
class SimulatorDataSource(MarketDataSource):
    def __init__(
        self,
        price_cache: PriceCache,
        update_interval: float = 0.5,
        event_probability: float = 0.001,
    ) -> None: ...

    async def start(self, tickers: list[str]) -> None:
        # 1. Create GBMSimulator with all initial tickers
        # 2. Seed PriceCache immediately (SSE has data before first step)
        # 3. Start _run_loop() as an asyncio.Task

    async def _run_loop(self) -> None:
        while True:
            prices = self._sim.step()
            for ticker, price in prices.items():
                self._cache.update(ticker=ticker, price=price)
            await asyncio.sleep(self._interval)
```

**Immediate seeding**: on `start()`, the source writes each ticker's initial price to the cache before the loop begins. This ensures the SSE endpoint and `GET /api/portfolio` return valid data on the very first request, with no blank/None prices.

**`add_ticker()` behavior**: immediately seeds the cache with the new ticker's starting price (from `GBMSimulator.get_price()` after `add_ticker()`) so the UI shows a price right away rather than waiting for the next loop tick.

---

## Behavior Notes

- **Prices never go negative** — `exp()` is always positive, so the multiplicative GBM formula guarantees S(t) > 0 for all t.
- **Resets on container restart** — since prices are in-memory, the simulator starts fresh at seed prices each time. `session_open` is captured on first update and held constant for the process lifetime.
- **Correlation matrix validity** — the Cholesky decomposition requires the matrix to be positive semi-definite. All correlation values are in [0, 1) and the diagonal is 1.0, so valid inputs are guaranteed for the sector-based grouping used here.
- **Performance** — `step()` is called every 500 ms. With numpy for random draws and pure Python for the per-ticker loop, this easily handles 50+ tickers without measurable CPU impact.
- **Unknown tickers** — in simulator mode, any ticker passing `^[A-Z]{1,8}$` validation is accepted. It receives `random.uniform(50.0, 300.0)` as its starting price and `DEFAULT_PARAMS` (σ=0.25, μ=0.05) for GBM parameters. No `unknown_ticker` error is ever raised in simulator mode — hallucinated symbols simply become tracked symbols with synthetic prices.
