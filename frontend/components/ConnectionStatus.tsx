'use client'

type Status = 'connecting' | 'connected' | 'disconnected'

interface Props {
  status: Status
}

const STATUS_CONFIG: Record<Status, { color: string; label: string }> = {
  connected:    { color: '#22c55e', label: 'Live' },
  connecting:   { color: '#ecad0a', label: 'Connecting' },
  disconnected: { color: '#ef4444', label: 'Disconnected' },
}

export default function ConnectionStatus({ status }: Props) {
  const { color, label } = STATUS_CONFIG[status]

  return (
    <span data-testid="connection-status" data-status={status} className="flex items-center gap-1.5 text-xs text-terminal-muted">
      <span
        className="inline-block w-2 h-2 rounded-full"
        style={{ backgroundColor: color }}
      />
      {label}
    </span>
  )
}
