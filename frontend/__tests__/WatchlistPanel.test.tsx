import { render, screen, fireEvent } from '@testing-library/react'
import WatchlistPanel from '@/components/WatchlistPanel'
import { WatchlistItem } from '@/lib/types'
import { PriceProvider } from '@/lib/usePriceStore'

jest.mock('@/lib/api', () => ({
  api: {
    getWatchlist: jest.fn().mockResolvedValue([]),
    addToWatchlist: jest.fn().mockResolvedValue({}),
    removeFromWatchlist: jest.fn().mockResolvedValue({}),
  },
}))

const makeItem = (ticker: string): WatchlistItem => ({
  ticker,
  current_price: 100,
  session_open: 98,
  daily_change_pct: 2.04,
  added_at: new Date().toISOString(),
})

const defaultProps = {
  items: [],
  selectedTicker: null,
  onSelectTicker: jest.fn(),
  onAddTicker: jest.fn().mockResolvedValue(undefined),
  onRemoveTicker: jest.fn().mockResolvedValue(undefined),
}

function renderWithProvider(ui: React.ReactElement) {
  return render(<PriceProvider>{ui}</PriceProvider>)
}

describe('WatchlistPanel', () => {
  it('renders empty state message when no items', () => {
    renderWithProvider(<WatchlistPanel {...defaultProps} />)
    expect(screen.getByText(/No tickers/)).not.toBeNull()
  })

  it('renders watchlist items', () => {
    const props = { ...defaultProps, items: [makeItem('AAPL'), makeItem('TSLA')] }
    renderWithProvider(<WatchlistPanel {...props} />)
    expect(screen.getByText('AAPL')).not.toBeNull()
    expect(screen.getByText('TSLA')).not.toBeNull()
  })

  it('calls onSelectTicker when a row is clicked', () => {
    const onSelect = jest.fn()
    const props = { ...defaultProps, items: [makeItem('AAPL')], onSelectTicker: onSelect }
    renderWithProvider(<WatchlistPanel {...props} />)
    fireEvent.click(screen.getByText('AAPL'))
    expect(onSelect).toHaveBeenCalledWith('AAPL')
  })

  it('has an add input and button', () => {
    renderWithProvider(<WatchlistPanel {...defaultProps} />)
    expect(screen.getByPlaceholderText('TICKER')).not.toBeNull()
    expect(screen.getByText('Add')).not.toBeNull()
  })

  it('uppercases input as typed', () => {
    renderWithProvider(<WatchlistPanel {...defaultProps} />)
    const input = screen.getByPlaceholderText('TICKER') as HTMLInputElement
    fireEvent.change(input, { target: { value: 'goog' } })
    expect(input.value).toBe('GOOG')
  })
})
