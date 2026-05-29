'use client'

import { Portfolio } from '@/lib/types'
import ConnectionStatus from './ConnectionStatus'

type SSEStatus = 'connecting' | 'connected' | 'disconnected'

interface Props {
  portfolio: Portfolio | null
  sseStatus: SSEStatus
}

function formatUsd(value: number): string {
  return value.toLocaleString('en-US', { style: 'currency', currency: 'USD', minimumFractionDigits: 2 })
}

export default function Header({ portfolio, sseStatus }: Props) {
  const totalValue = portfolio?.total_value ?? 0
  const cashBalance = portfolio?.cash_balance ?? 0
  const totalPnl = portfolio?.total_unrealized_pnl ?? 0
  const pnlPositive = totalPnl >= 0

  return (
    <header className="flex items-center justify-between px-4 py-2 border-b border-terminal-border bg-terminal-panel shrink-0">
      <div className="flex items-center gap-4">
        <span className="text-terminal-yellow font-bold text-lg tracking-widest">
          FinAlly
        </span>
        <span className="text-terminal-muted text-xs">AI Trading Workstation</span>
      </div>

      <div className="flex items-center gap-6 text-sm">
        <div className="flex items-center gap-1.5">
          <span className="text-terminal-muted text-xs">Portfolio</span>
          <span className="text-terminal-text font-semibold text-base tabular-nums">
            {formatUsd(totalValue)}
          </span>
        </div>

        <div className="flex items-center gap-1.5">
          <span className="text-terminal-muted text-xs">P&amp;L</span>
          <span
            className="font-semibold tabular-nums"
            style={{ color: pnlPositive ? '#22c55e' : '#ef4444' }}
          >
            {pnlPositive ? '+' : ''}{formatUsd(totalPnl)}
          </span>
        </div>

        <div className="flex items-center gap-1.5">
          <span className="text-terminal-muted text-xs">Cash</span>
          <span data-testid="cash-balance" className="text-terminal-text tabular-nums">
            {formatUsd(cashBalance)}
          </span>
        </div>

        <ConnectionStatus status={sseStatus} />
      </div>
    </header>
  )
}
