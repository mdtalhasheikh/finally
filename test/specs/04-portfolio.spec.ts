import { test, expect } from '@playwright/test'

test.describe('Portfolio visualization', () => {
  test('heatmap renders after buying a position', async ({ page, request }) => {
    await request.post('/api/portfolio/trade', {
      data: { ticker: 'TSLA', side: 'buy', quantity: 1 },
    })
    await page.goto('/')
    await page.waitForLoadState('networkidle')
    await page.waitForTimeout(1000)
    const heatmap = page.locator('[data-testid="portfolio-heatmap"]')
    await expect(heatmap).toBeVisible({ timeout: 8000 })
    await expect(heatmap).toContainText('TSLA')
  })

  test('P&L chart is visible', async ({ page }) => {
    await page.goto('/')
    await page.waitForLoadState('networkidle')
    await expect(page.locator('[data-testid="pnl-chart"]')).toBeVisible({ timeout: 8000 })
  })

  test('positions table shows positions', async ({ page, request }) => {
    await request.post('/api/portfolio/trade', {
      data: { ticker: 'JPM', side: 'buy', quantity: 1 },
    })
    await page.goto('/')
    await page.waitForLoadState('networkidle')
    await expect(page.locator('[data-testid="positions-table"]')).toContainText('JPM', { timeout: 8000 })
  })
})
