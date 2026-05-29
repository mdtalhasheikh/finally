import { defineConfig } from '@playwright/test'

export default defineConfig({
  testDir: './specs',
  timeout: 30000,
  retries: 1,
  use: {
    baseURL: process.env.BASE_URL || 'http://localhost:8000',
    headless: true,
    screenshot: 'only-on-failure',
  },
  reporter: [['list'], ['html', { open: 'never' }]],
})
