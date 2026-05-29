export interface PriceUpdate {
  ticker: string
  price: number
  previous_price: number
  timestamp: string
  change: number
  direction: 'up' | 'down' | 'flat'
  session_open?: number
}

export interface Position {
  ticker: string
  quantity: number
  avg_cost: number
  current_price: number
  session_open: number
  daily_change_pct: number
  unrealized_pnl: number
  unrealized_pnl_pct: number
}

export interface Portfolio {
  positions: Position[]
  cash_balance: number
  total_value: number
  total_unrealized_pnl: number
}

export interface WatchlistItem {
  ticker: string
  current_price: number
  session_open: number
  daily_change_pct: number
  added_at: string
}

export interface Trade {
  id: string
  ticker: string
  side: 'buy' | 'sell'
  quantity: number
  price: number
  executed_at: string
}

export interface ChatMessage {
  id: string
  role: 'user' | 'assistant'
  content: string
  actions?: {
    trades?: Array<{
      ticker: string
      side: string
      quantity: number
      price: number
      status: string
      error?: string
    }>
    watchlist_changes?: Array<{
      ticker: string
      action: string
      status: string
    }>
  }
  created_at: string
}

export interface SnapshotPoint {
  id: string
  total_value: number
  recorded_at: string
}
