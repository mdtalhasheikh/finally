import { test, expect } from '@playwright/test'

test.describe('AI Chat (mock mode)', () => {
  test('chat returns mock response', async ({ request }) => {
    const res = await request.post('/api/chat', { data: { message: 'hello there' } })
    expect(res.status()).toBe(200)
    const body = await res.json()
    expect(typeof body.message).toBe('string')
    expect(body.message.length).toBeGreaterThan(0)
    expect(Array.isArray(body.trades)).toBe(true)
  })

  test('mock-trade triggers AAPL buy', async ({ request }) => {
    const p0 = await (await request.get('/api/portfolio')).json()
    const cashBefore = p0.cash_balance

    const res = await request.post('/api/chat', { data: { message: 'mock-trade please' } })
    expect(res.status()).toBe(200)
    const body = await res.json()
    expect(body.trades.length).toBeGreaterThan(0)
    expect(body.trades[0].ticker).toBe('AAPL')

    const p1 = await (await request.get('/api/portfolio')).json()
    expect(p1.cash_balance).toBeLessThan(cashBefore)
  })

  test('chat history is retrievable', async ({ request }) => {
    await request.post('/api/chat', { data: { message: 'store this message' } })
    const res = await request.get('/api/chat/history')
    expect(res.status()).toBe(200)
    const history = await res.json()
    expect(Array.isArray(history)).toBe(true)
    expect(history.length).toBeGreaterThan(0)
  })

  test('UI: send chat message and see response', async ({ page }) => {
    await page.goto('/')
    await page.waitForLoadState('networkidle')
    await page.locator('[data-testid="chat-input"]').fill('hello')
    await page.locator('[data-testid="chat-send-button"]').click()
    await expect(page.locator('[data-testid="chat-message"]').last()).toBeVisible({ timeout: 15000 })
    await expect(page.locator('[data-testid="chat-message"]').last()).toContainText('Mock response')
  })
})
