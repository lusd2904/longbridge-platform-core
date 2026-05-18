import { VIEW_REGISTRY, resolveRoleViewCodes, resolveViewDefinition } from './viewRegistry.js'

function normalizeCodeList(list = []) {
  return Array.isArray(list)
    ? list
      .map((item) => String(item || '').trim())
      .filter(Boolean)
    : []
}

function normalizeMenu(menu = {}, index = 0) {
  return {
    routeName: String(menu.routeName || '').trim(),
    path: String(menu.path || '').trim(),
    title: String(menu.title || '菜单').trim(),
    icon: menu.icon,
    group: menu.group,
    groupTitle: menu.groupTitle,
    subsystemTitle: menu.subsystemTitle,
    subsystemIcon: menu.subsystemIcon,
    subsystemRouteName: menu.subsystemRouteName,
    subsystemRoutePath: menu.subsystemRoutePath,
    subsystemCode: String(menu.subsystemCode || menu.subsystem || 'workspace').trim() || 'workspace',
    hidden: Boolean(menu.hidden),
    sortIndex: Number(menu.sortIndex ?? index)
  }
}

export function normalizeFeatureFlags(rawFlags = []) {
  if (!Array.isArray(rawFlags)) {
    return {}
  }

  return rawFlags.reduce((result, flag) => {
    const code = String(flag?.code || '').trim()
    if (!code) {
      return result
    }

    result[code] = {
      enabled: flag?.enabled !== false,
      roles: normalizeCodeList(flag?.roles),
      terminals: normalizeCodeList(flag?.terminals)
    }
    return result
  }, {})
}

export function isFeatureEnabled(flagMap = {}, flagCode = '', context = {}) {
  const normalizedCode = String(flagCode || '').trim()
  if (!normalizedCode) {
    return true
  }

  const flag = flagMap[normalizedCode]
  if (!flag) {
    return true
  }

  if (flag.enabled === false) {
    return false
  }

  const contextRoles = Array.from(new Set([
    String(context.roleCode || '').trim(),
    ...normalizeCodeList(context.roleCodes)
  ].filter(Boolean)))
  if (flag.roles.length && !flag.roles.some((role) => contextRoles.includes(role))) {
    return false
  }

  const terminal = String(context.terminal || '').trim()
  if (flag.terminals.length && !flag.terminals.includes(terminal)) {
    return false
  }

  return true
}

export function buildPlatformShellModel({
  session = {},
  activeViewCode = '',
  terminal = 'web'
} = {}) {
  const user = session?.user || {}
  const roleCode = String(user.roleCode || user.role || 'user').trim() || 'user'
  const extraRoles = normalizeCodeList(session?.access?.roles)
  const roleCodes = Array.from(new Set([roleCode, ...extraRoles]))
  const menus = (Array.isArray(session?.menus) ? session.menus : [])
    .map(normalizeMenu)
    .filter((item) => !item.hidden)
    .sort((a, b) => a.sortIndex - b.sortIndex)

  const flagMap = normalizeFeatureFlags(session?.featureFlags || [])
  const candidateViewCodes = Array.from(new Set(roleCodes.flatMap((code) => resolveRoleViewCodes(code))))

  const availableViews = candidateViewCodes
    .filter((viewCode) => isFeatureEnabled(flagMap, `view.${viewCode}`, { roleCode, roleCodes, terminal }))
    .map((viewCode) => resolveViewDefinition(viewCode))

  const fallbackViews = availableViews.length ? availableViews : [VIEW_REGISTRY.trading]
  const activeView = fallbackViews.find((item) => item.code === String(activeViewCode || '').trim()) || fallbackViews[0]
  const visibleMenus = menus.filter((item) => activeView.allowedSubsystems.includes(item.subsystemCode))

  return {
    roleCode,
    availableViews: fallbackViews,
    activeView,
    visibleMenus,
    flagMap
  }
}
