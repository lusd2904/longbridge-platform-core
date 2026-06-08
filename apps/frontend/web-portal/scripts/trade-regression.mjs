import { createRequire } from 'node:module'

const require = createRequire(import.meta.url)
const { resolveBaseUrl } = require('../../../../scripts/base_url_helper.cjs')

const BASE = resolveBaseUrl('TRADE_REGRESSION_BASE')
const USERNAME = process.env.TRADE_REGRESSION_USERNAME || process.env.API_TEST_USERNAME || 'admin'
const PASSWORD = process.env.TRADE_REGRESSION_PASSWORD || process.env.API_TEST_PASSWORD || 'admin123'
const SYMBOL = process.env.TRADE_REGRESSION_SYMBOL || 'AAPL.US'
const ALLOW_ORDER_SUBMIT = process.env.TRADE_REGRESSION_ALLOW_ORDER_SUBMIT === '1'

async function request(path, { method = 'GET', token = '', body } = {}) {
  const response = await fetch(`${BASE}${path}`, {
    method,
    headers: {
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...(body ? { 'Content-Type': 'application/json' } : {})
    },
    body: body ? JSON.stringify(body) : undefined
  })

  const contentType = response.headers.get('content-type') || ''
  const payload = contentType.includes('application/json')
    ? await response.json()
    : await response.text()

  return { status: response.status, payload }
}

function assert(condition, message) {
  if (!condition) {
    throw new Error(message)
  }
}

async function main() {
  const login = await request('/svc/user/api/v1/auth/login', {
    method: 'POST',
    body: { username: USERNAME, password: PASSWORD }
  })
  assert(login.status === 200, `登录失败: ${login.status}`)

  const token = login.payload?.data?.token || ''
  assert(token, '未获取到登录令牌')

  const presetAccountId = Number(process.env.TRADE_REGRESSION_ACCOUNT_ID || 0)
  let accountId = presetAccountId
  let selectedAccount = null

  const accounts = await request('/svc/trade/api/v1/trade/accounts', { token })
  assert(accounts.status === 200, `获取账户失败: ${accounts.status}；可通过 TRADE_REGRESSION_ACCOUNT_ID 指定账户`)
  const accountRows = Array.isArray(accounts.payload?.data) ? accounts.payload.data : Array.isArray(accounts.payload) ? accounts.payload : []

  if (!accountId) {
    accountId = Number(accountRows[0]?.id || 0)
  }
  selectedAccount = accountRows.find((item) => Number(item?.id || 0) === accountId) || accountRows[0] || null

  assert(accountId > 0, '没有可用交易账户用于回归测试')

  const health = await request('/svc/trade/health', { token })
  assert(health.status === 200, `健康检查失败: ${health.status}`)
  assert(health.payload?.longbridge, 'trade-service /health 未暴露 longbridge 观测信息')

  const projection = await request(`/svc/trade/api/v1/trade/orders/projection?account_id=${accountId}&limit=5`, { token })
  assert(projection.status === 200, `订单投影检查失败: ${projection.status}`)

  const outboxEvents = await request('/svc/trade/api/v1/trade/outbox/events?limit=5&include_payload=false', { token })
  assert(outboxEvents.status === 200, `交易 outbox events 检查失败: ${outboxEvents.status}`)

  if (!ALLOW_ORDER_SUBMIT) {
    const report = {
      generatedAt: new Date().toISOString(),
      base: BASE,
      symbol: SYMBOL,
      accountId,
      accountSafety: selectedAccount
        ? {
            tradingMode: selectedAccount.tradingMode || selectedAccount.trading_mode || '',
            isPaper: Boolean(selectedAccount.isPaper || selectedAccount.is_paper)
          }
        : null,
      health: {
        status: health.payload?.status,
        longbridge: health.payload?.longbridge
      },
      projection: {
        status: projection.status,
        count: Array.isArray(projection.payload?.data?.list) ? projection.payload.data.list.length : 0
      },
      outboxEvents: {
        status: outboxEvents.status
      },
      submit: {
        status: 'skipped',
        reason: 'set TRADE_REGRESSION_ALLOW_ORDER_SUBMIT=1 to run the explicit order-submit drill'
      }
    }

    console.log(JSON.stringify(report, null, 2))
    return
  }

  assert(selectedAccount?.isPaper || selectedAccount?.is_paper, '显式下单演练只允许模拟账户')

  const submit = await request('/svc/trade/api/v1/trade/orders/submit', {
    method: 'POST',
    token,
    body: {
      symbol: SYMBOL,
      action: 'BUY',
      quantity: 1,
      account_id: accountId,
      price: null,
      order_type: 'MARKET',
      time_in_force: 'DAY'
    }
  })

  assert(submit.status !== 502, `下单仍返回 502: ${JSON.stringify(submit.payload)}`)

  const report = {
    generatedAt: new Date().toISOString(),
    base: BASE,
    symbol: SYMBOL,
    accountId,
    health: {
      status: health.payload?.status,
      longbridge: health.payload?.longbridge
    },
    submit: {
      status: submit.status,
      payload: submit.payload
    }
  }

  console.log(JSON.stringify(report, null, 2))
}

main().catch((error) => {
  console.error(error?.stack || error?.message || String(error))
  process.exit(1)
})
