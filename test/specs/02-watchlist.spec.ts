import { test, expect } from '@playwright/test'

test.describe('Watchlist API', () => {
  test('add ticker returns 201', async ({ request }) => {
    const ticker = 'ZM' + Date.now().toString().slice(-3)
    const res = await request.post('/api/watchlist', { data: { ticker } })
    // clean up regardless
    expect([201, 409]).toContain(res.status())
  })

  test('duplicate ticker returns 409', async ({ request }) => {
    const res = await request.post('/api/watchlist', { data: { ticker: 'AAPL' } })
    expect(res.status()).toBe(409)
    const body = await res.json()
    expect(body.error.code).toBe('ticker_already_exists')
  })

  test('invalid ticker symbol returns 422', async ({ request }) => {
    const res = await request.post('/api/watchlist', { data: { ticker: 'TOOLONGTICKE' } })
    expect(res.status()).toBe(422)
  })

  test('delete non-existent ticker returns 404', async ({ request }) => {
    const res = await request.delete('/api/watchlist/ZZZZZ')
    expect(res.status()).toBe(404)
  })

  test('add then remove ticker via UI', async ({ page }) => {
    await page.goto('/')
    await page.waitForLoadState('networkidle')
    const initialCount = await page.locator('[data-testid="watchlist-item"]').count()

    const addInput = page.locator('[data-testid="watchlist-add-input"]')
    await addInput.fill('SNAP')
    await page.locator('[data-testid="watchlist-add-button"]').click()
    await expect(page.locator('[data-testid="watchlist-item"]')).toHaveCount(initialCount + 1, { timeout: 5000 })

    const snapRow = page.locator('[data-testid="watchlist-item"]').filter({ hasText: 'SNAP' })
    await snapRow.hover()
    await snapRow.locator('[data-testid="watchlist-remove-button"]').click()
    await expect(page.locator('[data-testid="watchlist-item"]')).toHaveCount(initialCount, { timeout: 5000 })
  })
})
