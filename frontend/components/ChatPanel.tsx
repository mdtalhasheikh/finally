'use client'

import { useState, useEffect, useRef, useCallback } from 'react'
import { v4 as uuidv4 } from 'uuid'
import { ChatMessage } from '@/lib/types'
import { api } from '@/lib/api'

interface TradeAction {
  ticker: string
  side: string
  quantity: number
  price: number
  status: string
  error?: string
}

interface WatchlistChange {
  ticker: string
  action: string
  status: string
}

function TradeCard({ trade }: { trade: TradeAction }) {
  const statusColor = trade.status === 'executed' ? '#22c55e' : '#ef4444'
  return (
    <div className="mt-1 px-2 py-1 bg-terminal-bg border border-terminal-border rounded text-xs">
      <span className="text-terminal-muted">{trade.side.toUpperCase()} </span>
      <span className="text-terminal-text font-semibold">{trade.quantity} {trade.ticker}</span>
      <span className="text-terminal-muted"> @ {trade.price.toFixed(2)}</span>
      <span className="ml-2" style={{ color: statusColor }}>{trade.status}</span>
      {trade.error && <span className="text-terminal-red ml-1">— {trade.error}</span>}
    </div>
  )
}

function WatchlistChangeCard({ change }: { change: WatchlistChange }) {
  const statusColor = change.status === 'ok' ? '#22c55e' : '#ef4444'
  return (
    <div className="mt-1 px-2 py-1 bg-terminal-bg border border-terminal-border rounded text-xs">
      <span className="text-terminal-muted">{change.action} </span>
      <span className="text-terminal-text font-semibold">{change.ticker}</span>
      <span className="ml-2" style={{ color: statusColor }}>{change.status}</span>
    </div>
  )
}

function MessageBubble({ msg }: { msg: ChatMessage }) {
  const isUser = msg.role === 'user'

  return (
    <div data-testid="chat-message" className={`flex ${isUser ? 'justify-end' : 'justify-start'} mb-2`}>
      <div
        className={`max-w-[85%] px-3 py-2 rounded text-xs ${
          isUser
            ? 'bg-terminal-border text-terminal-text'
            : 'bg-terminal-panel border border-terminal-border text-terminal-text'
        }`}
      >
        <p className="whitespace-pre-wrap leading-relaxed">{msg.content}</p>

        {msg.actions?.trades && msg.actions.trades.length > 0 && (
          <div className="mt-1">
            {msg.actions.trades.map((t, i) => (
              <TradeCard key={i} trade={t} />
            ))}
          </div>
        )}

        {msg.actions?.watchlist_changes && msg.actions.watchlist_changes.length > 0 && (
          <div className="mt-1">
            {msg.actions.watchlist_changes.map((c, i) => (
              <WatchlistChangeCard key={i} change={c} />
            ))}
          </div>
        )}
      </div>
    </div>
  )
}

export default function ChatPanel() {
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const [collapsed, setCollapsed] = useState(false)
  const bottomRef = useRef<HTMLDivElement>(null)

  // Load history on mount
  useEffect(() => {
    api.getChatHistory()
      .then(history => setMessages(history))
      .catch(() => {})
  }, [])

  // Scroll to bottom when messages change
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  const sendMessage = useCallback(async () => {
    const text = input.trim()
    if (!text || loading) return

    const userMsg: ChatMessage = {
      id: uuidv4(),
      role: 'user',
      content: text,
      created_at: new Date().toISOString(),
    }
    setMessages(prev => [...prev, userMsg])
    setInput('')
    setLoading(true)

    try {
      const response = await api.sendChatMessage(text)
      const assistantMsg: ChatMessage = {
        id: uuidv4(),
        role: 'assistant',
        content: response.message,
        actions: {
          trades: response.trades as TradeAction[],
          watchlist_changes: response.watchlist_changes as WatchlistChange[],
        },
        created_at: new Date().toISOString(),
      }
      setMessages(prev => [...prev, assistantMsg])
    } catch (err) {
      const errMsg: ChatMessage = {
        id: uuidv4(),
        role: 'assistant',
        content: err instanceof Error ? `Error: ${err.message}` : 'Something went wrong.',
        created_at: new Date().toISOString(),
      }
      setMessages(prev => [...prev, errMsg])
    } finally {
      setLoading(false)
    }
  }, [input, loading])

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault()
        sendMessage()
      }
    },
    [sendMessage]
  )

  return (
    <aside className="flex flex-col h-full bg-terminal-panel border-l border-terminal-border w-72 shrink-0">
      {/* Header */}
      <div className="flex items-center justify-between px-3 py-2 border-b border-terminal-border">
        <span className="text-terminal-muted text-xs uppercase tracking-widest">AI Assistant</span>
        <button
          className="text-terminal-muted hover:text-terminal-text text-xs"
          onClick={() => setCollapsed(v => !v)}
        >
          {collapsed ? '[+]' : '[-]'}
        </button>
      </div>

      {!collapsed && (
        <>
          {/* Message list */}
          <div className="flex-1 overflow-y-auto px-3 py-2">
            {messages.length === 0 && (
              <p className="text-terminal-muted text-xs">
                Ask me to buy/sell stocks, add tickers to your watchlist, or analyze your portfolio.
              </p>
            )}
            {messages.map(msg => (
              <MessageBubble key={msg.id} msg={msg} />
            ))}
            {loading && (
              <div className="flex justify-start mb-2">
                <div className="px-3 py-2 bg-terminal-panel border border-terminal-border rounded text-xs text-terminal-muted">
                  Thinking...
                </div>
              </div>
            )}
            <div ref={bottomRef} />
          </div>

          {/* Input area */}
          <div className="px-3 py-2 border-t border-terminal-border flex gap-2">
            <textarea
              className="flex-1 bg-terminal-bg border border-terminal-border text-terminal-text text-xs px-2 py-1.5 rounded resize-none focus:outline-none focus:border-terminal-purple placeholder-terminal-muted"
              placeholder="Ask something..."
              rows={2}
              value={input}
              onChange={e => setInput(e.target.value)}
              onKeyDown={handleKeyDown}
              disabled={loading}
              data-testid="chat-input"
            />
            <button
              className="px-3 py-1 rounded text-xs font-semibold text-white self-end disabled:opacity-50 hover:opacity-80"
              style={{ backgroundColor: '#753991' }}
              onClick={sendMessage}
              disabled={loading || !input.trim()}
              data-testid="chat-send-button"
            >
              Send
            </button>
          </div>
        </>
      )}
    </aside>
  )
}
