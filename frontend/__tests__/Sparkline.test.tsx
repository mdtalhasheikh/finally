import { render } from '@testing-library/react'
import Sparkline from '@/components/Sparkline'

describe('Sparkline', () => {
  it('renders without crashing with empty data', () => {
    const { container } = render(<Sparkline data={[]} />)
    const svg = container.querySelector('svg')
    expect(svg).not.toBeNull()
  })

  it('renders an SVG polyline when data is provided', () => {
    const { container } = render(<Sparkline data={[10, 20, 15, 25, 30]} />)
    const polyline = container.querySelector('polyline')
    expect(polyline).not.toBeNull()
  })

  it('color is green when last value > first value', () => {
    const { container } = render(<Sparkline data={[10, 15, 20]} />)
    const polyline = container.querySelector('polyline')
    expect(polyline?.getAttribute('stroke')).toBe('#22c55e')
  })

  it('color is red when last value < first value', () => {
    const { container } = render(<Sparkline data={[20, 15, 10]} />)
    const polyline = container.querySelector('polyline')
    expect(polyline?.getAttribute('stroke')).toBe('#ef4444')
  })

  it('color is gray when all values are equal', () => {
    const { container } = render(<Sparkline data={[10, 10, 10]} />)
    const polyline = container.querySelector('polyline')
    expect(polyline?.getAttribute('stroke')).toBe('#6b7280')
  })

  it('renders single-point data without crashing', () => {
    const { container } = render(<Sparkline data={[42]} />)
    const svg = container.querySelector('svg')
    expect(svg).not.toBeNull()
  })

  it('respects explicit color prop', () => {
    const { container } = render(<Sparkline data={[5, 10]} color="#ff00ff" />)
    const polyline = container.querySelector('polyline')
    expect(polyline?.getAttribute('stroke')).toBe('#ff00ff')
  })
})
