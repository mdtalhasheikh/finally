'use client'

import { useEffect, useRef } from 'react'
import {
  createChart,
  ColorType,
  UTCTimestamp,
  IChartApi,
  ISeriesApi,
  AreaData,
} from 'lightweight-charts'

interface PricePoint {
  time: number
  price: number
}

interface Props {
  ticker: string
  data: PricePoint[]
}

// Convert epoch ms to UTCTimestamp (seconds)
function toUTC(epochMs: number): UTCTimestamp {
  return Math.floor(epochMs / 1000) as UTCTimestamp
}

export default function MainChart({ ticker, data }: Props) {
  const containerRef = useRef<HTMLDivElement>(null)
  const chartRef = useRef<IChartApi | null>(null)
  const seriesRef = useRef<ISeriesApi<'Area'> | null>(null)

  // Create chart once on mount
  useEffect(() => {
    const container = containerRef.current
    if (!container) return

    const chart = createChart(container, {
      layout: {
        background: { type: ColorType.Solid, color: '#0d1117' },
        textColor: '#6b7280',
      },
      grid: {
        vertLines: { color: '#2d2d3a' },
        horzLines: { color: '#2d2d3a' },
      },
      crosshair: {
        vertLine: { color: '#6b7280', labelBackgroundColor: '#1a1a2e' },
        horzLine: { color: '#6b7280', labelBackgroundColor: '#1a1a2e' },
      },
      rightPriceScale: { borderColor: '#2d2d3a' },
      timeScale: { borderColor: '#2d2d3a', timeVisible: true },
      handleScroll: true,
      handleScale: true,
    })
    chartRef.current = chart

    const series = chart.addAreaSeries({
      lineColor: '#209dd7',
      topColor: 'rgba(32, 157, 215, 0.3)',
      bottomColor: 'rgba(32, 157, 215, 0.0)',
      lineWidth: 2,
    })
    seriesRef.current = series

    // Resize observer
    const observer = new ResizeObserver(() => {
      if (container) {
        chart.resize(container.clientWidth, container.clientHeight)
      }
    })
    observer.observe(container)

    return () => {
      observer.disconnect()
      chart.remove()
      chartRef.current = null
      seriesRef.current = null
    }
  }, [])

  // Update data when it changes
  useEffect(() => {
    const series = seriesRef.current
    if (!series || data.length === 0) return

    // Deduplicate by time and sort ascending
    const seen = new Set<number>()
    const chartData: AreaData[] = data
      .map(p => ({ time: toUTC(p.time), value: p.price }))
      .filter(p => {
        const t = p.time as number
        if (seen.has(t)) return false
        seen.add(t)
        return true
      })
      .sort((a, b) => (a.time as number) - (b.time as number))

    series.setData(chartData)
    chartRef.current?.timeScale().fitContent()
  }, [data])

  return (
    <div className="flex flex-col bg-terminal-panel rounded border border-terminal-border">
      <div className="px-3 py-1.5 border-b border-terminal-border text-xs text-terminal-muted flex items-center gap-2">
        <span className="text-terminal-text font-semibold">{ticker || 'Select a ticker'}</span>
        <span>— Price</span>
      </div>
      <div ref={containerRef} className="h-64 w-full" />
    </div>
  )
}
