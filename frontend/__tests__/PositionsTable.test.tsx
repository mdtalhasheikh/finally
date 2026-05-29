import { render, screen } from '@testing-library/react'
import PositionsTable from '@/components/PositionsTable'
import { Position } from '@/lib/types'

const makePosition = (overrides: Partial<Position> = {}): Position => ({
  ticker: 'AAPL',
  quantity: 10,
  avg_cost: 150,
  current_price: 160,
  session_open: 155,
  daily_change_pct: 3.23,
  unrealized_pnl: 100,
  unrealized_pnl_pct: 6.67,
  ...overrides,
})

describe('PositionsTable', () => {
  it('renders "No positions yet" when positions array is empty', () => {
    render(<PositionsTable positions={[]} />)
    expect(screen.getByText('No positions yet')).not.toBeNull()
  })

  it('renders the correct number of rows', () => {
    const positions = [
      makePosition({ ticker: 'AAPL' }),
      makePosition({ ticker: 'TSLA' }),
      makePosition({ ticker: 'MSFT' }),
    ]
    render(<PositionsTable positions={positions} />)
    expect(screen.getByText('AAPL')).not.toBeNull()
    expect(screen.getByText('TSLA')).not.toBeNull()
    expect(screen.getByText('MSFT')).not.toBeNull()
  })

  it('renders positive P&L cells in green', () => {
    const positions = [makePosition({ unrealized_pnl: 100, unrealized_pnl_pct: 5 })]
    const { container } = render(<PositionsTable positions={positions} />)
    const greenCells = container.querySelectorAll('td[style*="22c55e"]')
    expect(greenCells.length).toBeGreaterThan(0)
  })

  it('renders negative P&L cells in red', () => {
    const positions = [makePosition({ unrealized_pnl: -50, unrealized_pnl_pct: -3.33 })]
    const { container } = render(<PositionsTable positions={positions} />)
    const redCells = container.querySelectorAll('td[style*="ef4444"]')
    expect(redCells.length).toBeGreaterThan(0)
  })

  it('formats positive P&L with leading + sign', () => {
    const positions = [makePosition({ unrealized_pnl: 100, unrealized_pnl_pct: 6.67 })]
    render(<PositionsTable positions={positions} />)
    expect(screen.getByText('+100.00')).not.toBeNull()
  })
})
