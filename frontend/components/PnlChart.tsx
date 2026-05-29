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
import { SnapshotPoint } from '@/lib/types'

interface Props {
  data: SnapshotPoint[]
}

function toUTC(isoString: string): UTCTimestamp {
  return Math.floor(new Date(isoString).getTime() / 1000) as UTCTimestamp
}

export default function PnlChart({ data }: Props) {
  const containerRef = useRef<HTMLDivElement>(null)
  const chartRef = useRef<IChartApi | null>(null)
  const seriesRef = useRef<ISeriesApi<'Area'> | null>(null)

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
      rightPriceScale: { borderColor: '#2d2d3a' },
      timeScale: { borderColor: '#2d2d3a', timeVisible: true },
      handleScroll: true,
      handleScale: true,
    })
    chartRef.current = chart

    const series = chart.addAreaSeries({
      lineColor: '#753991',
      topColor: 'rgba(117, 57, 145, 0.3)',
      bottomColor: 'rgba(117, 57, 145, 0.0)',
      lineWidth: 2,
    })
    seriesRef.current = series

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

  useEffect(() => {
    const series = seriesRef.current
    if (!series || data.length === 0) return

    const seen = new Set<number>()
    const chartData: AreaData[] = data
      .map(p => ({ time: toUTC(p.recorded_at), value: p.total_value }))
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
    <div data-testid="pnl-chart" className="flex flex-col bg-terminal-panel rounded border border-terminal-border">
      <div className="px-3 py-1.5 border-b border-terminal-border text-xs text-terminal-muted">
        Portfolio Value
      </div>
      <div ref={containerRef} className="h-48 w-full" />
    </div>
  )
}
