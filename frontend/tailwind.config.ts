import type { Config } from 'tailwindcss'

const config: Config = {
  content: ['./app/**/*.{ts,tsx}', './components/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        terminal: {
          bg: '#0d1117',
          panel: '#1a1a2e',
          border: '#2d2d3a',
          yellow: '#ecad0a',
          blue: '#209dd7',
          purple: '#753991',
          green: '#22c55e',
          red: '#ef4444',
          muted: '#6b7280',
          text: '#e2e8f0',
        },
      },
    },
  },
  plugins: [],
}
export default config
