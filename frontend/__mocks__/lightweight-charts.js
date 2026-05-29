module.exports = {
  createChart: () => ({
    addAreaSeries: () => ({ setData: jest.fn(), update: jest.fn() }),
    addLineSeries: () => ({ setData: jest.fn(), update: jest.fn() }),
    timeScale: () => ({ fitContent: jest.fn() }),
    resize: jest.fn(),
    remove: jest.fn(),
  }),
}
