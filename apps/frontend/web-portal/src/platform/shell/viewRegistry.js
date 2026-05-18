export const VIEW_REGISTRY = {
  trading: {
    code: 'trading',
    title: '交易',
    homeRouteName: 'Trading',
    allowedSubsystems: ['workspace', 'trading', 'market']
  },
  research: {
    code: 'research',
    title: '研究',
    homeRouteName: 'AIAnalysis',
    allowedSubsystems: ['workspace', 'market', 'analysis']
  },
  management: {
    code: 'management',
    title: '系统',
    homeRouteName: 'Settings',
    allowedSubsystems: ['workspace', 'platform']
  },
  composite: {
    code: 'composite',
    title: '全部',
    homeRouteName: 'Dashboard',
    allowedSubsystems: ['workspace', 'market', 'trading', 'analysis', 'platform']
  }
}

const ROLE_VIEW_MAP = {
  admin: ['composite', 'management'],
  trader: ['trading', 'composite'],
  analyst: ['research', 'composite'],
  viewer: ['research'],
  user: ['trading']
}

export function resolveRoleViewCodes(roleCode = '') {
  const normalizedRole = String(roleCode || '').trim()
  return ROLE_VIEW_MAP[normalizedRole] || ['trading']
}

export function resolveViewDefinition(viewCode = '') {
  const normalizedViewCode = String(viewCode || '').trim()
  return VIEW_REGISTRY[normalizedViewCode] || VIEW_REGISTRY.trading
}
