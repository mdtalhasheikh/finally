import { test, expect } from '@playwright/test'

test.describe('Trading API', () => {
  test('buy shares reduces cash and creates position', async ({ request }) => {
    const p0 = await (await request.get('/api/portfolio')).json()
    const cashBefore = p0.cash_balance

    const res = await request.post('/api/portfolio/trade', {
      data: { ticker: 'AAPL', side: 'buy', quantity: 2 },
    })
    expect(res.status()).toBe(201)
    const body = await res.json()
    expect(body.trade.ticker).toBe('AAPL')
    expect(body.trade.quantity).toBe(2)
    expect(body.cash_balance).toBeLessThan(cashBefore)
    expect(body.position.quantity).toBeGreaterThanOrEqual(2)
  })

  test('sell shares increases cash', async ({ request }) => {
    // Buy first
    await request.post('/api/portfolio/trade', {
      data: { ticker: 'MSFT', side: 'buy', quantity: 3 },
    })
    const p1 = await (await request.get('/api/portfolio')).json()
    const cashAfterBuy = p1.cash_balance

    const res = await request.post('/api/portfolio/trade', {
      data: { ticker: 'MSFT', side: 'sell', quantity: 1 },
    })
    expect(res.status()).toBe(201)
    const body = await res.json()
    expect(body.cash_balance).toBeGreaterThan(cashAfterBuy)
  })

  test('buy with insufficient cash returns 422', async ({ request }) => {
    const res = await request.post('/api/portfolio/trade', {
      data: { ticker: 'AAPL', side: 'buy', quantity: 9999999 },
    })
    expect(res.status()).toBe(422)
    const body = await res.json()
    expect(body.error.code).toBe('insufficient_cash')
  })

  test('sell more than owned returns 422', async ({ request }) => {
    const res = await request.post('/api/portfolio/trade', {
      data: { ticker: 'GOOGL', side: 'sell', quantity: 99999 },
    })
    expect(res.status()).toBe(422)
    const body = await res.json()
    expect(body.error.code).toBe('insufficient_shares')
  })

  test('quantity <= 0 returns 422', async ({ request }) => {
    const res = await request.post('/api/portfolio/trade', {
      data: { ticker: 'AAPL', side: 'buy', quantity: 0 },
    })
    expect(res.status()).toBe(422)
  })

  test('idempotency key deduplicates trades', async ({ request }) => {
    const key = 'e2e-idem-' + Date.now()
    const r1 = await request.post('/api/portfolio/trade', {
      data: { ticker: 'V', side: 'buy', quantity: 1, idempotency_key: key },
    })
    expect(r1.status()).toBe(201)
    const b1 = await r1.json()

    const r2 = await request.post('/api/portfolio/trade', {
      data: { ticker: 'V', side: 'buy', quantity: 1, idempotency_key: key },
    })
    expect(r2.status()).toBe(200)
    const b2 = await r2.json()
    expect(b2.trade.id).toBe(b1.trade.id)
  })

  test('UI: buy via trade bar shows position', async ({ page }) => {
    await page.goto('/')
    await page.waitForLoadState('networkidle')
    await page.locator('[data-testid="trade-ticker-input"]').fill('AAPL')
    await page.locator('[data-testid="trade-quantity-input"]').fill('1')
    await page.locator('[data-testid="trade-buy-button"]').click()
    await expect(page.locator('[data-testid="positions-table"]')).toContainText('AAPL', { timeout: 8000 })
  })
})
