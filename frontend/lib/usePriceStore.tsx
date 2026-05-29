'use client'
import { createContext, useContext, useState, useCallback, ReactNode } from 'react'
import { PriceUpdate } from './types'

interface PriceRecord {
  time: number
  price: number
}

interface PriceState {
  prices: Record<string, PriceUpdate>
  // last 200 data points per ticker
  history: Record<string, PriceRecord[]>
}

interface PriceContextValue {
  state: PriceState
  onPrice: (update: PriceUpdate) => void
}

const PriceContext = createContext<PriceContextValue | null>(null)

export function PriceProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<PriceState>({ prices: {}, history: {} })

  const onPrice = useCallback((update: PriceUpdate) => {
    setState(prev => {
      const hist = prev.history[update.ticker] ?? []
      const newHist = [...hist, { time: Date.now(), price: update.price }].slice(-200)
      return {
        prices: { ...prev.prices, [update.ticker]: update },
        history: { ...prev.history, [update.ticker]: newHist },
      }
    })
  }, [])

  return (
    <PriceContext.Provider value={{ state, onPrice }}>
      {children}
    </PriceContext.Provider>
  )
}

export function usePriceStore(): PriceContextValue {
  const ctx = useContext(PriceContext)
  if (!ctx) throw new Error('usePriceStore must be used inside PriceProvider')
  return ctx
}
