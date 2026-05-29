'use client'

import { Position } from '@/lib/types'

interface Props {
  positions: Position[]
}

function fmt2(n: number): string {
  return n.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function fmtPnl(n: number): string {
  return (n >= 0 ? '+' : '') + fmt2(n)
}

function fmtPct(n: number): string {
  return (n >= 0 ? '+' : '') + n.toFixed(2) + '%'
}

const HEADERS = ['Ticker', 'Qty', 'Avg Cost', 'Price', 'P&L', '% Change']

export default function PositionsTable({ positions }: Props) {
  if (positions.length === 0) {
    return (
      <div data-testid="positions-table" className="bg-terminal-panel border border-terminal-border rounded p-4">
        <p className="text-terminal-muted text-xs">No positions yet</p>
      </div>
    )
  }

  return (
    <div data-testid="positions-table" className="bg-terminal-panel border border-terminal-border rounded overflow-x-auto">
      <div className="px-3 py-1.5 border-b border-terminal-border text-xs text-terminal-muted">
        Open Positions
      </div>
      <table className="w-full text-xs tabular-nums">
        <thead>
          <tr className="border-b border-terminal-border">
            {HEADERS.map(h => (
              <th
                key={h}
                className="px-3 py-1.5 text-left text-terminal-muted font-normal uppercase tracking-wide"
              >
                {h}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {positions.map(pos => {
            const pnlPositive = pos.unrealized_pnl >= 0
            const pnlColor = pnlPositive ? '#22c55e' : '#ef4444'

            return (
              <tr
                key={pos.ticker}
                className="border-b border-terminal-border last:border-0 hover:bg-terminal-border transition-colors"
              >
                <td className="px-3 py-1.5 text-terminal-text font-semibold">{pos.ticker}</td>
                <td className="px-3 py-1.5 text-terminal-text">{pos.quantity}</td>
                <td className="px-3 py-1.5 text-terminal-text">{fmt2(pos.avg_cost)}</td>
                <td className="px-3 py-1.5 text-terminal-text">{fmt2(pos.current_price)}</td>
                <td className="px-3 py-1.5" style={{ color: pnlColor }}>
                  {fmtPnl(pos.unrealized_pnl)}
                </td>
                <td className="px-3 py-1.5" style={{ color: pnlColor }}>
                  {fmtPct(pos.unrealized_pnl_pct)}
                </td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}
