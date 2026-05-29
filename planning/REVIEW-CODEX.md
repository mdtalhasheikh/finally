# Codex Review of PLAN.md

## Findings

1. **High: Chat transaction boundaries conflict with Massive-mode ticker validation.**
   PLAN.md says an off-watchlist LLM trade is added to the watchlist before execution, and in Massive mode the implicit add is rolled back if Polygon returns no data (`PLAN.md:449-456`). Later, it says market-data side effects are applied only after DB commit, and if the market source rejects the symbol the assistant message is updated after the fact (`PLAN.md:460-470`). Those two flows cannot both be true: if the DB has already committed the watchlist row/trade state, there is no clean rollback path for the implicit add, and executing the trade before source validation can create a position the price cache cannot value. Recommendation: make Massive ticker resolution a pre-transaction/pre-trade validation step. Only begin the DB transaction after the ticker has been accepted by the selected market source, or explicitly accept the committed-error model and remove the rollback language.

2. **High: Manual watchlist adds do not define unknown-ticker behavior in Massive mode.**
   `POST /api/watchlist` is specified only as trim/uppercase/regex plus 201/409/422 (`PLAN.md:374-379`). Unknown-symbol probing is defined only for LLM trades (`PLAN.md:449-458`). A user can manually add `GOOOG` in Massive mode and the plan does not say whether the API returns 404/422, inserts an unpriced row, or inserts then later errors. Because `/api/watchlist` promises latest prices and daily-change fields, this needs the same source-resolution contract as LLM implicit adds. Recommendation: for Massive mode, validate against Polygon before inserting and return a clear 404 or 422-style domain error when no data is available; simulator mode can keep accepting syntactically valid tickers.

3. **Medium: Daily-change field names are inconsistent across API contracts.**
   The market-data model is defined around `session_open` (`PLAN.md:205-212`), and `GET /api/watchlist` returns `session_open` (`PLAN.md:379`). `GET /api/portfolio` instead says position rows include `day_open` (`PLAN.md:336`). This will split frontend/backed models for the same value. Recommendation: use one field name everywhere, preferably `session_open` because it matches the market-data extension and watchlist response.

4. **Medium: SSE stream description still says watchlist-equivalent despite open-position tracking.**
   The tracked ticker set is correctly defined as `watchlist ∪ open positions` (`PLAN.md:197-203`), but the SSE section says "in the single-user model this is equivalent to the user's watchlist" (`PLAN.md:218`). That is false after the user removes a ticker with an open position. Recommendation: update the SSE wording to say it streams all actively tracked tickers, which are watchlist entries plus open positions.

5. **Medium: Static-export Next.js and URL hash state need an implementation guard.**
   The plan requires a static Next.js export served by FastAPI (`PLAN.md:70-72`) and storing the selected ticker in the URL hash (`PLAN.md:540`). That is workable, but any frontend code that reads `window.location.hash` during render will break static generation or hydration. Recommendation: state that hash parsing must happen client-side after mount, with a deterministic default ticker for the exported HTML.

6. **Low: The embedded historical review section is now noisy and partially misleading.**
   Section 13 includes prior questions, user answers, and old risks that the document later says are resolved (`PLAN.md:655-753`). Some answers are clearly stale or wrong, such as the missing-OpenRouter-key answer saying "Add to watchlist" (`PLAN.md:690-691`). Downstream agents may skim Section 13 and implement from stale notes instead of the resolved body. Recommendation: move old review material to `planning/archive/` or replace Section 13 with a short changelog of resolved decisions.

## Open Questions

- What exact error response shape should failed trades/watchlist changes use? The plan lists status codes but not an error body. A shared `{code, message, details?}` shape would make frontend and chat action rendering more predictable.
- Should `POST /api/portfolio/trade` allow fractional quantities with any positive decimal, or enforce a minimum increment/precision? The schema says fractional shares are supported, but validation precision is not specified.
- Should `/api/portfolio/history` be capped by time/count query params, even if retention is unbounded? The table can grow without cleanup, and the frontend chart does not need all historical rows on every load.

## Summary

The plan is much tighter than the earlier review notes: startup sequencing, idempotency, snapshotting, SSE, and mock LLM behavior are now mostly specified. The main issue left is the boundary between DB transactions and market-source validation. Resolve that before backend implementation, because it affects watchlist writes, LLM action execution, trade validity, and portfolio valuation.
