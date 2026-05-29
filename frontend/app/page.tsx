'use client'

import { useState, useEffect, useCallback } from 'react'
import { Portfolio, WatchlistItem, SnapshotPoint } from '@/lib/types'
import { api } from '@/lib/api'
import { useSSE } from '@/lib/useSSE'
import { usePriceStore } from '@/lib/usePriceStore'

import Header from '@/components/Header'
import WatchlistPanel from '@/components/WatchlistPanel'
import MainChart from '@/components/MainChart'
import PortfolioHeatmap from '@/components/PortfolioHeatmap'
import PnlChart from '@/components/PnlChart'
import PositionsTable from '@/components/PositionsTable'
import TradeBar from '@/components/TradeBar'
import ChatPanel from '@/components/ChatPanel'

export default function TradingTerminal() {
  const [portfolio, setPortfolio] = useState<Portfolio | null>(null)
  const [watchlist, setWatchlist] = useState<WatchlistItem[]>([])
  const [history, setHistory] = useState<SnapshotPoint[]>([])
  const [selectedTicker, setSelectedTicker] = useState<string | null>(null)

  const { state: priceState, onPrice } = usePriceStore()
  const sseStatus = useSSE(onPrice)

  // Initial data load
  const loadPortfolio = useCallback(async () => {
    try {
      const data = await api.getPortfolio()
      setPortfolio(data)
    } catch {}
  }, [])

  const loadWatchlist = useCallback(async () => {
    try {
      const data = await api.getWatchlist()
      setWatchlist(data)
    } catch {}
  }, [])

  const loadHistory = useCallback(async () => {
    try {
      const data = await api.getPortfolioHistory(500)
      setHistory(data)
    } catch {}
  }, [])

  useEffect(() => {
    loadPortfolio()
    loadWatchlist()
    loadHistory()
  }, [loadPortfolio, loadWatchlist, loadHistory])

  // Refresh portfolio on trade execution
  const handleTradeExecuted = useCallback(async () => {
    await loadPortfolio()
    await loadHistory()
  }, [loadPortfolio, loadHistory])

  // Add/remove watchlist
  const handleAddTicker = useCallback(async (ticker: string) => {
    await api.addToWatchlist(ticker)
    await loadWatchlist()
  }, [loadWatchlist])

  const handleRemoveTicker = useCallback(async (ticker: string) => {
    await api.removeFromWatchlist(ticker)
    setWatchlist(prev => prev.filter(w => w.ticker !== ticker))
    if (selectedTicker === ticker) setSelectedTicker(null)
  }, [selectedTicker])

  // Chart data for selected ticker
  const chartData = selectedTicker
    ? (priceState.history[selectedTicker] ?? [])
    : []

  // Merge live prices into portfolio positions for the heatmap
  const livePositions = portfolio?.positions.map(pos => {
    const live = priceState.prices[pos.ticker]
    if (!live) return pos
    const currentPrice = live.price
    const unrealizedPnl = (currentPrice - pos.avg_cost) * pos.quantity
    const unrealizedPnlPct = ((currentPrice - pos.avg_cost) / pos.avg_cost) * 100
    const dailyChangePct = pos.session_open
      ? ((currentPrice - pos.session_open) / pos.session_open) * 100
      : pos.daily_change_pct
    return { ...pos, current_price: currentPrice, unrealized_pnl: unrealizedPnl, unrealized_pnl_pct: unrealizedPnlPct, daily_change_pct: dailyChangePct }
  }) ?? []

  // Live-updated total value for header
  const livePortfolio = portfolio
    ? {
        ...portfolio,
        positions: livePositions,
        total_unrealized_pnl: livePositions.reduce((s, p) => s + p.unrealized_pnl, 0),
        total_value:
          portfolio.cash_balance +
          livePositions.reduce((s, p) => s + p.current_price * p.quantity, 0),
      }
    : null

  return (
    <div className="flex flex-col h-screen overflow-hidden bg-terminal-bg">
      {/* Top bar */}
      <Header portfolio={livePortfolio} sseStatus={sseStatus} />

      {/* Main 3-column layout */}
      <div className="flex flex-1 overflow-hidden">
        {/* Left: Watchlist */}
        <WatchlistPanel
          items={watchlist}
          selectedTicker={selectedTicker}
          onSelectTicker={setSelectedTicker}
          onAddTicker={handleAddTicker}
          onRemoveTicker={handleRemoveTicker}
        />

        {/* Center: Charts + table + trade bar */}
        <main className="flex flex-col flex-1 overflow-hidden">
          <div className="flex-1 overflow-y-auto p-3 flex flex-col gap-3">
            {/* Price chart */}
            <MainChart
              ticker={selectedTicker ?? ''}
              data={chartData}
            />

            {/* Heatmap + PnL side-by-side when there's space */}
            <div className="flex gap-3">
              <div className="flex-1">
                <PortfolioHeatmap positions={livePositions} width={400} height={160} />
              </div>
              <div className="flex-1">
                <PnlChart data={history} />
              </div>
            </div>

            {/* Positions table */}
            <PositionsTable positions={livePositions} />
          </div>

          {/* Trade bar pinned to bottom of center column */}
          <TradeBar
            defaultTicker={selectedTicker ?? ''}
            onTradeExecuted={handleTradeExecuted}
          />
        </main>

        {/* Right: Chat */}
        <ChatPanel />
      </div>
    </div>
  )
}
