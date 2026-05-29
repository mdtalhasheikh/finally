import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import TradeBar from '@/components/TradeBar'

const mockExecuteTrade = jest.fn()

jest.mock('@/lib/api', () => ({
  api: {
    executeTrade: (...args: unknown[]) => mockExecuteTrade(...args),
  },
}))

// Mock uuid to return a predictable value
jest.mock('uuid', () => ({ v4: () => 'test-uuid-1234' }))

describe('TradeBar', () => {
  beforeEach(() => {
    mockExecuteTrade.mockReset()
  })

  it('renders ticker input', () => {
    render(<TradeBar />)
    expect(screen.getByTestId('trade-ticker')).not.toBeNull()
  })

  it('renders quantity input', () => {
    render(<TradeBar />)
    expect(screen.getByTestId('trade-quantity')).not.toBeNull()
  })

  it('renders Buy and Sell buttons', () => {
    render(<TradeBar />)
    expect(screen.getByTestId('trade-buy')).not.toBeNull()
    expect(screen.getByTestId('trade-sell')).not.toBeNull()
  })

  it('Buy button label is "Buy"', () => {
    render(<TradeBar />)
    expect(screen.getByTestId('trade-buy').textContent).toBe('Buy')
  })

  it('Sell button label is "Sell"', () => {
    render(<TradeBar />)
    expect(screen.getByTestId('trade-sell').textContent).toBe('Sell')
  })

  it('buttons are disabled while trade is in-flight', async () => {
    // Return a promise that never resolves during the test window
    mockExecuteTrade.mockReturnValue(new Promise(() => {}))

    render(<TradeBar defaultTicker="AAPL" />)

    const quantityInput = screen.getByTestId('trade-quantity')
    fireEvent.change(quantityInput, { target: { value: '5' } })

    const buyBtn = screen.getByTestId('trade-buy')
    fireEvent.click(buyBtn)

    await waitFor(() => {
      expect(screen.getByTestId('trade-buy')).toBeDisabled()
      expect(screen.getByTestId('trade-sell')).toBeDisabled()
    })
  })
})
