import { render, screen } from '@testing-library/react'
import ChatPanel from '@/components/ChatPanel'

jest.mock('@/lib/api', () => ({
  api: {
    getChatHistory: jest.fn().mockResolvedValue([]),
    sendChatMessage: jest.fn().mockResolvedValue({
      message: 'Hello!',
      trades: [],
      watchlist_changes: [],
    }),
  },
}))

describe('ChatPanel', () => {
  it('renders the chat textarea input', () => {
    render(<ChatPanel />)
    expect(screen.getByTestId('chat-input')).not.toBeNull()
  })

  it('renders the Send button', () => {
    render(<ChatPanel />)
    expect(screen.getByTestId('chat-send')).not.toBeNull()
  })

  it('Send button is labeled "Send"', () => {
    render(<ChatPanel />)
    const btn = screen.getByTestId('chat-send')
    expect(btn.textContent).toBe('Send')
  })

  it('renders the AI Assistant label', () => {
    render(<ChatPanel />)
    expect(screen.getByText(/AI Assistant/i)).not.toBeNull()
  })
})
