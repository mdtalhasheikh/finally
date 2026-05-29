import { Portfolio, WatchlistItem, ChatMessage, SnapshotPoint } from './types'

const BASE = '' // same origin

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(BASE + path, options)
  if (!res.ok) {
    const body = await res.json().catch(() => ({}))
    const err = body as { error?: { message?: string; code?: string } }
    throw Object.assign(
      new Error(err?.error?.message ?? res.statusText),
      { code: err?.error?.code, status: res.status }
    )
  }
  if (res.status === 204) return undefined as T
  return res.json() as Promise<T>
}

export const api = {
  getPortfolio: () => request<Portfolio>('/api/portfolio'),

  executeTrade: (
    ticker: string,
    side: 'buy' | 'sell',
    quantity: number,
    idempotencyKey: string
  ) =>
    request('/api/portfolio/trade', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ ticker, side, quantity, idempotency_key: idempotencyKey }),
    }),

  getPortfolioHistory: (limit = 500) =>
    request<SnapshotPoint[]>(`/api/portfolio/history?limit=${limit}`),

  getWatchlist: () => request<WatchlistItem[]>('/api/watchlist'),

  addToWatchlist: (ticker: string) =>
    request('/api/watchlist', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ ticker }),
    }),

  removeFromWatchlist: (ticker: string) =>
    request(`/api/watchlist/${ticker}`, { method: 'DELETE' }),

  sendChatMessage: (message: string) =>
    request<{ message: string; trades: unknown[]; watchlist_changes: unknown[] }>('/api/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message }),
    }),

  getChatHistory: () => request<ChatMessage[]>('/api/chat/history'),
}
