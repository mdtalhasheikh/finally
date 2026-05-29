'use client'

interface Props {
  data: number[]
  width?: number
  height?: number
  color?: string
}

// Normalize values to fit within the SVG viewport
function normalizePoints(data: number[], w: number, h: number): string {
  const min = Math.min(...data)
  const max = Math.max(...data)
  const range = max - min || 1

  return data
    .map((v, i) => {
      const x = (i / (data.length - 1)) * w
      const y = h - ((v - min) / range) * h
      return `${x.toFixed(1)},${y.toFixed(1)}`
    })
    .join(' ')
}

// Auto-color: green if trending up, red if trending down, gray if flat/empty
function autoColor(data: number[]): string {
  if (data.length < 2) return '#6b7280'
  const first = data[0]
  const last = data[data.length - 1]
  if (last > first) return '#22c55e'
  if (last < first) return '#ef4444'
  return '#6b7280'
}

export default function Sparkline({ data, width = 80, height = 30, color }: Props) {
  if (data.length === 0) {
    return <svg width={width} height={height} />
  }

  if (data.length === 1) {
    // Single point: draw a horizontal line at midpoint
    const mid = height / 2
    return (
      <svg width={width} height={height}>
        <line
          x1={0} y1={mid} x2={width} y2={mid}
          stroke={color ?? autoColor(data)}
          strokeWidth={1.5}
        />
      </svg>
    )
  }

  const resolvedColor = color ?? autoColor(data)
  const points = normalizePoints(data, width, height)

  return (
    <svg width={width} height={height} style={{ overflow: 'visible' }}>
      <polyline
        points={points}
        fill="none"
        stroke={resolvedColor}
        strokeWidth={1.5}
        strokeLinejoin="round"
        strokeLinecap="round"
      />
    </svg>
  )
}
