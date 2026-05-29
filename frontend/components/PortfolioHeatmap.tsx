'use client'

import { Position } from '@/lib/types'

interface Props {
  positions: Position[]
  width?: number
  height?: number
}

interface Rect {
  x: number
  y: number
  w: number
  h: number
  position: Position
}

// Slice-and-dice treemap layout — simpler and deterministic
function buildLayout(
  positions: Position[],
  x: number,
  y: number,
  w: number,
  h: number
): Rect[] {
  if (positions.length === 0) return []

  const totalValue = positions.reduce((s, p) => s + Math.abs(p.current_price * p.quantity), 0)
  if (totalValue === 0) return []

  const rects: Rect[] = []
  let remaining = positions.slice().sort(
    (a, b) => Math.abs(b.current_price * b.quantity) - Math.abs(a.current_price * a.quantity)
  )
  let cx = x, cy = y, cw = w, ch = h
  let remainingTotal = totalValue

  while (remaining.length > 0) {
    const pos = remaining[0]
    const posValue = Math.abs(pos.current_price * pos.quantity)
    const fraction = posValue / remainingTotal

    if (cw >= ch) {
      // Split horizontally
      const rw = cw * fraction
      rects.push({ x: cx, y: cy, w: rw, h: ch, position: pos })
      cx += rw
      cw -= rw
    } else {
      // Split vertically
      const rh = ch * fraction
      rects.push({ x: cx, y: cy, w: cw, h: rh, position: pos })
      cy += rh
      ch -= rh
    }

    remainingTotal -= posValue
    remaining = remaining.slice(1)
  }

  return rects
}

// Interpolate between red, gray, and green based on P&L %
function pnlColor(pct: number): string {
  // Clamp to [-10, 10] range for color mapping
  const clamped = Math.max(-10, Math.min(10, pct))
  if (clamped >= 0) {
    // gray → green
    const t = clamped / 10
    const r = Math.round(107 + (34 - 107) * t)
    const g = Math.round(114 + (197 - 114) * t)
    const b = Math.round(128 + (94 - 128) * t)
    return `rgb(${r},${g},${b})`
  } else {
    // red → gray
    const t = (clamped + 10) / 10
    const r = Math.round(239 + (107 - 239) * t)
    const g = Math.round(68 + (114 - 68) * t)
    const b = Math.round(68 + (128 - 68) * t)
    return `rgb(${r},${g},${b})`
  }
}

export default function PortfolioHeatmap({ positions, width = 400, height = 160 }: Props) {
  if (positions.length === 0) {
    return (
      <div
        data-testid="portfolio-heatmap"
        className="flex items-center justify-center bg-terminal-panel border border-terminal-border rounded text-terminal-muted text-xs"
        style={{ width, height }}
      >
        No positions
      </div>
    )
  }

  const rects = buildLayout(positions, 0, 0, width, height)

  return (
    <div data-testid="portfolio-heatmap" className="bg-terminal-panel border border-terminal-border rounded">
      <div className="px-3 py-1.5 border-b border-terminal-border text-xs text-terminal-muted">
        Portfolio Heatmap
      </div>
      <svg width={width} height={height} style={{ display: 'block' }}>
        {rects.map(({ x, y, w, h, position }) => {
          const color = pnlColor(position.unrealized_pnl_pct)
          const pctText =
            (position.unrealized_pnl_pct >= 0 ? '+' : '') +
            position.unrealized_pnl_pct.toFixed(2) +
            '%'
          const showLabel = w > 30 && h > 20

          return (
            <g key={position.ticker}>
              <rect
                x={x + 1}
                y={y + 1}
                width={Math.max(0, w - 2)}
                height={Math.max(0, h - 2)}
                fill={color}
                rx={2}
                opacity={0.85}
              />
              {showLabel && (
                <>
                  <text
                    x={x + w / 2}
                    y={y + h / 2 - 5}
                    textAnchor="middle"
                    fill="#e2e8f0"
                    fontSize={Math.min(12, w / 4)}
                    fontFamily="monospace"
                    fontWeight="bold"
                  >
                    {position.ticker}
                  </text>
                  <text
                    x={x + w / 2}
                    y={y + h / 2 + 8}
                    textAnchor="middle"
                    fill="#e2e8f0"
                    fontSize={Math.min(10, w / 5)}
                    fontFamily="monospace"
                  >
                    {pctText}
                  </text>
                </>
              )}
            </g>
          )
        })}
      </svg>
    </div>
  )
}
