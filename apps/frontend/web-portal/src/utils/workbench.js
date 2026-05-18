function normalizeRole(roleCode = '') {
  return String(roleCode || '').trim().toLowerCase()
}

function normalizeRouteName(value = '') {
  return String(value || '').trim()
}

function normalizeCapability(value = '') {
  return String(value || '').trim()
}

function buildVisibleRouteSet(menuRoutes = []) {
  return new Set(
    (Array.isArray(menuRoutes) ? menuRoutes : [])
      .map((item) => normalizeRouteName(item?.routeName || item))
      .filter(Boolean)
  )
}

function buildCapabilitySet(capabilities = [], access = {}) {
  const values = Array.isArray(capabilities) && capabilities.length
    ? capabilities
    : Array.isArray(access?.capabilities)
      ? access.capabilities
      : []

  return new Set(values.map((item) => normalizeCapability(item)).filter(Boolean))
}

function buildRouteAccess({ menuRoutes = [], capabilities = [], access = {}, roleCode = '' } = {}) {
  const normalizedRole = normalizeRole(roleCode)
  const visibleRoutes = buildVisibleRouteSet(menuRoutes)
  const visibleCapabilities = buildCapabilitySet(capabilities, access)

  const hasRoute = (routeName, fallback = false) => {
    const normalizedRoute = normalizeRouteName(routeName)
    if (visibleRoutes.size > 0) {
      return Boolean(normalizedRoute && visibleRoutes.has(normalizedRoute))
    }
    return Boolean(fallback)
  }

  return {
    normalizedRole,
    canTrade: hasRoute('Trading', Boolean(access.canUseQuantTrading || normalizedRole === 'admin' || normalizedRole === 'trader')),
    canManageRisk: hasRoute('RiskManagement', Boolean(access.canUseQuantTrading || visibleCapabilities.has('risk.manage') || normalizedRole === 'admin')),
    canViewAnalysis: hasRoute('AIAnalysis', visibleCapabilities.has('ai.analysis')),
    canViewSymbol: hasRoute('SymbolDetail', visibleCapabilities.has('market.detail.view') || hasRoute('MarketData')),
    canViewProfile: hasRoute('Profile', visibleCapabilities.has('profile.view')),
    canManageTasks: hasRoute('SchedulerCenter', Boolean(access.canManageTasks || visibleCapabilities.has('tasks.manage') || normalizedRole === 'admin')),
    canViewMarket: hasRoute('MarketData', visibleCapabilities.has('market.view') || true),
    canViewOrders: hasRoute('Orders', visibleCapabilities.has('orders.view')),
    canViewPositions: hasRoute('Positions', visibleCapabilities.has('positions.view')),
    canViewSettings: hasRoute('Settings', visibleCapabilities.has('settings.manage') || normalizedRole === 'admin')
  }
}

function buildActionLabel(target) {
  const routeName = normalizeRouteName(target?.name || '')
  const labelMap = {
    Trading: '进入交易台',
    RiskManagement: '查看风控',
    SchedulerCenter: '打开任务中心',
    Orders: '查看订单',
    Positions: '查看持仓',
    Profile: '绑定账户',
    Settings: '打开设置',
    MarketData: '进入市场',
    AIAnalysis: '继续研判',
    SymbolDetail: '查看详情'
  }
  return labelMap[routeName] || '继续处理'
}

function compareAlertPriority(left, right) {
  const levelWeight = {
    critical: 0,
    warning: 1,
    info: 2,
    healthy: 3
  }
  const leftWeight = levelWeight[String(left?.level || 'info').trim().toLowerCase()] ?? 99
  const rightWeight = levelWeight[String(right?.level || 'info').trim().toLowerCase()] ?? 99
  if (leftWeight !== rightWeight) {
    return leftWeight - rightWeight
  }
  return String(left?.title || '').localeCompare(String(right?.title || ''), 'zh-CN')
}

function resolveAlertTarget(serviceKey = '', routeAccess = {}) {
  const key = String(serviceKey || '').trim()
  if (key === 'trade_service') {
    if (routeAccess.canViewOrders) return { name: 'Orders' }
    if (routeAccess.canViewSettings) return { name: 'Settings' }
  }
  if (key === 'risk_service' && routeAccess.canManageRisk) {
    return { name: 'RiskManagement' }
  }
  if (routeAccess.canManageTasks) {
    return { name: 'SchedulerCenter' }
  }
  if (routeAccess.canViewProfile) {
    return { name: 'Profile' }
  }
  return { name: 'Dashboard' }
}

export function pickPrimaryFocus(recommendationItems = [], positions = []) {
  const recommendation = Array.isArray(recommendationItems)
    ? recommendationItems.find((item) => item?.symbol) || recommendationItems[0]
    : null
  if (recommendation?.symbol) {
    return {
      symbol: String(recommendation.symbol).trim().toUpperCase(),
      market: String(recommendation.market || '').trim().toUpperCase() || 'US',
      source: 'recommendation'
    }
  }

  const position = Array.isArray(positions)
    ? positions.find((item) => item?.symbol) || positions[0]
    : null
  if (position?.symbol) {
    const symbol = String(position.symbol).trim().toUpperCase()
    return {
      symbol,
      market: symbol.endsWith('.HK') ? 'HK' : symbol.endsWith('.SZ') || symbol.endsWith('.SH') ? 'CN' : 'US',
      source: 'position'
    }
  }

  return {
    symbol: 'AAPL.US',
    market: 'US',
    source: 'fallback'
  }
}

export function buildRoleWorkflowCards({
  roleCode = '',
  access = {},
  menuRoutes = [],
  capabilities = [],
  selectedAccountName = '',
  recommendationItems = [],
  positions = [],
  overallHealthLabel = '检测中'
} = {}) {
  const routeAccess = buildRouteAccess({ menuRoutes, capabilities, access, roleCode })
  const focus = pickPrimaryFocus(recommendationItems, positions)
  const accountLabel = selectedAccountName || '未绑定账户'
  const cards = []

  if (routeAccess.canTrade) {
    cards.push(
      {
        id: 'trade-execution',
        kicker: 'Trader',
        title: '交易执行',
        note: `${accountLabel} · ${focus.symbol}`,
        description: '带着账户上下文直接进入交易页，持续看到参考价、持仓和最近订单。',
        target: { name: 'Trading', query: { symbol: focus.symbol, action: 'buy' } }
      },
      routeAccess.canManageRisk ? {
        id: 'risk-check',
        kicker: 'Guardrail',
        title: '风控巡检',
        note: '持仓、保护单与通知联动',
        description: '先检查风险事件和保护单，再回到交易决策。',
        target: { name: 'RiskManagement' }
      } : null
    )
  }

  if (routeAccess.canViewAnalysis) {
    cards.push({
      id: 'market-analysis',
      kicker: 'Research',
      title: '市场 -> 研判',
      note: `${focus.symbol} · ${focus.source === 'recommendation' ? '推荐候选' : '持仓跟踪'}`,
      description: '从标的详情进入 AI 研判，保留当前 symbol / market 上下文，不再手工重复搜索。',
      target: { name: 'AIAnalysis', query: { symbol: focus.symbol, market: focus.market } }
    })
  }

  if (routeAccess.canViewSymbol) {
    cards.push({
      id: 'symbol-detail',
      kicker: 'Context',
      title: '标的详情',
      note: `${focus.market} 市场上下文`,
      description: '先看标的快照、报价和内容，再决定是否进入策略或交易动作。',
      target: { name: 'SymbolDetail', params: { symbol: focus.symbol } }
    })
  }

  if (routeAccess.canManageTasks) {
    cards.push({
      id: 'ops-center',
      kicker: 'Ops',
      title: '平台巡检',
      note: overallHealthLabel,
      description: '进入任务中心查看调度、失败重试和服务状态，适合管理员排障。',
      target: { name: 'SchedulerCenter' }
    })
  }

  return cards.filter(Boolean).slice(0, 4)
}

export function buildOperationalAlerts({
  systemHealth = {},
  menuRoutes = [],
  capabilities = [],
  access = {},
  roleCode = '',
  selectedAccountName = '',
  accountDataMeta = {},
  positionsDataMeta = {},
  recentTradeMeta = {}
} = {}) {
  const routeAccess = buildRouteAccess({ menuRoutes, capabilities, access, roleCode })
  const alerts = []
  const dedupe = new Set()
  const services = systemHealth?.services && typeof systemHealth.services === 'object'
    ? systemHealth.services
    : {}

  const pushAlert = (item) => {
    if (!item?.id) {
      return
    }
    if (dedupe.has(item.id)) {
      return
    }
    dedupe.add(item.id)
    alerts.push({
      ...item,
      actionLabel: item.actionLabel || buildActionLabel(item.target)
    })
  }

  const degradedServices = Object.values(services).filter((service) => ['degraded', 'unhealthy'].includes(String(service?.status || '').trim().toLowerCase()))
  if (degradedServices.length > 1 || (degradedServices.length === 1 && !Array.isArray(degradedServices[0]?.details?.alerts))) {
    pushAlert({
      id: 'service-health',
      level: degradedServices.some((service) => service?.status === 'unhealthy') ? 'critical' : 'warning',
      title: '服务巡检异常',
      detail: degradedServices.map((service) => service?.service || 'unknown').join(' / '),
      target: routeAccess.canManageTasks ? { name: 'SchedulerCenter' } : { name: 'Dashboard' }
    })
  }

  Object.entries(services).forEach(([key, service]) => {
    const serviceAlerts = Array.isArray(service?.details?.alerts) ? service.details.alerts : []
    serviceAlerts.forEach((item, index) => {
      const target = resolveAlertTarget(key, routeAccess)
      pushAlert({
        id: `${key}-${item.code || index}`,
        level: item.level || 'info',
        title: item.message || `${service?.service || key} 告警`,
        detail: item.action || service?.status_text || '',
        target
      })
    })
  })

  if (!selectedAccountName) {
    pushAlert({
      id: 'account-missing',
      level: 'warning',
      title: '尚未绑定交易账户',
      detail: '可以先查看市场与推荐，交易账户尚未接入。',
      target: routeAccess.canViewProfile ? { name: 'Profile' } : { name: 'Dashboard' }
    })
  }

  if (accountDataMeta?.warning) {
    pushAlert({
      id: 'account-fallback',
      level: 'warning',
      title: '账户摘要已回退',
      detail: String(accountDataMeta.warning),
      target: routeAccess.canViewProfile ? { name: 'Profile' } : { name: 'Dashboard' }
    })
  }

  if (selectedAccountName && !positionsDataMeta?.snapshotAt) {
    pushAlert({
      id: 'position-snapshot-missing',
      level: 'warning',
      title: '持仓快照未就绪',
      detail: `${selectedAccountName} 暂无持仓更新时间。`,
      target: routeAccess.canViewPositions ? { name: 'Positions' } : { name: 'Dashboard' }
    })
  }

  if (selectedAccountName && !recentTradeMeta?.snapshotAt) {
    pushAlert({
      id: 'order-projection-missing',
      level: 'info',
      title: '订单快照等待生成',
      detail: '最近订单暂无更新时间。',
      target: routeAccess.canViewOrders ? { name: 'Orders' } : { name: 'Dashboard' }
    })
  }

  if (!alerts.length) {
    pushAlert({
      id: 'all-clear',
      level: 'healthy',
      title: '当前无阻塞告警',
      detail: '服务、账户和订单状态正常。',
      target: { name: 'MarketData' }
    })
  }

  return alerts.sort(compareAlertPriority).slice(0, 6)
}
