'use client'
import { useEffect, useRef, useState } from 'react'
import { PriceUpdate } from './types'

type SSEStatus = 'connecting' | 'connected' | 'disconnected'

export function useSSE(onPrice: (update: PriceUpdate) => void): SSEStatus {
  const [status, setStatus] = useState<SSEStatus>('connecting')
  const esRef = useRef<EventSource | null>(null)
  const onPriceRef = useRef(onPrice)
  onPriceRef.current = onPrice

  useEffect(() => {
    let retries = 0
    const maxRetries = 5
    let timeoutId: ReturnType<typeof setTimeout> | null = null

    const connect = () => {
      const es = new EventSource('/api/stream/prices')
      esRef.current = es

      es.onopen = () => {
        setStatus('connected')
        retries = 0
      }

      es.onmessage = (e: MessageEvent) => {
        try {
          onPriceRef.current(JSON.parse(e.data as string) as PriceUpdate)
        } catch {
          // malformed message — ignore
        }
      }

      es.onerror = () => {
        es.close()
        if (retries < maxRetries) {
          setStatus('connecting')
          retries++
          timeoutId = setTimeout(connect, Math.min(1000 * retries, 10000))
        } else {
          setStatus('disconnected')
        }
      }
    }

    connect()

    return () => {
      if (timeoutId) clearTimeout(timeoutId)
      esRef.current?.close()
    }
  }, [])

  return status
}
