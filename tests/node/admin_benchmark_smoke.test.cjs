const test = require('node:test')
const assert = require('node:assert/strict')

const benchmark = require('../../scripts/admin_benchmark_smoke.cjs')

test('buildSuite includes slow-page read-only benchmark endpoints', () => {
  const suite = benchmark.buildSuiteForTest({
    token: 'test-token',
    authInfo: {
      data: {
        user: {
          defaultAccountId: null
        }
      }
    },
    brokerAccounts: {
      data: [
        { id: 18, is_default: true }
      ]
    }
  })

  const ids = suite.map((item) => item.id)

  assert.deepEqual(ids.filter((id) => [
    'market-stock-pool',
    'market-insights',
    'market-insights-history',
    'market-history-compare',
    'market-backfill-status',
    'market-history-coverage',
    'market-history-coverage-symbol',
    'longbridge-quotes',
    'longbridge-depth',
    'longbridge-trades',
    'longbridge-snapshot',
    'symbol-overview',
    'finance-briefings',
    'notifications-all',
    'notifications-trade',
    'risk-overview',
    'orders-projection',
    'positions-snapshot',
    'positions-projection'
  ].includes(id)), [
    'market-stock-pool',
    'market-insights',
    'market-insights-history',
    'market-history-compare',
    'market-backfill-status',
    'market-history-coverage',
    'market-history-coverage-symbol',
    'longbridge-quotes',
    'longbridge-depth',
    'longbridge-trades',
    'longbridge-snapshot',
    'symbol-overview',
    'finance-briefings',
    'notifications-all',
    'notifications-trade',
    'risk-overview',
    'orders-projection',
    'positions-snapshot',
    'positions-projection'
  ])

  assert.equal(
    suite.some((item) => item.method !== 'GET' && ids.includes(item.id)),
    false
  )
})

test('buildSuite infers account-scoped endpoints from enveloped trade accounts response', () => {
  const suite = benchmark.buildSuiteForTest({
    token: 'test-token',
    authInfo: {
      data: {
        user: {}
      }
    },
    brokerAccounts: {
      success: true,
      data: [
        { id: 28, isDefault: true }
      ]
    }
  })

  const paths = suite.map((item) => item.path)
  assert.ok(paths.includes('/svc/trade/api/v1/trade/accounts/28/positions'))
  assert.ok(paths.includes('/svc/trade/api/v1/trade/accounts/28/snapshot/state'))
})

test('formatConsoleSummary prints p50 and p95 for successful endpoints', () => {
  const lines = benchmark.formatConsoleSummaryForTest({
    endpoints: [
      {
        id: 'market-stock-pool',
        label: 'Market Stock Pool',
        method: 'GET',
        path: '/svc/market/api/v1/market/stock-pool',
        okCount: 3,
        failCount: 0,
        p50Ms: 31.25,
        p95Ms: 55.5,
        statusCodes: [200],
        unavailable: false,
        lastError: ''
      }
    ]
  })

  assert.match(lines[0], /market-stock-pool/)
  assert.match(lines[0], /p50=31\.25ms/)
  assert.match(lines[0], /p95=55\.5ms/)
})

test('formatConsoleSummary marks failed endpoints clearly', () => {
  const lines = benchmark.formatConsoleSummaryForTest({
    endpoints: [
      {
        id: 'notifications-trade',
        label: 'Notifications Trade',
        method: 'GET',
        path: '/svc/risk/api/v1/notifications',
        okCount: 0,
        failCount: 2,
        p50Ms: null,
        p95Ms: null,
        statusCodes: [503],
        unavailable: false,
        lastError: 'service unavailable'
      }
    ]
  })

  assert.match(lines[0], /FAIL/)
  assert.match(lines[0], /notifications-trade/)
  assert.match(lines[0], /status=503/)
  assert.match(lines[0], /service unavailable/)
})
