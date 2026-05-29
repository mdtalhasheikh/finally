import type { Metadata } from 'next'
import type { ReactNode } from 'react'
import './globals.css'
import { PriceProvider } from '@/lib/usePriceStore'

export const metadata: Metadata = {
  title: 'FinAlly — AI Trading Workstation',
  description: 'AI-powered trading terminal',
}

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en">
      <body>
        <PriceProvider>
          {children}
        </PriceProvider>
      </body>
    </html>
  )
}
