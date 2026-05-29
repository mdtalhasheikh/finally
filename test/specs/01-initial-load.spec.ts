import { test, expect } from '@playwright/test'

test.describe('Initial load', () => {
  test('health endpoint returns ok', async ({ request }) => {
    const res = await request.get('/api/health')
    expect(res.status()).toBe(200)
    const body = await res.json()
    expect(body.status).toBe('ok')
  })

  test('watchlist API returns 10 default tickers', async ({ request }) => {
    const res = await request.get('/api/watchlist')
    expect(res.status()).toBe(200)
    const items = await res.json()
    expect(items.length).toBe(10)
    const tickers = items.map((i: { ticker: string }) => i.ticker)
    expect(tickers).toContain('AAPL')
    expect(tickers).toContain('GOOGL')
    expect(tickers).toContain('NVDA')
  })

  test('portfolio API returns $10k cash balance', async ({ request }) => {
    const res = await request.get('/api/portfolio')
    expect(res.status()).toBe(200)
    const body = await res.json()
    expect(body.cash_balance).toBeCloseTo(10000, 0)
  })

  test('portfolio history has at least one snapshot', async ({ request }) => {
    const res = await request.get('/api/portfolio/history')
    expect(res.status()).toBe(200)
    const snapshots = await res.json()
    expect(snapshots.length).toBeGreaterThanOrEqual(1)
    expect(snapshots[0].total_value).toBeGreaterThan(0)
  })

  test('page loads and shows watchlist items', async ({ page }) => {
    await page.goto('/')
    await expect(page.locator('[data-testid="watchlist-item"]').first()).toBeVisible({ timeout: 10000 })
    const count = await page.locator('[data-testid="watchlist-item"]').count()
    expect(count).toBe(10)
  })

  test('page shows cash balance containing 10,000', async ({ page }) => {
    await page.goto('/')
    const cashEl = page.locator('[data-testid="cash-balance"]')
    await expect(cashEl).toBeVisible({ timeout: 10000 })
    await expect(cashEl).toContainText('10,000')
  })

  test('SSE connection status becomes connected', async ({ page }) => {
    await page.goto('/')
    await page.waitForTimeout(3000)
    const status = page.locator('[data-testid="connection-status"]')
    await expect(status).toBeVisible()
    await expect(status).toHaveAttribute('data-status', 'connected', { timeout: 8000 })
  })
})
