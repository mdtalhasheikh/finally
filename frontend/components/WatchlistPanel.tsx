'use client'

import { useState, useRef, useCallback, useEffect } from 'react'
import { WatchlistItem } from '@/lib/types'
import { usePriceStore } from '@/lib/usePriceStore'
import Sparkline from './Sparkline'

interface Props {
  items: WatchlistItem[]
  selectedTicker: string | null
  onSelectTicker: (ticker: string) => void
  onAddTicker: (ticker: string) => Promise<void>
  onRemoveTicker: (ticker: string) => Promise<void>
}

function formatPrice(price: number): string {
  return price.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function formatChangePct(pct: number): string {
  return (pct >= 0 ? '+' : '') + pct.toFixed(2) + '%'
}

interface RowProps {
  item: WatchlistItem
  isSelected: boolean
  onSelect: () => void
  onRemove: () => void
  sparkData: number[]
}

function WatchlistRow({ item, isSelected, onSelect, onRemove, sparkData }: RowProps) {
  const priceRef = useRef<HTMLSpanElement>(null)
  const flashTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const prevPriceRef = useRef(item.current_price)

  // Flash animation when price changes
  useEffect(() => {
    const el = priceRef.current
    if (!el) return
    if (item.current_price === prevPriceRef.current) return

    const direction = item.current_price > prevPriceRef.current ? 'price-flash-up' : 'price-flash-down'
    prevPriceRef.current = item.current_price

    // Remove any existing flash class first
    el.classList.remove('price-flash-up', 'price-flash-down')
    // Force reflow to restart animation
    void el.offsetWidth
    el.classList.add(direction)

    if (flashTimerRef.current) clearTimeout(flashTimerRef.current)
    flashTimerRef.current = setTimeout(() => {
      el.classList.remove(direction)
    }, 500)
  }, [item.current_price])

  const changePositive = item.daily_change_pct >= 0

  return (
    <div
      data-testid="watchlist-item"
      className={`group flex items-center gap-2 px-3 py-2 cursor-pointer hover:bg-terminal-border transition-colors ${
        isSelected ? 'bg-terminal-border border-l-2 border-terminal-yellow' : ''
      }`}
      onClick={onSelect}
    >
      {/* Ticker */}
      <span className="text-terminal-text font-semibold text-sm w-14 shrink-0">
        {item.ticker}
      </span>

      {/* Price */}
      <span
        ref={priceRef}
        data-testid={`ticker-price-${item.ticker}`}
        className="text-terminal-text text-sm tabular-nums w-20 text-right"
      >
        {formatPrice(item.current_price)}
      </span>

      {/* Change % */}
      <span
        className="text-xs tabular-nums w-16 text-right"
        style={{ color: changePositive ? '#22c55e' : '#ef4444' }}
      >
        {formatChangePct(item.daily_change_pct)}
      </span>

      {/* Sparkline */}
      <div className="flex-1 flex justify-end">
        <Sparkline data={sparkData} width={60} height={24} />
      </div>

      {/* Remove button — visible on hover */}
      <button
        data-testid="watchlist-remove-button"
        className="opacity-0 group-hover:opacity-100 ml-1 text-terminal-muted hover:text-terminal-red text-xs px-1"
        onClick={e => {
          e.stopPropagation()
          onRemove()
        }}
        title={`Remove ${item.ticker}`}
      >
        X
      </button>
    </div>
  )
}

export default function WatchlistPanel({
  items,
  selectedTicker,
  onSelectTicker,
  onAddTicker,
  onRemoveTicker,
}: Props) {
  const [inputTicker, setInputTicker] = useState('')
  const [adding, setAdding] = useState(false)
  const [addError, setAddError] = useState<string | null>(null)
  const { state } = usePriceStore()

  const handleAdd = useCallback(async () => {
    const ticker = inputTicker.trim().toUpperCase()
    if (!ticker) return

    setAdding(true)
    setAddError(null)
    try {
      await onAddTicker(ticker)
      setInputTicker('')
    } catch (err) {
      setAddError(err instanceof Error ? err.message : 'Failed to add ticker')
    } finally {
      setAdding(false)
    }
  }, [inputTicker, onAddTicker])

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      if (e.key === 'Enter') handleAdd()
    },
    [handleAdd]
  )

  // Merge live prices into watchlist items
  const enrichedItems = items.map(item => {
    const live = state.prices[item.ticker]
    return live
      ? {
          ...item,
          current_price: live.price,
          daily_change_pct: live.session_open
            ? ((live.price - live.session_open) / live.session_open) * 100
            : item.daily_change_pct,
        }
      : item
  })

  return (
    <aside className="flex flex-col h-full bg-terminal-panel border-r border-terminal-border w-56 shrink-0">
      <div className="px-3 py-2 border-b border-terminal-border">
        <span className="text-terminal-muted text-xs uppercase tracking-widest">Watchlist</span>
      </div>

      <div className="flex-1 overflow-y-auto">
        {enrichedItems.length === 0 && (
          <p className="text-terminal-muted text-xs px-3 py-4">No tickers. Add one below.</p>
        )}
        {enrichedItems.map(item => (
          <WatchlistRow
            key={item.ticker}
            item={item}
            isSelected={selectedTicker === item.ticker}
            onSelect={() => onSelectTicker(item.ticker)}
            onRemove={() => onRemoveTicker(item.ticker)}
            sparkData={(state.history[item.ticker] ?? []).map(p => p.price)}
          />
        ))}
      </div>

      {/* Add ticker form */}
      <div className="px-3 py-2 border-t border-terminal-border">
        <div className="flex gap-1">
          <input
            data-testid="watchlist-add-input"
            className="flex-1 bg-terminal-bg border border-terminal-border text-terminal-text text-xs px-2 py-1 rounded focus:outline-none focus:border-terminal-blue uppercase placeholder-terminal-muted"
            placeholder="TICKER"
            value={inputTicker}
            onChange={e => setInputTicker(e.target.value.toUpperCase())}
            onKeyDown={handleKeyDown}
            disabled={adding}
            maxLength={8}
          />
          <button
            data-testid="watchlist-add-button"
            className="bg-terminal-blue text-white text-xs px-2 py-1 rounded hover:opacity-80 disabled:opacity-50"
            onClick={handleAdd}
            disabled={adding || !inputTicker.trim()}
          >
            {adding ? '...' : 'Add'}
          </button>
        </div>
        {addError && (
          <p className="text-terminal-red text-xs mt-1">{addError}</p>
        )}
      </div>
    </aside>
  )
}
