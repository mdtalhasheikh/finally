'use client'

import { useState, useCallback } from 'react'
import { v4 as uuidv4 } from 'uuid'
import { api } from '@/lib/api'

interface Props {
  defaultTicker?: string
  onTradeExecuted?: () => void
}

type ToastType = 'success' | 'error' | null

export default function TradeBar({ defaultTicker = '', onTradeExecuted }: Props) {
  const [ticker, setTicker] = useState(defaultTicker)
  const [quantity, setQuantity] = useState('')
  const [loading, setLoading] = useState(false)
  const [toast, setToast] = useState<{ type: ToastType; message: string } | null>(null)

  const showToast = useCallback((type: 'success' | 'error', message: string) => {
    setToast({ type, message })
    setTimeout(() => setToast(null), 3000)
  }, [])

  const executeTrade = useCallback(
    async (side: 'buy' | 'sell') => {
      const t = ticker.trim().toUpperCase()
      const q = parseFloat(quantity)

      if (!t) return showToast('error', 'Enter a ticker')
      if (!q || q <= 0) return showToast('error', 'Enter a valid quantity')

      setLoading(true)
      try {
        const idempotencyKey = uuidv4()
        await api.executeTrade(t, side, q, idempotencyKey)
        showToast('success', `${side.toUpperCase()} ${q} ${t} executed`)
        onTradeExecuted?.()
      } catch (err) {
        showToast('error', err instanceof Error ? err.message : 'Trade failed')
      } finally {
        setLoading(false)
      }
    },
    [ticker, quantity, showToast, onTradeExecuted]
  )

  return (
    <div className="flex items-center gap-3 px-4 py-2 border-t border-terminal-border bg-terminal-panel shrink-0">
      <span className="text-terminal-muted text-xs uppercase tracking-widest mr-1">Trade</span>

      <input
        className="bg-terminal-bg border border-terminal-border text-terminal-text text-sm px-2 py-1 rounded w-24 uppercase focus:outline-none focus:border-terminal-blue placeholder-terminal-muted"
        placeholder="TICKER"
        value={ticker}
        onChange={e => setTicker(e.target.value.toUpperCase())}
        disabled={loading}
        maxLength={8}
        data-testid="trade-ticker-input"
      />

      <input
        className="bg-terminal-bg border border-terminal-border text-terminal-text text-sm px-2 py-1 rounded w-28 focus:outline-none focus:border-terminal-blue placeholder-terminal-muted"
        placeholder="Quantity"
        type="number"
        min="0.0001"
        step="any"
        value={quantity}
        onChange={e => setQuantity(e.target.value)}
        disabled={loading}
        data-testid="trade-quantity-input"
      />

      <button
        className="px-4 py-1 rounded text-sm font-semibold text-white disabled:opacity-50 hover:opacity-80 transition-opacity"
        style={{ backgroundColor: '#209dd7' }}
        onClick={() => executeTrade('buy')}
        disabled={loading}
        data-testid="trade-buy-button"
      >
        {loading ? '...' : 'Buy'}
      </button>

      <button
        className="px-4 py-1 rounded text-sm font-semibold text-white disabled:opacity-50 hover:opacity-80 transition-opacity"
        style={{ backgroundColor: '#ef4444' }}
        onClick={() => executeTrade('sell')}
        disabled={loading}
        data-testid="trade-sell"
      >
        {loading ? '...' : 'Sell'}
      </button>

      {toast && (
        <span
          className="text-xs ml-2"
          style={{ color: toast.type === 'success' ? '#22c55e' : '#ef4444' }}
        >
          {toast.message}
        </span>
      )}
    </div>
  )
}
