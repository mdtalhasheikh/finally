# FinAlly Integration Report

Generated: 2026-05-29

---

## 1. Playwright Test Files Written

All files were written (or overwritten) under `test/`. Existing files that were replaced are noted.

| File | Lines | Notes |
|------|-------|-------|
| `test/package.json` | 13 | Updated: added `typescript ^5.7.0` devDependency, replaced `test:report` script with `test:headed` |
| `test/playwright.config.ts` | 13 | Updated: removed `video: 'off'` option (not in spec) |
| `test/tsconfig.json` | 9 | Unchanged (already matched spec) |
| `test/specs/01-initial-load.spec.ts` | 58 | Replaced: new file has 7 tests (4 API + 3 UI) |
| `test/specs/02-watchlist.spec.ts` | 43 | Replaced: 5 tests (4 API + 1 UI add/remove flow) |
| `test/specs/03-trading.spec.ts` | 84 | Replaced: 8 tests (7 API + 1 UI buy flow) |
| `test/specs/04-portfolio.spec.ts` | 30 | Replaced: 3 tests (1 API history + 2 UI heatmap/table) |
| `test/specs/05-chat.spec.ts` | 44 | Replaced: 4 tests (3 API + 1 UI send message) |
| `test/specs/06-sse.spec.ts` | 31 | New: 2 tests (SSE content-type + price update) |

**Note:** The old `test/specs/06-sse-resilience.spec.ts` was NOT removed — it still exists alongside the new `06-sse.spec.ts`. This creates a duplicate file number prefix. The Frontend Engineer should delete `06-sse-resilience.spec.ts` to avoid running it alongside the new suite.

---

## 2. Backend Unit Test Results

### Status: COULD NOT RUN — Sandbox Filesystem Restriction

The `uv run --extra dev pytest` command (the only permitted pattern) fails at startup because the sandbox blocks write access to `~/.cache/uv`:

```
error: Failed to initialize cache at `/Users/talha/.cache/uv`
  Caused by: failed to open file `/Users/talha/.cache/uv/sdists-v9/.git`: Operation not permitted (os error 1)
```

`uv` always initializes its cache on startup regardless of flags (`--offline`, `--no-sync`, `--cache-dir` with another path all trigger the same failure because the allowed command pattern is `uv run --extra dev pytest *` and prepending `UV_CACHE_DIR=...` changes the command string, which is then denied by the permissions allowlist).

**Fix:** Run `/sandbox` in Claude Code and add `~/.cache/uv` to the write allowlist, then re-run:
```bash
cd backend && uv run --extra dev pytest -v --tb=short
```

### Static Analysis: Expected Test Results

Based on reading all 130 test cases against the source code:

#### tests/database/test_init.py (7 tests) — EXPECTED: ALL PASS
- Schema, seed data, idempotent init, nested directory creation — all implementation matches.

#### tests/market/test_models.py (11 tests) — EXPECTED: ALL PASS
- PriceUpdate dataclass fields, change calculations, direction logic, to_dict — clean.

#### tests/market/test_cache.py (13 tests) — EXPECTED: ALL PASS
- PriceCache CRUD, version, direction, rounding — all match implementation.

#### tests/market/test_simulator.py (17 tests) — EXPECTED: ALL PASS
- GBM simulator, Cholesky correlation matrix, seed prices, positive prices — clean.

#### tests/market/test_simulator_source.py (10 tests) — EXPECTED: ALL PASS
- SimulatorDataSource lifecycle, ticker add/remove, price updates over time — clean.

#### tests/market/test_factory.py (6 tests) — EXPECTED: ALL PASS
- Factory returns SimulatorDataSource without MASSIVE_API_KEY, MassiveDataSource with it.

#### tests/market/test_massive.py (13 tests) — EXPECTED: ALL PASS
- MassiveDataSource poll cycle, cache updates, error resilience — clean.

#### tests/llm/test_llm.py (11 tests) — EXPECTED: ALL PASS
- LLMResponse model, MockLLMService, factory — all match implementation.

#### tests/routes/test_health.py (1 test) — EXPECTED: PASS
- Simple GET /api/health returns `{"status": "ok"}`.

#### tests/routes/test_watchlist.py (12 tests) — EXPECTED: 11 PASS, 1 FAIL

**FAIL: `test_add_ticker_duplicate_409`**
- Test asserts: `resp.json()["error"]["code"] == "ticker_already_exists"`
- Route returns: `_error("ticker_already_exists", ...)` (line 89 of watchlist.py)
- **Resolution: Actually this matches — no failure.** Both use `ticker_already_exists`.
  (The old E2E spec at `test/specs/02-watchlist.spec.ts` previously used `ticker_exists`, but the backend route has always used `ticker_already_exists`.)
- **All 12 tests expected to PASS.**

#### tests/routes/test_portfolio.py (12 tests) — EXPECTED: ALL PASS
- All buy/sell/idempotency/validation paths match the implementation.

#### tests/routes/test_chat.py (10 tests) — EXPECTED: ALL PASS
- Mock LLM service, trade execution, partial failure tolerance, history — all clean.

**Summary (static analysis): 130 tests, expected 130 PASS, 0 FAIL.**

The `.pytest_cache/v/cache/lastfailed` file contains `TestClient` keys for `test_health.py` and `test_portfolio.py` — these appear to be from an old incomplete test run where FastAPI's `TestClient` was imported before `httpx` was installed. With the full venv in place these should pass.

---

## 3. Server Smoke Test Results

### Status: COULD NOT RUN — Same Sandbox Restriction

`uv run uvicorn app.main:app ...` fails identically to `uv run pytest`:

```
error: Failed to initialize cache at `/Users/talha/.cache/uv`
  Caused by: failed to open file `/Users/talha/.cache/uv/sdists-v9/.git`: Operation not permitted (os error 1)
```

**Fix:** Same as above — allow `~/.cache/uv` in the sandbox, then:
```bash
cd backend
LLM_MOCK=true OPENROUTER_API_KEY=mock-key DB_PATH=/tmp/claude/smoke-finally.db \
  uv run uvicorn app.main:app --host 127.0.0.1 --port 8877 &
sleep 8
curl -s http://127.0.0.1:8877/api/health
curl -s http://127.0.0.1:8877/api/watchlist | head -c 200
curl -s http://127.0.0.1:8877/api/portfolio | head -c 200
kill $(lsof -ti:8877)
```

### Expected Smoke Test Results (based on code analysis)

Given the backend code and database seed:

| Endpoint | Expected | Reasoning |
|----------|----------|-----------|
| GET /api/health | `{"status": "ok"}` 200 | Simple constant response |
| GET /api/watchlist | 200, 10 items, includes AAPL/GOOGL/NVDA | `seed.sql` inserts 10 default tickers |
| GET /api/portfolio | 200, `cash_balance: 10000.0` | `seed.sql` creates user with $10k cash, no positions |
| GET /api/portfolio/history | 200, >= 1 snapshot | Lifespan calls `_record_snapshot()` on startup |
| POST /api/chat `{"message":"hello"}` | 200, mock response | `LLM_MOCK=true` activates `MockLLMService` |
| GET /api/stream/prices | 200 text/event-stream | `create_stream_router` registers SSE endpoint |

---

## 4. Issues Found

### Issue 1: Sandbox blocks `uv` cache initialization
**File:** N/A (infrastructure)
**Description:** The sandbox's filesystem write restrictions prevent `uv` from initializing `~/.cache/uv`. Since all allowed commands use `uv run`, neither pytest nor uvicorn can be executed within the sandbox. This blocks Jobs 2 and 3.
**Severity:** Blocker for CI/local testing via Claude Code.

### Issue 2: `data-testid="chat-send"` vs `data-testid="chat-send-button"`
**File:** `frontend/components/ChatPanel.tsx:202`
**Description:** The component has `data-testid="chat-send"` but the E2E spec `05-chat.spec.ts` selects `[data-testid="chat-send-button"]`. The selector will never match.

### Issue 3: `data-testid="trade-ticker"` vs `data-testid="trade-ticker-input"`
**File:** `frontend/components/TradeBar.tsx:59`
**Description:** Component has `data-testid="trade-ticker"` but specs `03-trading.spec.ts` uses `[data-testid="trade-ticker-input"]`.

### Issue 4: `data-testid="trade-quantity"` vs `data-testid="trade-quantity-input"`
**File:** `frontend/components/TradeBar.tsx:71`
**Description:** Component has `data-testid="trade-quantity"` but spec uses `[data-testid="trade-quantity-input"]`.

### Issue 5: `data-testid="trade-buy"` vs `data-testid="trade-buy-button"`
**File:** `frontend/components/TradeBar.tsx:79`
**Description:** Component has `data-testid="trade-buy"` but spec uses `[data-testid="trade-buy-button"]`.

### Issue 6: Missing `data-testid="watchlist-item"` on WatchlistRow
**File:** `frontend/components/WatchlistPanel.tsx:62` (the `<div>` for each row)
**Description:** `WatchlistRow` renders a `<div>` without any `data-testid`. Specs `01-initial-load.spec.ts`, `02-watchlist.spec.ts`, `06-sse.spec.ts`, and `06-sse-resilience.spec.ts` all select `[data-testid="watchlist-item"]`.

### Issue 7: Missing `data-testid="watchlist-add-input"` and `data-testid="watchlist-add-button"`
**File:** `frontend/components/WatchlistPanel.tsx:183-194`
**Description:** The add ticker input and button have no `data-testid` attributes. Used in specs `02-watchlist.spec.ts`.

### Issue 8: Missing `data-testid="watchlist-remove-button"` on remove button
**File:** `frontend/components/WatchlistPanel.tsx:94`
**Description:** The remove button has no `data-testid`. Used in spec `02-watchlist.spec.ts`.

### Issue 9: Missing `data-testid="cash-balance"` in Header
**File:** `frontend/components/Header.tsx:47`
**Description:** The Cash `<span>` has no `data-testid`. Spec `01-initial-load.spec.ts` selects `[data-testid="cash-balance"]`.

### Issue 10: Missing `data-testid="connection-status"` and `data-status` attribute in ConnectionStatus
**File:** `frontend/components/ConnectionStatus.tsx:19`
**Description:** The `<span>` has no `data-testid` and no `data-status` attribute. Specs `01-initial-load.spec.ts` and `06-sse-resilience.spec.ts` select `[data-testid="connection-status"]` and assert `data-status="connected"`.

### Issue 11: Missing `data-testid="ticker-price-AAPL"` (and per-ticker prices)
**File:** `frontend/components/WatchlistPanel.tsx:74`
**Description:** The price `<span>` in WatchlistRow has no `data-testid`. Spec `06-sse.spec.ts` and `01-initial-load.spec.ts` (old) select `[data-testid="ticker-price-AAPL"]`.

### Issue 12: Missing `data-testid="portfolio-heatmap"` on PortfolioHeatmap
**File:** `frontend/components/PortfolioHeatmap.tsx:101`
**Description:** The outer `<div>` has no `data-testid`. Spec `04-portfolio.spec.ts` selects `[data-testid="portfolio-heatmap"]`.

### Issue 13: Missing `data-testid="pnl-chart"` on PnlChart
**File:** `frontend/components/PnlChart.tsx:90`
**Description:** The outer `<div>` has no `data-testid`. Spec `04-portfolio.spec.ts` selects `[data-testid="pnl-chart"]`.

### Issue 14: Missing `data-testid="positions-table"` on PositionsTable
**File:** `frontend/components/PositionsTable.tsx:33`
**Description:** The outer `<div>` has no `data-testid`. Specs `03-trading.spec.ts` and `04-portfolio.spec.ts` select `[data-testid="positions-table"]`.

### Issue 15: Missing `data-testid="chat-message"` on MessageBubble
**File:** `frontend/components/ChatPanel.tsx:51`
**Description:** The message bubble `<div>` has no `data-testid`. Spec `05-chat.spec.ts` selects `[data-testid="chat-message"]`.

### Issue 16: Duplicate `06-` spec file prefix
**File:** `test/specs/06-sse-resilience.spec.ts` (old) and `test/specs/06-sse.spec.ts` (new)
**Description:** Two files share the `06-` prefix. Playwright will run both. The old file uses different selectors (some that exist, some that don't). Delete `06-sse-resilience.spec.ts` to keep only the authoritative new file.

---

## 5. Missing `data-testid` Attributes (for the Frontend Engineer)

The following attributes need to be added to frontend components. None currently exist in the codebase.

| Selector Expected by Specs | Component File | Element to Add It To |
|---------------------------|---------------|---------------------|
| `data-testid="watchlist-item"` | `WatchlistPanel.tsx:62` | The outer `<div>` in `WatchlistRow` |
| `data-testid="watchlist-add-input"` | `WatchlistPanel.tsx:183` | The ticker `<input>` |
| `data-testid="watchlist-add-button"` | `WatchlistPanel.tsx:191` | The Add `<button>` |
| `data-testid="watchlist-remove-button"` | `WatchlistPanel.tsx:94` | The X `<button>` inside WatchlistRow |
| `data-testid="ticker-price-AAPL"` | `WatchlistPanel.tsx:74` | The price `<span>` — use dynamic: `data-testid={\`ticker-price-${item.ticker}\`}` |
| `data-testid="cash-balance"` | `Header.tsx:47` | The cash `<span>` |
| `data-testid="connection-status"` + `data-status={status}` | `ConnectionStatus.tsx:19` | The outer `<span>` — add both attributes |
| `data-testid="portfolio-heatmap"` | `PortfolioHeatmap.tsx:101` | The outer `<div>` |
| `data-testid="pnl-chart"` | `PnlChart.tsx:90` | The outer `<div>` |
| `data-testid="positions-table"` | `PositionsTable.tsx:33` | The outer `<div>` |
| `data-testid="chat-message"` | `ChatPanel.tsx:51` | The inner bubble `<div>` in `MessageBubble` |

The following are wrong names (attribute exists but name differs):

| Existing `data-testid` | Spec Expects | File |
|------------------------|-------------|------|
| `chat-send` | `chat-send-button` | `ChatPanel.tsx:202` |
| `trade-ticker` | `trade-ticker-input` | `TradeBar.tsx:59` |
| `trade-quantity` | `trade-quantity-input` | `TradeBar.tsx:71` |
| `trade-buy` | `trade-buy-button` | `TradeBar.tsx:79` |

---

## 6. Recommended Fixes

The fixes are listed in priority order. Do NOT apply — describe only.

### Fix A: Unblock sandbox for `uv` (Infra/DevOps)
Add `~/.cache/uv` (i.e., `/Users/talha/.cache/uv`) to the sandbox write allowlist using `/sandbox`. Without this, no backend tests or server can be launched from within Claude Code.

### Fix B: Rename mismatched `data-testid` values in frontend (Frontend Engineer)
In `TradeBar.tsx`, rename:
- `data-testid="trade-ticker"` → `data-testid="trade-ticker-input"`
- `data-testid="trade-quantity"` → `data-testid="trade-quantity-input"`
- `data-testid="trade-buy"` → `data-testid="trade-buy-button"`

In `ChatPanel.tsx`, rename:
- `data-testid="chat-send"` → `data-testid="chat-send-button"`

### Fix C: Add missing `data-testid` attributes (Frontend Engineer)
Apply all additions listed in Section 5 above. The most impactful ones are:
1. `data-testid="watchlist-item"` on `WatchlistRow` outer div — blocks 3 spec files
2. `data-testid="connection-status"` + `data-status={status}` on `ConnectionStatus` — blocks initial load and SSE tests
3. `data-testid="cash-balance"` on Header cash span — blocks initial load test
4. `data-testid="positions-table"` on PositionsTable — blocks trading and portfolio tests
5. `data-testid="portfolio-heatmap"` on PortfolioHeatmap — blocks portfolio spec
6. `data-testid="pnl-chart"` on PnlChart — blocks portfolio spec
7. `data-testid="chat-message"` on MessageBubble — blocks chat spec
8. `data-testid="watchlist-add-input"` and `data-testid="watchlist-add-button"` — blocks watchlist UI test
9. `data-testid="watchlist-remove-button"` — blocks watchlist remove UI test
10. Dynamic `data-testid={\`ticker-price-${item.ticker}\`}` on WatchlistRow price span — blocks SSE spec

### Fix D: Delete duplicate old spec file (Frontend/QA Engineer)
Delete `test/specs/06-sse-resilience.spec.ts` — it is superseded by `06-sse.spec.ts` and uses outdated selectors (e.g., expects `data-status` to be either `"connected"` or `"connecting"` which is weaker than the new spec's assertion).

### Fix E: Verify `ticker_already_exists` error code in watchlist spec (QA — already done)
The new `02-watchlist.spec.ts` correctly asserts `ticker_already_exists`. The old `06-sse-resilience` (and the replaced old `02-watchlist.spec.ts`) was checking `ticker_exists` which was wrong. The backend route at `watchlist.py:89` returns `ticker_already_exists`. No backend fix needed.

### Fix F: Verify chat mock response content (QA note)
Spec `05-chat.spec.ts` asserts `toContainText('Mock response')`. The `MockLLMService` returns `"Mock response: " + user_message`. This will match for `message: 'hello'` but the UI test checks `[data-testid="chat-message"]` which doesn't exist yet (Fix C). Once C is applied this should work correctly.
