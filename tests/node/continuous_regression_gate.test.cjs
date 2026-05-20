const test = require('node:test')
const assert = require('node:assert/strict')

const gate = require('../../scripts/continuous_regression_gate.cjs')

test('evaluateWebSmokeReport passes when required critical pages stay within thresholds', () => {
  const result = gate.evaluateWebSmokeReport({
    pages: [
      { name: 'market', ok: true, initialReadyDurationMs: 1200, durationMs: 2600 },
      { name: 'trading', ok: true, initialReadyDurationMs: 800, durationMs: 3100 },
      { name: 'scheduler-center', ok: true, initialReadyDurationMs: 900, durationMs: 1400 },
      { name: 'history-coverage', ok: true, initialReadyDurationMs: 700, durationMs: 1600 }
    ],
    errors: []
  })

  assert.equal(result.failures.length, 0)
  assert.equal(result.summaries.length, 4)
})

test('evaluateWebSmokeReport fails when a critical page result is missing', () => {
  const result = gate.evaluateWebSmokeReport({
    pages: [
      { name: 'market', ok: true, initialReadyDurationMs: 1200, durationMs: 2600 }
    ],
    errors: []
  })

  assert.match(result.failures.join('\n'), /web-smoke:trading: missing page result/)
  assert.match(result.failures.join('\n'), /web-smoke:scheduler-center: missing page result/)
  assert.match(result.failures.join('\n'), /web-smoke:history-coverage: missing page result/)
})

test('evaluateWebSmokeReport fails when a critical page exceeds the total threshold', () => {
  const result = gate.evaluateWebSmokeReport({
    pages: [
      { name: 'market', ok: true, initialReadyDurationMs: 1200, durationMs: 2600 },
      { name: 'trading', ok: true, initialReadyDurationMs: 800, durationMs: 24000 },
      { name: 'scheduler-center', ok: true, initialReadyDurationMs: 900, durationMs: 1400 },
      { name: 'history-coverage', ok: true, initialReadyDurationMs: 700, durationMs: 1600 }
    ],
    errors: []
  })

  assert.match(result.failures.join('\n'), /web-smoke:trading: total 24000ms > 20000ms/)
})

test('evaluateApiBenchmarkReport fails when a critical endpoint p95 exceeds threshold', () => {
  const result = gate.evaluateApiBenchmarkReport({
    endpoints: [
      { id: 'market-stock-pool', okCount: 3, failCount: 0, p95Ms: 200, statusCodes: [200] },
      { id: 'market-insights', okCount: 3, failCount: 0, p95Ms: 200, statusCodes: [200] },
      { id: 'market-history-compare', okCount: 3, failCount: 0, p95Ms: 200, statusCodes: [200] },
      { id: 'market-history-coverage', okCount: 3, failCount: 0, p95Ms: 25000, statusCodes: [200] },
      { id: 'risk-overview', okCount: 3, failCount: 0, p95Ms: 200, statusCodes: [200] },
      { id: 'orders-projection', okCount: 3, failCount: 0, p95Ms: 200, statusCodes: [200] },
      { id: 'positions-projection', okCount: 3, failCount: 0, p95Ms: 200, statusCodes: [200] }
    ]
  })

  assert.match(result.failures.join('\n'), /api-benchmark:market-history-coverage: p95 25000ms > 20000ms/)
})
