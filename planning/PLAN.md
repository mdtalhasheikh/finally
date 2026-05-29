# FinAlly — AI Trading Workstation

## Project Specification

## 1. Vision

FinAlly (Finance Ally) is a visually stunning AI-powered trading workstation that streams live market data, lets users trade a simulated portfolio, and integrates an LLM chat assistant that can analyze positions and execute trades on the user's behalf. It looks and feels like a modern Bloomberg terminal with an AI copilot.

This is the capstone project for an agentic AI coding course. It is built entirely by Coding Agents demonstrating how orchestrated AI agents can produce a production-quality full-stack application. Agents interact through files in `planning/`.

## 2. User Experience

### First Launch

The user runs a single Docker command (or a provided start script). A browser opens to `http://localhost:8000`. No login, no signup. They immediately see:

- A watchlist of 10 default tickers with live-updating prices in a grid
- $10,000 in virtual cash
- A dark, data-rich trading terminal aesthetic
- An AI chat panel ready to assist

### What the User Can Do

- **Watch prices stream** — prices flash green (uptick) or red (downtick) with subtle CSS animations that fade
- **View sparkline mini-charts** — price action beside each ticker in the watchlist, accumulated on the frontend from the SSE stream since page load (sparklines fill in progressively)
- **Click a ticker** to see a larger detailed chart in the main chart area
- **Buy and sell shares** — market orders only, instant fill at current price, no fees, no confirmation dialog
- **Monitor their portfolio** — a heatmap (treemap) showing positions sized by weight and colored by P&L, plus a P&L chart tracking total portfolio value over time
- **View a positions table** — ticker, quantity, average cost, current price, unrealized P&L, % change
- **Chat with the AI assistant** — ask about their portfolio, get analysis, and have the AI execute trades and manage the watchlist through natural language
- **Manage the watchlist** — add/remove tickers manually or via the AI chat

### Visual Design

- **Dark theme**: backgrounds around `#0d1117` or `#1a1a2e`, muted gray borders, no pure black
- **Price flash animations**: brief green/red background highlight on price change, fading over ~500ms via CSS transitions
- **Connection status indicator**: a small colored dot (green = connected, yellow = reconnecting, red = disconnected) visible in the header
- **Professional, data-dense layout**: inspired by Bloomberg/trading terminals — every pixel earns its place
- **Responsive but desktop-first**: optimized for wide screens, functional on tablet

### Color Scheme

- Accent Yellow: `#ecad0a`
- Blue Primary: `#209dd7`
- Purple Secondary: `#753991` (submit buttons)

## 3. Architecture Overview

### Single Container, Single Port

```
┌─────────────────────────────────────────────────┐
│  Docker Container (port 8000)                   │
│                                                 │
│  FastAPI (Python/uv)                            │
│  ├── /api/*          REST endpoints             │
│  ├── /api/stream/*   SSE streaming              │
│  └── /*              Static file serving         │
│                      (Next.js export)            │
│                                                 │
│  SQLite database (volume-mounted)               │
│  Background task: market data polling/sim        │
└─────────────────────────────────────────────────┘
```

- **Frontend**: Next.js with TypeScript, built as a static export (`output: 'export'`), served by FastAPI as static files
- **Backend**: FastAPI (Python), managed as a `uv` project
- **Database**: SQLite, single file at `db/finally.db`, volume-mounted for persistence
- **Real-time data**: Server-Sent Events (SSE) — simpler than WebSockets, one-way server→client push, works everywhere
- **AI integration**: LiteLLM → OpenRouter (Cerebras for fast inference), with structured outputs for trade execution
- **Market data**: Environment-variable driven — simulator by default, real data via Massive API if key provided

### Why These Choices

| Decision                | Rationale                                                                                     |
| ----------------------- | --------------------------------------------------------------------------------------------- |
| SSE over WebSockets     | One-way push is all we need; simpler, no bidirectional complexity, universal browser support  |
| Static Next.js export   | Single origin, no CORS issues, one port, one container, simple deployment                     |
| SQLite over Postgres    | No auth = no multi-user = no need for a database server; self-contained, zero config          |
| Single Docker container | Students run one command; no docker-compose for production, no service orchestration          |
| uv for Python           | Fast, modern Python project management; reproducible lockfile; what students should learn     |
| Market orders only      | Eliminates order book, limit order logic, partial fills — dramatically simpler portfolio math |

---

## 4. Directory Structure

```
finally/
├── frontend/                 # Next.js TypeScript project (static export)
├── backend/                  # FastAPI uv project (Python)
│   └── database/             # Schema definitions, seed data, init logic
├── planning/                 # Project-wide documentation for agents
│   ├── PLAN.md               # This document
│   └── ...                   # Additional agent reference docs
├── scripts/
│   ├── start_mac.sh          # Launch Docker container (macOS/Linux)
│   ├── stop_mac.sh           # Stop Docker container (macOS/Linux)
│   ├── start_windows.ps1     # Launch Docker container (Windows PowerShell)
│   └── stop_windows.ps1      # Stop Docker container (Windows PowerShell)
├── test/                     # Playwright E2E tests + docker-compose.test.yml
├── db/                       # Volume mount target (SQLite file lives here at runtime)
│   └── .gitkeep              # Directory exists in repo; finally.db is gitignored
├── Dockerfile                # Multi-stage build (Node → Python)
├── docker-compose.yml        # Optional convenience wrapper
├── .env                      # Environment variables (gitignored, .env.example committed)
└── .gitignore
```

### Key Boundaries

- **`frontend/`** is a self-contained Next.js project. It knows nothing about Python. It talks to the backend via `/api/*` endpoints and `/api/stream/*` SSE endpoints. Internal structure is up to the Frontend Engineer agent.
- **`backend/`** is a self-contained uv project with its own `pyproject.toml`. It owns all server logic including database initialization, schema, seed data, API routes, SSE streaming, market data, and LLM integration. Internal structure is up to the Backend/Market Data agents.
- **`backend/database/`** contains schema SQL definitions and seed logic. The backend initializes the database during FastAPI's `lifespan` startup — before any background task runs — creating tables and seeding default data if the SQLite file doesn't exist or is empty. (Renamed from `backend/db/` to avoid colliding with the top-level `db/` data directory.)
- **`db/`** at the top level is the runtime volume mount point. The SQLite file (`db/finally.db`) is created here by the backend and persists across container restarts via Docker volume.
- **`planning/`** contains project-wide documentation, including this plan. All agents reference files here as the shared contract.
- **`test/`** contains Playwright E2E tests and supporting infrastructure (e.g., `docker-compose.test.yml`). Unit tests live within `frontend/` and `backend/` respectively, following each framework's conventions.
- **`scripts/`** contains start/stop scripts that wrap Docker commands.

---

## 5. Environment Variables

```bash
# Required: OpenRouter API key for LLM chat functionality
OPENROUTER_API_KEY=your-openrouter-api-key-here

# Optional: Massive (Polygon.io) API key for real market data
# If not set, the built-in market simulator is used (recommended for most users)
MASSIVE_API_KEY=

# Optional: Polling interval for Massive API in seconds. Default 15 (safe for the free tier's 5 calls/min).
MASSIVE_POLL_INTERVAL_SECONDS=15

# Optional: Fallback LLM model used when the primary model 5xxs or fails to produce valid structured output
LLM_FALLBACK_MODEL=openrouter/google/gemini-2.5-flash

# Optional: Set to "true" for deterministic mock LLM responses (testing)
LLM_MOCK=false
```

### Behavior

- If `MASSIVE_API_KEY` is set and non-empty → backend uses Massive REST API for market data
- If `MASSIVE_API_KEY` is absent or empty → backend uses the built-in market simulator
- If `LLM_MOCK=true` → backend returns deterministic mock LLM responses (for E2E tests)
- The backend reads `.env` from the project root (mounted into the container or read via docker `--env-file`)
- Environment-variable changes are picked up on container start only — toggling `MASSIVE_API_KEY` (simulator ↔ real data) or rotating `OPENROUTER_API_KEY` requires a container restart.
- On startup, the backend asserts that `OPENROUTER_API_KEY` is set unless `LLM_MOCK=true`. A missing key in non-mock mode is a fast boot failure with a clear error pointing at `.env`.

### Backend Configuration File

Tunables that don't belong in `.env` (because they're not secrets and don't change between deployments) live in `backend/app/config.py` as a single typed dataclass. Examples:

| Setting                               | Default                          | Notes                                                                                     |
| ------------------------------------- | -------------------------------- | ----------------------------------------------------------------------------------------- |
| `LLM_MAX_HISTORY_MESSAGES`            | 20                               | Recent chat messages sent back to the LLM per request and returned by `/api/chat/history` |
| `LLM_PRIMARY_MODEL`                   | `openrouter/openai/gpt-oss-120b` | Override only if running a different course-provided model                                |
| `PORTFOLIO_SNAPSHOT_INTERVAL_SECONDS` | 30                               | Cadence of the background snapshot writer                                                 |
| `SIMULATOR_TICK_INTERVAL_MS`          | 500                              | Simulator update rate (Massive mode uses `MASSIVE_POLL_INTERVAL_SECONDS` instead)         |
| `STARTING_CASH`                       | 10000.0                          | Seed cash balance for the default user                                                    |

The rule of thumb: secret or infra-shaped → env var; code-tunable knob → `config.py`.

---

## 6. Market Data

### Two Implementations, One Interface

Both the simulator and the Massive client implement the same abstract interface. The backend selects which to use based on the environment variable. All downstream code (SSE streaming, price cache, frontend) is agnostic to the source.

### Simulator (Default)

- Generates prices using geometric Brownian motion (GBM) with configurable drift and volatility per ticker
- Updates at ~500ms intervals
- Correlated moves across tickers (e.g., tech stocks move together)
- Occasional random "events" — sudden 2-5% moves on a ticker for drama
- Starts from realistic seed prices (e.g., AAPL ~$190, GOOGL ~$175, etc.)
- Runs as an in-process background task — no external dependencies

### Massive API (Optional)

- The underlying market data provider is **Polygon.io**, accessed via the `massive` Python package — "Massive" is just the SDK name; if you read the docs, look for Polygon.
- REST API polling (not WebSocket) — simpler, works on all tiers
- Polls for the union of all watched tickers on the interval set by `MASSIVE_POLL_INTERVAL_SECONDS` (default 15 s, safe for the free tier's 5 calls/min limit; lower it for paid tiers)
- Parses REST response into the same format as the simulator

### Shared Price Cache

- A single background task (simulator or Massive poller) starts during FastAPI's `lifespan` startup and runs continuously for the lifetime of the process, regardless of whether any SSE client is connected. Trade execution, portfolio valuation, and the snapshot writer all assume a fresh cache.
- On app launch the cache is pre-populated for every tracked ticker before the first SSE event is emitted, so the UI shows real prices on first paint rather than blanks.
- The cache holds the latest price, previous price, timestamp, and `session_open` (the day-open reference; see below) for each ticker.
- SSE streams read from this cache and push updates to connected clients.
- The cache is keyed by ticker, not user. The single-user app uses one watchlist, but the cache shape is already correct for future multi-user expansion: multiple users' watchlists will union into a single set of tracked tickers that share this cache.

### Tracked Ticker Set

The set of tickers the market source is actively pricing is **`watchlist ∪ {tickers with non-zero open positions}`**, not just the watchlist. Consequences:

- Removing a ticker from the watchlist while an open position still exists does **not** stop pricing — the cache and SSE stream continue to carry it so the positions table stays live.
- The market source only stops tracking a ticker when it leaves both sets (removed from the watchlist *and* the position is fully closed).
- On lifespan startup, the backend computes this union from the DB and asks the market source to track all of it before opening the SSE endpoint.

### Daily Change Reference Price

`session_open` is an explicit field on the `PriceUpdate` model and the `PriceCache` — this is a small additive extension to the already-built market-data subsystem (see `MARKET_DATA_SUMMARY.md`). It is:

- **Simulator mode**: captured the first time a ticker enters the cache after process start and held constant for the lifetime of the process.
- **Massive mode**: mapped from Polygon's daily-open field on each poll. If Polygon does not return a daily-open value for a ticker (e.g. before market open, or a newly added symbol), the Massive client falls back to the simulator-style "capture first observed price as `session_open` and hold" behaviour.

Daily change % is `(current - session_open) / session_open`. It is a session-relative metric for the demo (resets on container restart in simulator mode; resets at the exchange's daily-open boundary in Massive mode), not an exchange-calendar one.

### SSE Streaming

- Endpoint: `GET /api/stream/prices`
- Long-lived SSE connection; client uses native `EventSource` API
- Server pushes price updates for all actively tracked tickers at a regular cadence (~500ms) — the union of the user's watchlist and any tickers with open positions (not just the watchlist; see Section 6, "Tracked Ticker Set")
- Each SSE event contains ticker, price, previous price, timestamp, and change direction
- Client handles reconnection automatically (EventSource has built-in retry)

---

## 7. Database

### SQLite with Startup Initialization

The backend initializes the SQLite database during FastAPI's `lifespan` startup, before any background task (market-data poller, portfolio-snapshot writer) begins. Schema SQL and seed data live in `backend/database/`. If the file doesn't exist or tables are missing, the schema is created and default data is seeded. This means:

- No separate migration step
- No manual database setup
- Fresh Docker volumes start with a clean, seeded database automatically
- Background tasks never race the schema — they only start after init succeeds

### Money and Precision

All monetary fields (`cash_balance`, `avg_cost`, `price`, `total_value`) and `quantity` are stored as SQLite `REAL` (IEEE-754 double). Repeated buy/sell cycles can drift by sub-cent amounts. For this demo we accept that and apply two rules:

- Values shown to the UI are rounded to 2 decimals for currency, 4 for `avg_cost`, and 6 for fractional `quantity`.
- Tests use `pytest.approx` (or equivalent) for any equality assertion involving money — never `==`.

If a future iteration adds real (non-fake) money or any settlement logic, switch cash/cost columns to integer minor units (cents) before that work begins.

### Retention

For the demo we accept unbounded growth of `portfolio_snapshots` (~2,880 rows/day at the default 30 s cadence) and `chat_messages`. A single-user demo session does not generate enough rows to matter. A periodic cleanup task can be bolted on later; it is out of scope for the initial build.

### Schema

All tables include a `user_id` column defaulting to `"default"`. This is hardcoded for now (single-user) but enables future multi-user support without schema migration.

**users_profile** — User state (cash balance)

- `id` TEXT PRIMARY KEY (default: `"default"`)
- `cash_balance` REAL (default: `10000.0`)
- `created_at` TEXT (ISO timestamp)

**watchlist** — Tickers the user is watching

- `id` TEXT PRIMARY KEY (UUID)
- `user_id` TEXT (default: `"default"`)
- `ticker` TEXT
- `added_at` TEXT (ISO timestamp)
- UNIQUE constraint on `(user_id, ticker)`

**positions** — Current holdings (one row per ticker per user)

- `id` TEXT PRIMARY KEY (UUID)
- `user_id` TEXT (default: `"default"`)
- `ticker` TEXT
- `quantity` REAL (fractional shares supported)
- `avg_cost` REAL
- `updated_at` TEXT (ISO timestamp)
- UNIQUE constraint on `(user_id, ticker)`

**trades** — Trade history (append-only log)

- `id` TEXT PRIMARY KEY (UUID)
- `user_id` TEXT (default: `"default"`)
- `ticker` TEXT
- `side` TEXT (`"buy"` or `"sell"`)
- `quantity` REAL (fractional shares supported)
- `price` REAL (execution price)
- `executed_at` TEXT (ISO timestamp)
- `idempotency_key` TEXT NULLABLE — client-supplied dedupe token; see "Trade idempotency" in Section 8
- `cash_balance_after` REAL — user cash balance immediately after this trade
- `position_qty_after` REAL — quantity held in the affected ticker immediately after this trade (0 if fully sold)
- `position_avg_cost_after` REAL NULLABLE — avg cost of the position immediately after this trade (NULL when `position_qty_after` is 0)
- UNIQUE constraint on `(user_id, idempotency_key)` (composite to keep keys scoped per-user once the multi-user iteration arrives; SQLite treats NULL as distinct in UNIQUE, so rows without a key are unaffected)

**portfolio_snapshots** — Portfolio value over time (for P&L chart). Recorded:

- Once during FastAPI lifespan startup, after the price cache is pre-populated, so the P&L chart has at least one data point on first paint and never starts empty.
- Every `PORTFOLIO_SNAPSHOT_INTERVAL_SECONDS` (default 30 s) by a background task.
- Immediately after each trade execution.

Columns:

- `id` TEXT PRIMARY KEY (UUID)
- `user_id` TEXT (default: `"default"`)
- `total_value` REAL
- `recorded_at` TEXT (ISO timestamp)

**chat_messages** — Conversation history with LLM

- `id` TEXT PRIMARY KEY (UUID)
- `user_id` TEXT (default: `"default"`)
- `role` TEXT (`"user"` or `"assistant"`)
- `content` TEXT
- `actions` TEXT (JSON — trades executed, watchlist changes made; null for user messages)
- `created_at` TEXT (ISO timestamp)

### Default Seed Data

- One user profile: `id="default"`, `cash_balance=10000.0`
- Ten watchlist entries: AAPL, GOOGL, MSFT, AMZN, TSLA, NVDA, META, JPM, V, NFLX

---

## 8. API Endpoints

### Market Data

| Method | Path                 | Description                      |
| ------ | -------------------- | -------------------------------- |
| GET    | `/api/stream/prices` | SSE stream of live price updates |

### Portfolio

| Method | Path                     | Description                                                                  |
| ------ | ------------------------ | ---------------------------------------------------------------------------- |
| GET    | `/api/portfolio`         | Current positions, cash balance, total value, unrealized P&L                 |
| POST   | `/api/portfolio/trade`   | Execute a trade: `{ticker, quantity, side, idempotency_key?}`                |
| GET    | `/api/portfolio/history` | Portfolio value snapshots over time (for P&L chart)                          |

**`GET /api/portfolio` response shape** — each position row includes `current_price`, `session_open` (the session reference price; see Section 6), `daily_change_pct`, `unrealized_pnl`, and `unrealized_pnl_pct`, alongside `quantity` and `avg_cost`. Top-level fields: `cash_balance`, `total_value`, `total_unrealized_pnl`.

**`POST /api/portfolio/trade` response shape**:

```json
{
  "trade": {
    "id": "uuid",
    "ticker": "AAPL",
    "side": "buy",
    "quantity": 10,
    "price": 191.23,
    "executed_at": "2026-05-26T14:03:21Z"
  },
  "cash_balance": 8087.7,
  "position": { "ticker": "AAPL", "quantity": 10, "avg_cost": 191.23 }
}
```

The frontend can apply this directly without a follow-up `GET /api/portfolio` for the affected ticker. It should still refetch the full portfolio shortly after if it needs aggregate fields (heatmap weights, total P&L), but the optimistic update is correct.

**Quantity precision** — `quantity` must be a positive number (floats accepted; no minimum increment). The demo supports fractional shares. The API layer rejects `quantity <= 0` with a 422.

**`GET /api/portfolio/history` query params** — accepts an optional `?limit=N` integer (default 500, max 2000). At the default 30 s cadence, 500 rows covers ~4 hours of history — enough for the P&L chart without fetching thousands of rows on a long-running demo session. Results are ordered oldest-first.

**Error response shape** — all 4xx/5xx responses from `/api/*` use a consistent JSON body:

```json
{ "error": { "code": "string", "message": "string", "details": {} } }
```

`code` is a machine-readable string (e.g., `"insufficient_cash"`, `"unknown_ticker"`, `"ticker_already_exists"`, `"ticker_not_found"`, `"invalid_symbol"`). `details` is optional and may carry extra context (e.g., the attempted ticker). The frontend and chat action renderer key off `code` for specific error messaging.

**Trade idempotency** — `POST /api/portfolio/trade` accepts an optional `idempotency_key` (string, typically a client-side UUID). The server stores it on the `trades` row with a `UNIQUE (user_id, idempotency_key)` constraint.

- **New key (or no key)** → execute the trade and return 201 with the response shape above.
- **Repeat key matching an existing row** → return 200 with the **original** trade response, reconstructed from the snapshot columns on the `trades` row: `cash_balance` in the response is `trade.cash_balance_after`, and `position` is `{ticker, quantity: position_qty_after, avg_cost: position_avg_cost_after}` (or `null` when `position_qty_after` is 0). This means a retry returns the *original* response shape even if subsequent trades have moved cash or position state — the idempotency contract holds across later activity.
- The frontend should refetch `/api/portfolio` after applying a replayed response if it needs aggregate fields (heatmap weights, total P&L); the snapshot values are correct as-of-original-execution and may not reflect current aggregate state.
- **Frontend manual trades**: generate a fresh UUID per Buy/Sell click. The button stays disabled during the in-flight request as a UI guard, but the key handles the case where a network blip causes a retry.
- **LLM-driven trades**: the chat handler generates one key per trade extracted from the LLM response (e.g., `f"{chat_message_id}:{trade_index}"`). This means retrying the same chat turn does not produce duplicate trades.
- **Concurrency**: keys without an existing row are not pre-reserved — concurrent requests with the same key may both succeed if neither has committed yet. For a single-user demo this race is acceptable; if it becomes a real concern, wrap the insert in `BEGIN IMMEDIATE` + `ON CONFLICT DO NOTHING` and return the existing row from the conflict path.

### Watchlist

| Method | Path                      | Description                                  |
| ------ | ------------------------- | -------------------------------------------- |
| GET    | `/api/watchlist`          | Current watchlist tickers with latest prices |
| POST   | `/api/watchlist`          | Add a ticker: `{ticker}`                     |
| DELETE | `/api/watchlist/{ticker}` | Remove a ticker                              |

**Watchlist semantics**:

- Tickers are uppercased and trimmed server-side before lookup/insert. Canonical form is `^[A-Z]{1,8}$`; the frontend may send lowercase.
- `POST /api/watchlist` returns 201 on success, 409 if the ticker is already on the watchlist, 422 if the symbol fails the regex above. **In Massive mode**, the handler additionally probes Polygon before inserting (same 5 s timeout used for LLM implicit adds). If Polygon returns no data for the symbol, the insert is aborted and the endpoint returns 422 with `code: "unknown_ticker"`. **In simulator mode**, any syntactically valid symbol is accepted without further validation.
- `DELETE /api/watchlist/{ticker}` returns 204 on success, 404 if the ticker isn't on the watchlist. Removing the watchlist row does **not** stop the market source from tracking the ticker when an open position still exists in it (see Section 6, "Tracked Ticker Set") — the position stays in the positions table and continues to be priced live from the cache.
- `GET /api/watchlist` returns rows with the same daily-change fields as the portfolio response, so the frontend has a complete picture on first paint without computing anything from SSE: `{ticker, current_price, session_open, daily_change_pct, added_at}`. The SSE stream then updates `current_price` tick-by-tick; `daily_change_pct` is re-derived client-side against the unchanged `session_open`.

### Chat

| Method | Path                | Description                                                                                                                  |
| ------ | ------------------- | ---------------------------------------------------------------------------------------------------------------------------- |
| POST   | `/api/chat`         | Send a message, receive complete JSON response (message + executed actions)                                                  |
| GET    | `/api/chat/history` | Return the most recent N messages (N = `LLM_MAX_HISTORY_MESSAGES`, default 20) for replay on page load, oldest-first ordered |

### System

| Method | Path          | Description                          |
| ------ | ------------- | ------------------------------------ |
| GET    | `/api/health` | Health check (for Docker/deployment) |

---

## 9. LLM Integration

When writing code to make calls to LLMs, use cerebras-inference skill to use LiteLLM via OpenRouter to the `openrouter/openai/gpt-oss-120b` model with Cerebras as the inference provider. Structured Outputs should be used to interpret the results.

There is an OPENROUTER_API_KEY in the .env file in the project root.

### Boot-time Configuration

On FastAPI lifespan startup the backend asserts that `OPENROUTER_API_KEY` is set unless `LLM_MOCK=true`. A missing key in non-mock mode is a fast boot failure with a clear error message pointing the user at `.env`. There is no lazy 503 path; the app refuses to start so the misconfiguration is obvious.

### Fallback Model

If the primary model (`LLM_PRIMARY_MODEL` in `backend/app/config.py`, default `openrouter/openai/gpt-oss-120b`) returns a 5xx, refuses structured output, or returns JSON that fails pydantic validation after one retry, the backend retries the same prompt once against `LLM_FALLBACK_MODEL` (env var, default `openrouter/google/gemini-2.5-flash` — a fast model that reliably supports JSON-mode). If the fallback also fails, the chat endpoint returns 502 and the chat panel shows a user-friendly error bubble. All failures are logged with the model identifier and the validation reason.

### How It Works

When the user sends a chat message, the backend:

1. Loads the user's current portfolio context (cash, positions with P&L, watchlist with live prices, total portfolio value)
2. Loads the last `LLM_MAX_HISTORY_MESSAGES` messages (default 20, set in `backend/app/config.py`) from the `chat_messages` table
3. Constructs a prompt with a system message, portfolio context, conversation history, and the user's new message
4. Calls the LLM via LiteLLM → OpenRouter, requesting structured output, using the cerebras-inference skill
5. Parses and pydantic-validates the structured JSON response; on validation failure, retries once with the same model, then falls back to `LLM_FALLBACK_MODEL`
6. Auto-executes any trades or watchlist changes specified in the response (see "Unknown Tickers" below)
7. Stores the message and executed actions in `chat_messages`
8. Returns the complete JSON response to the frontend (no token-by-token streaming — Cerebras inference is fast enough that a loading indicator is sufficient)

### Structured Output Schema

The LLM is instructed to respond with JSON matching this schema:

```json
{
  "message": "Your conversational response to the user",
  "trades": [{ "ticker": "AAPL", "side": "buy", "quantity": 10 }],
  "watchlist_changes": [{ "ticker": "PYPL", "action": "add" }]
}
```

- `message` (required): The conversational text shown to the user
- `trades` (optional): Array of trades to auto-execute. Each trade goes through the same validation as manual trades (sufficient cash for buys, sufficient shares for sells)
- `watchlist_changes` (optional): Array of watchlist modifications

### Auto-Execution

Trades specified by the LLM execute automatically — no confirmation dialog. This is a deliberate design choice:

- It's a simulated environment with fake money, so the stakes are zero
- It creates an impressive, fluid demo experience
- It demonstrates agentic AI capabilities — the core theme of the course

If a trade fails validation (e.g., insufficient cash, insufficient shares), the error is appended to the chat response so the LLM can inform the user on the next turn. The failed trade is **not** persisted in `trades`.

### Unknown / Unwatched Tickers

If the LLM proposes a trade for a ticker that is not on the watchlist, the backend automatically adds it to the watchlist (and asks the market source to start tracking it) before executing the trade. The implicit add appears in `watchlist_changes` of the response so the UI can render it.

Resolution behaviour differs by data source:

- **Simulator mode**: the simulator accepts any syntactically valid ticker (`^[A-Z]{1,8}$` after normalisation) and assigns a random starting price plus default GBM parameters when the symbol is not in its seed list. This matches the existing market-data subsystem and is intentional — for a demo, an LLM-hallucinated symbol simply becomes a tracked symbol with a synthetic price. **No `unknown_ticker` error is raised in simulator mode.**
- **Massive mode**: the Massive client probes Polygon for the ticker on first add (configurable timeout, default 5 s). If Polygon returns no data — a hallucinated symbol like `GOOOG`, or a delisted one — the implicit watchlist add is rolled back and the trade is rejected with an `unknown_ticker` error appended to the chat response so the LLM can apologise on the next turn.

Syntactically invalid symbols (failing `^[A-Z]{1,8}$` after normalisation) are rejected by the API layer in both modes, before either data source sees them.

### Chat Transaction Boundaries

A single `POST /api/chat` call writes to multiple tables: `chat_messages` (user row + assistant row), `trades` (any executed orders), `watchlist` (any add/remove), `positions`, `users_profile.cash_balance`, and `portfolio_snapshots` (post-trade snapshot).

**Phase 1 — pre-transaction market-source validation (Massive mode only)**. Before any DB write, the handler collects all off-watchlist tickers referenced in `trades` or `watchlist_changes`. For each, it probes Polygon (5 s timeout). Any ticker that Polygon does not recognise is removed from the action list and tagged with an `unknown_ticker` failure — no DB transaction has started yet, so no rollback is needed. Simulator mode skips this phase entirely (all syntactically valid symbols are accepted).

**Phase 2 — DB transaction**. After validation, the handler executes:

1. Begin transaction.
2. Insert the user message row.
3. Execute every validated action in order. A validation failure on a single trade (insufficient cash, insufficient shares) records the failure on the assistant message's `actions` JSON but does **not** abort sibling trades or the transaction — partial success is allowed.
4. Insert the assistant message row, with the `actions` JSON describing what executed and what failed (including any `unknown_ticker` rejections from Phase 1).
5. Commit.

**Phase 3 — market-source activation (after commit)**. For newly validated tickers, the handler tells the market source to start tracking them (updating the in-memory set, beginning to poll/simulate). These calls happen after commit so the DB is never left dirty if activation fails. A failure here is logged but does not affect the already-committed trade or assistant message.

If the DB transaction itself rolls back (rare — disk full, schema violation), the API returns 500 and the chat panel shows an error bubble. Neither message is persisted; the next chat turn starts from the prior state.

### System Prompt Guidance

The LLM should be prompted as "FinAlly, an AI trading assistant" with instructions to:

- Analyze portfolio composition, risk concentration, and P&L
- Suggest trades with reasoning
- Execute trades when the user asks or agrees
- Modify the watchlist **only on explicit user request** (e.g., "add NFLX to my watchlist"). Implicit adds happen automatically when the LLM trades an off-watchlist ticker (see above) — that is the one allowed exception. Unsolicited watchlist edits in conversational responses are discouraged because they surprise the user.
- Be concise and data-driven in responses
- Always respond with valid structured JSON

### LLM Mock Mode

When `LLM_MOCK=true`, the backend skips OpenRouter entirely and returns one of two static fixtures from `backend/app/llm/mock.py`, dispatched on a simple case-insensitive substring check of the user's message. The dispatch keeps the mock deterministic while letting smoke chats run without mutating portfolio state.

- **Default fixture** (any input not matching the trade-trigger) — a plain conversational reply, no actions, so `"hello"` E2E chats don't move cash or positions:

  ```json
  {
    "message": "Mock response: I'm here to help. Tell me what you'd like to do.",
    "trades": [],
    "watchlist_changes": []
  }
  ```

- **Trade-trigger fixture** (user message contains the substring `mock-trade`, case-insensitive) — a deterministic response that executes one buy of AAPL:

  ```json
  {
    "message": "Mock response: buying 1 share of AAPL.",
    "trades": [{ "ticker": "AAPL", "side": "buy", "quantity": 1 }],
    "watchlist_changes": []
  }
  ```

This enables:

- Fast, free, reproducible E2E tests (Playwright asserts against one of two fixed shapes)
- A no-side-effect default so smoke chats don't pollute the portfolio
- A deterministic switch for the trade-execution path

Add new fixtures (or switch on a header like `X-Mock-Scenario`) only if a test scenario demands it — keep mock mode simple by default.

---

## 10. Frontend Design

### Layout

The frontend is a single-page application with a dense, terminal-inspired layout. The specific component architecture and layout system is up to the Frontend Engineer, but the UI should include these elements:

- **Watchlist panel** — grid/table of watched tickers with: ticker symbol, current price (flashing green/red on change), daily change %, and a sparkline mini-chart (accumulated from SSE since page load)
- **Main chart area** — larger chart for the currently selected ticker, with at minimum price over time. Clicking a ticker in the watchlist selects it here.
- **Portfolio heatmap** — treemap visualization where each rectangle is a position, sized by portfolio weight, colored by P&L (green = profit, red = loss)
- **P&L chart** — line chart showing total portfolio value over time, using data from `portfolio_snapshots`
- **Positions table** — tabular view of all positions: ticker, quantity, avg cost, current price, unrealized P&L, % change
- **Trade bar** — simple input area: ticker field, quantity field, buy button, sell button. Market orders, instant fill.
- **AI chat panel** — docked/collapsible sidebar. Message input, scrolling conversation history, loading indicator while waiting for LLM response. Trade executions and watchlist changes shown inline as confirmations.
- **Header** — portfolio total value (updating live), connection status indicator, cash balance

### Technical Notes

- Use `EventSource` for SSE connection to `/api/stream/prices`
- **Main chart**: TradingView's `lightweight-charts` (canvas, fast on time-series, small bundle). The frontend agent should not relitigate this choice.
- **Sparklines**: pure SVG/CSS in a tiny per-ticker component. Recharts/lightweight-charts is overkill at this scale and hurts the first-paint budget.
- Sparklines accumulate from the SSE stream since page load. A hard refresh starts the sparkline empty and it fills back in over the next ~30 s. **This is an intentional limitation** — do not build a server-side history endpoint to back-fill it. The empty-then-fill effect is acceptable for the demo.
- The currently selected ticker (for the main chart) is held in the URL hash (`#ticker=AAPL`). Page refresh and browser back/forward preserve the view without any backend involvement and without `localStorage`. Because this is a static export, `window.location.hash` must be read **client-side after mount** (inside `useEffect`) — never during render or static generation. The default ticker when the hash is absent or unparseable is `AAPL`.
- Price flash effect: on receiving a new price, briefly apply a CSS class with background color transition, then remove it
- Connection status is derived from `EventSource.readyState` and the `open`/`error` events (green = OPEN, yellow = CONNECTING after an error, red = CLOSED beyond reconnect attempts).
- All API calls go to the same origin (`/api/*`) — no CORS configuration needed
- Tailwind CSS for styling with a custom dark theme

---

## 11. Docker & Deployment

### Multi-Stage Dockerfile

```
Stage 1: Node 20 slim
  - Copy frontend/
  - npm ci && npm run build (npm ci, not npm install — reproducible from package-lock.json)

Stage 2: Python 3.12 slim
  - Install uv
  - Copy backend/
  - uv sync (install Python dependencies from lockfile)
  - Copy frontend build output into a static/ directory
  - Expose port 8000
  - CMD: uvicorn serving FastAPI app
```

FastAPI serves the static frontend files and all API routes on port 8000.

### Docker Volume

The SQLite database persists via a **bind mount** of the project's `db/` directory:

```bash
docker run -v "$(pwd)/db:/app/db" -p 8000:8000 --env-file .env finally
```

A bind mount (rather than a named Docker volume) was chosen so the user can open `db/finally.db` locally with any SQLite browser between runs without `docker cp`. The `docker-compose.yml` uses the same bind mount for consistency. The start scripts create the host `db/` directory if it doesn't already exist.

### SSE Behind Reverse Proxies

`localhost` works out of the box. If anyone deploys this behind nginx, Caddy, CloudFront, or App Runner, **response buffering must be disabled on `/api/stream/*`** or SSE messages will be batched at the proxy and the live-tick effect dies. Example for nginx:

```nginx
location /api/stream/ {
  proxy_buffering off;
  proxy_cache off;
  proxy_read_timeout 24h;
}
```

### Start/Stop Scripts

**`scripts/start_mac.sh`** (macOS/Linux):

- Builds the Docker image if not already built (or if `--build` flag passed)
- Runs the container with the volume mount, port mapping, and `.env` file
- Prints the URL to access the app
- Optionally opens the browser

**`scripts/stop_mac.sh`** (macOS/Linux):

- Stops and removes the running container
- Does NOT remove the volume (data persists)

**`scripts/start_windows.ps1`** / **`scripts/stop_windows.ps1`**: PowerShell equivalents for Windows.

All scripts should be idempotent — safe to run multiple times.

### Optional Cloud Deployment

The container is designed to deploy to AWS App Runner, Render, or any container platform. A Terraform configuration for App Runner may be provided in a `deploy/` directory as a stretch goal, but is not part of the core build.

---

## 12. Testing Strategy

### Unit Tests (within `frontend/` and `backend/`)

**Backend (pytest)**:

- Coverage target: **≥80%** for new subsystems (matches the 84% bar set by the market-data subsystem).
- Use `pytest.approx` for any equality assertion involving money or prices — never `==` against floats.
- Market data: simulator generates valid prices, GBM math is correct, Massive API response parsing works, both implementations conform to the abstract interface
- Portfolio: trade execution logic, P&L calculations, edge cases (selling more than owned, buying with insufficient cash, selling at a loss, fractional quantities), idempotency replay (repeat key returns the original snapshot response even after a subsequent successful trade has moved cash/position state), composite `(user_id, idempotency_key)` constraint allows the same key under different users
- LLM: structured output parsing handles all valid schemas, graceful handling of malformed responses, the fallback-model retry path, boot-time key-check failure, trade validation within chat flow, simulator-mode auto-add of unknown tickers (no rejection), Massive-mode `unknown_ticker` rejection with implicit-add rollback, chat transaction atomicity (partial trade failure does not roll back sibling trades or the assistant message; total DB failure rolls back both user and assistant messages)
- Market data: `session_open` is set on first ticker insert in simulator mode and held; `PriceCache` exposes it on `PriceUpdate`; tracked-ticker set is `watchlist ∪ open positions` (removing a watchlist row while a position is open keeps pricing live)
- Snapshots: an initial `portfolio_snapshots` row exists immediately after lifespan startup, before the 30-second background writer fires
- API routes: correct status codes, response shapes, error handling, watchlist 201/409/404 semantics, `GET /api/watchlist` returns `session_open`/`daily_change_pct`

**Frontend (React Testing Library or similar)**:

- Component rendering with mock data
- Price flash animation triggers correctly on price changes
- Watchlist CRUD operations
- Portfolio display calculations
- Chat message rendering and loading state

### E2E Tests (in `test/`)

**Infrastructure**: A separate `docker-compose.test.yml` in `test/` that spins up the app container plus a Playwright container. This keeps browser dependencies out of the production image.

**Environment**: Tests run with `LLM_MOCK=true` by default for speed and determinism.

**Key Scenarios** (this list is the must-pass minimum; additional scenarios welcome — no formal coverage gate on E2E, scenario-driven only):

- Fresh start: default watchlist appears, $10k balance shown, prices are streaming
- Add and remove a ticker from the watchlist
- Buy shares: cash decreases, position appears, portfolio updates
- Sell shares: cash increases, position updates or disappears
- Portfolio visualization: heatmap renders with correct colors, P&L chart has data points
- AI chat (mocked): send a message, receive a response, trade execution appears inline
- SSE resilience: disconnect and verify reconnection

---

## 13. Review Feedback (added during doc-review)

This section captures open questions, clarifications, risks, and simplification opportunities surfaced from reviewing PLAN.md against the already-built market-data subsystem (see `MARKET_DATA_SUMMARY.md`). Items are grouped by theme; many are small but worth resolving before downstream agents start work, because they pin contracts at the seams between components.

### 13.1 Questions and clarifications

**Lifecycle and initialization**

- Section 7 says the DB initializes "on startup (or first request)." Which is it? The market-data background task and the 30-second `portfolio_snapshots` writer both need the schema present before they can run, so lazy-on-first-request would race with startup tasks. Recommend: initialize unconditionally inside FastAPI's `lifespan` context manager before any background task starts.
  Answer : as recomended
- When does the market-data background task actually start, and does it keep running with zero connected SSE clients? It must, because `portfolio_snapshots` and any real-time portfolio valuation depend on a fresh price cache. Worth stating explicitly.
  Answer : As recomended, it should be running in background to keep real time data on screen, and market data should be fetch as soon as the app UI loads so the data is present on screen on page load.
- Section 6 mentions the price cache "supports future multi-user scenarios" — but with `user_id="default"` hardcoded everywhere and the cache being a process-global singleton, what does "multi-user-ready" actually mean here? Either drop the claim or define what the path looks like (per-user watchlists feeding into one shared price cache is fine — just say so).
  Answer : multi user means that platform supports more than one user. Initially only one user but on further iterations it will support multiple users.
  **API contract details**
- `POST /api/portfolio/trade` — what does the response body look like? The executed trade row? The updated cash + position? Both? Frontend needs to know whether to optimistically update or refetch.
  Answer : you can decide based on the build.
- `POST /api/watchlist` — request body shape `{ticker}` is shown, but normalization rules are not. Are tickers uppercased server-side? Validated against a known set? Rejected if already present (409) or treated idempotently (200)?
  Answer : you can decide based on the build.
- `DELETE /api/watchlist/{ticker}` — 404 if absent, or idempotent 204? Same for removing a ticker the user has an open position in (should that be blocked, or allowed?).
  Answer : you can decide based on the build.
- No `GET /api/chat/history` endpoint is listed, but the frontend needs to render past conversation on page reload (per Section 7 we persist `chat_messages`). Either add the endpoint or state that chat history starts fresh per page load.
  Answer : you can decide based on the build.
- `GET /api/portfolio` — does this include `previous_close` or any per-ticker daily-change basis the UI needs for the "daily change %" column in the watchlist? The price cache only holds `previous_price` (last tick), not daily open. Need to decide what "daily change %" actually means in this app.
  Answer : you can decide based on the build.
  **LLM integration**

- The `cerebras-inference` skill targets `openrouter/openai/gpt-oss-120b`. Does that model reliably honour OpenRouter's `response_format: json_schema` strict mode? If not, the plan should explicitly fall back to JSON-mode plus pydantic validation with a single retry on parse failure — otherwise the agent building this will quietly invent its own strategy.
  Answer : Have another fast model as back up in case we have to fallback.
- Conversation history: how many turns are sent back to the LLM per request? An unbounded `chat_messages` table will eventually blow the context window. Recommend: cap at last N messages (e.g., 20) or last K tokens.
  Answer : keep it configurable in a seperate config file
- What if the LLM proposes a trade for a ticker not in the watchlist? Auto-add to watchlist, or reject? Same question for a ticker the price cache doesn't know about.
  Answer : Add to watchlist
- `LLM_MOCK=true` — what shape do the mock responses take? Static fixed JSON? Cycling through fixtures? E2E tests need to depend on this being deterministic and well-defined.
  Answer : for mock testing static fixed json
- What happens when `OPENROUTER_API_KEY` is missing AND `LLM_MOCK` is not `true`? Boot failure? Lazy 503 on `/api/chat`? Recommend explicit boot-time check with a clear error.
  Answer : Add to watchlist

**Environment and config**

- The `MASSIVE_API_KEY` polling cadence depends on tier — how does the backend know which tier the user is on? It can't infer this; it has to be configured. Recommend a single `MASSIVE_POLL_INTERVAL_SECONDS` env var with a sensible default of 15 (free-tier safe).
  Answer : keep it in configuration
- Switching `MASSIVE_API_KEY` on/off requires a container restart — state that explicitly.
  Answer : keep it in configuration

**Frontend**

- "Sparklines accumulated from SSE since page load" means a hard refresh resets them. Acceptable for a demo, but call it out as an intentional limitation rather than letting the frontend agent discover it and reinvent something more complex.
- Where does the "currently selected ticker for the main chart" live — in-memory React state, URL hash, or persisted to backend? URL hash is the cheapest way to make refreshes preserve the view.
- Section 10 mentions both Lightweight Charts and Recharts. Pick one in the plan so the frontend agent doesn't relitigate it. Recommend Lightweight Charts for the main chart (canvas, fast for time series) and pure SVG/CSS for sparklines — Recharts is overkill for sparklines and slower for the main chart.

### 13.2 Risks worth flagging

- **Float precision on money.** `cash_balance`, `avg_cost`, `quantity`, and `price` are all `REAL` (SQLite IEEE-754 float). Repeated buy/sell cycles will drift. For a fake-money demo this is tolerable, but it will show up in tests that expect exact equality. Options: (a) accept and use `pytest.approx` in tests, (b) store cash and cost as integer cents, (c) use `numeric`/`Decimal` via the Python adapter. Pick one and document.
- **Trade endpoint is not idempotent.** A retried POST creates a duplicate trade. For a demo this is unlikely to matter, but the auto-executing LLM amplifies the blast radius if anything ever double-fires. Cheapest mitigation: accept a client-provided `idempotency_key` and de-dupe on it; or just accept the risk and document it.
- **Unbounded growth tables.** `portfolio_snapshots` at 30 s cadence = ~2,880 rows/day; `chat_messages` grows per turn. No retention or pagination policy is specified. Probably fine for a demo session, but state the assumption.
- **Auto-executed LLM trades + hallucinated tickers.** Plan says validation = "sufficient cash / shares." It does not say "ticker must exist in the market data source." Add that check, otherwise an LLM typo creates a position in a ticker the SSE stream has never heard of.
- **Two directories named "db".** `backend/db/` (schema definitions, code) and top-level `db/` (volume mount, runtime SQLite file) will confuse readers and agents. Rename one — recommend `backend/database/` for the code so the only `db/` in the tree is the data directory.
- **Volume binding inconsistency.** Section 11 shows `docker run -v finally-data:/app/db` (named volume) while the directory-structure section calls top-level `db/` the "volume mount target" (implying a bind mount). These are not the same. Pick one — bind mount (`./db:/app/db`) is friendlier for "open the SQLite file locally" workflows; named volume is more portable. Document the choice once.
- **SSE behind reverse proxies.** Not relevant for `localhost`, but if anyone deploys this to App Runner / Render / behind nginx, the proxy must disable response buffering on the SSE route. Worth a single sentence in the deployment section.

### 13.3 Simplification opportunities

_The reviewer's simplification proposals were declined — the affected tables and structures (`portfolio_snapshots`, `users_profile`, `user_id` columns, per-OS start scripts) are retained as written in Sections 4–11._

### 13.4 Minor notes

- `Massive (Polygon.io)` — the README/env-var comment is the only place the relationship is explained. Worth a one-liner in Section 6 too, since "Massive" alone is non-obvious. **Resolved**: added to Section 6.
- Section 11's stage-1 Dockerfile uses `npm install` — should be `npm ci` for reproducible builds from `package-lock.json`. **Resolved**: Section 11.
- Section 12 lists test scenarios but does not say what counts as "done" (coverage %, count of E2E specs). The market-data subsystem hit 84% / 73 tests — set a similar bar here for the rest, or explicitly say "no coverage gate, scenario-driven only." **Resolved**: Section 12 now sets ≥80% backend coverage and "scenario-driven only" for E2E.
- The plan repeatedly refers to "the user" in the singular while keeping the multi-user `user_id` columns. Pick a stance and stick to it. **Resolved**: per 13.1, single user now, multi-user is a roadmap item; `user_id` columns kept and the language in Section 6 reflects this.
- Section 9 says the LLM should "manage the watchlist proactively." Proactively how — only when asked, or unsolicited mid-conversation? Unsolicited watchlist changes would surprise users. **Resolved**: Section 9 now restricts to explicit-request only, with implicit-add via trade as the single exception.

### 13.5 Resolved open questions

All five items from the earlier review have been resolved:

1. **Missing `OPENROUTER_API_KEY` with `LLM_MOCK` unset** → fast boot failure with a clear error. **Resolved**: Section 9, "Boot-time Configuration".
2. **Float-precision strategy** → keep `REAL` columns, round at the UI layer, use `pytest.approx` in tests. **Resolved**: Section 7, "Money and Precision".
3. **Trade idempotency** → add an `idempotency_key` to `POST /api/portfolio/trade` and to the `trades` row. **Resolved**: Section 7 (schema column) and Section 8 ("Trade idempotency" subsection); a unit-test bullet added in Section 12.
4. **Trade response shape** → `{trade, cash_balance, position}`. **Resolved**: Section 8.
5. **Watchlist DELETE with an open position** → delete the watchlist row, leave the position visible in the positions table. **Resolved**: Section 8, "Watchlist semantics".

### 13.6 Codex review (planning/review-codex.md) — resolved

The first codex pass (items 1–6 below) was incorporated in the previous revision cycle. The second codex pass (`planning/review-codex.md`) surfaced six new contract gaps and three open questions. All are now resolved in the plan body:

**Findings from second Codex pass:**

1. **Chat transaction boundaries conflict with Massive-mode ticker validation** → Massive ticker resolution is now a pre-transaction validation step (Phase 1). DB transaction only begins after tickers are accepted by the market source. Market-source activation (start tracking) still happens after commit. The contradictory "rollback after commit" language is removed. **Resolved**: Section 9, "Chat Transaction Boundaries".

2. **Manual watchlist adds (`POST /api/watchlist`) had no unknown-ticker contract in Massive mode** → Massive mode now probes Polygon (5 s timeout) before inserting; returns 422 `code: "unknown_ticker"` if no data. Simulator mode accepts any syntactically valid symbol unchanged. **Resolved**: Section 8, "Watchlist semantics".

3. **Daily-change field name inconsistency (`day_open` vs `session_open`)** → `GET /api/portfolio` response now uses `session_open` everywhere, matching the `PriceCache`, `PriceUpdate`, and `GET /api/watchlist` shapes. **Resolved**: Section 8, portfolio response shape.

4. **SSE description incorrectly said "equivalent to watchlist"** → Updated to "all actively tracked tickers — the union of the user's watchlist and any tickers with open positions." **Resolved**: Section 6, "SSE Streaming".

5. **Static-export Next.js + URL hash need implementation guard** → Added explicit note: `window.location.hash` must be read client-side in `useEffect`, never during render/static generation; default ticker is AAPL. **Resolved**: Section 10.

6. **Section 13 noise with stale review material** → Old question/answer pairs in Section 13.1 are retained for traceability but all open items from those passes are resolved in the plan body. Section 13.6 is now the authoritative resolved-decisions log.

**Open questions from second Codex pass:**

- **Error response shape** → All `/api/*` errors return `{"error": {"code": "...", "message": "...", "details": {}}}`. Machine-readable `code` values defined. **Resolved**: Section 8, "Error response shape".
- **Fractional quantity precision** → Any positive float accepted; no minimum increment. `quantity <= 0` returns 422. **Resolved**: Section 8, "Quantity precision".
- **`GET /api/portfolio/history` pagination** → `?limit=N` param added (default 500, max 2000), results oldest-first. **Resolved**: Section 8, portfolio history query params.

**Previously resolved (first pass):**

1. Idempotency response snapshots → Section 7 (schema), Section 8 ("Trade idempotency").
2. `session_open` on `PriceUpdate`/`PriceCache` → Section 6, "Daily Change Reference Price".
3. Tracked-ticker set = `watchlist ∪ open positions` → Section 6, Section 8.
4. Simulator vs Massive unknown-ticker contract → Section 9, "Unknown / Unwatched Tickers".
5. Chat transaction boundary subsection added → Section 9.
6. `UNIQUE (user_id, idempotency_key)` → Section 7 (`trades`).
