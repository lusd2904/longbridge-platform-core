import { getTokenLocal, setTokenLocal, clearAuthLocal } from './authPure.js';
import { loginPure } from './api.js';
import { buildPlatformShellModel } from '../platform/shell/platformShellModel.js';
const SESSION_KEY = 'platform_bootstrap';
const ACTIVE_SUBSYSTEM_KEY = 'platform_active_subsystem';
const ACTIVE_VIEW_KEY = 'platform_active_view';
const WORKBENCH_TABS_KEY = 'workbench_tabs';
const DEFAULT_SUBSYSTEM_CODE = 'workspace';
const SUBSYSTEM_TITLE_MAP = {
  workspace: '仪表盘',
  trading: '交易中心',
  market: '市场中心',
  analysis: '策略研究',
  platform: '系统管理'
};
const MENU_TITLE_MAP = {
  Trading: '交易台',
  AIAnalysis: 'AI研判',
  Backtest: '策略回测',
  MarketData: '实时行情',
  FinanceNews: '财经快讯',
  BrokerManagement: '券商连接',
  Settings: '系统设置中心'
};
const login = (d) => loginPure(d);
const logout = () => clearAuth();
export {
  getTokenLocal as getToken,
  setTokenLocal as setToken,
  isAdmin,
  isLoggedIn,
  login,
  getSession,
  setSession,
  clearAuth,
  logout,
  getCurrentUser,
  getAccess,
  getMenus,
  getSubsystems,
  getPreferredSubsystem,
  getActiveSubsystem,
  setActiveSubsystem,
  findSubsystemByRoute,
  getMenusBySubsystem,
  getViews,
  getPreferredView,
  getActiveView,
  setActiveView,
  getMenusByView,
  hasCapability
};

function decodeJwtPayload(token) {
  try {
    const parts = token.split('.');
    if (parts.length !== 3) return null;
    const base64 = parts[1].replace(/-/g, '+').replace(/_/g, '/');
    const padded = base64.padEnd(Math.ceil(base64.length / 4) * 4, '=');
    const decoded = atob(padded);
    return JSON.parse(decoded);
  } catch {
    return null;
  }
}

// Simple admin check based on token payload (if JWT) or a hardcoded flag.
function isLoggedIn() {
  return !!getTokenLocal();
}

function isAdmin() {
  const user = getCurrentUser();
  if (user?.role === 'admin' || user?.roleCode === 'admin') {
    return true;
  }

  const token = getTokenLocal();
  if (!token) return false;
  const payload = decodeJwtPayload(token);
  return payload?.role === 'admin' || payload?.isAdmin === true;
}

function getSession() {
  try {
    const raw = localStorage.getItem(SESSION_KEY);
    return raw ? JSON.parse(raw) : null;
  } catch {
    return null;
  }
}

function setSession(payload = {}) {
  const nextPayload = payload || {};
  localStorage.setItem(SESSION_KEY, JSON.stringify(nextPayload));
  if (typeof window !== 'undefined') {
    window.dispatchEvent(new CustomEvent('platform-session-updated'));
  }
}

function clearAuth() {
  clearAuthLocal();
  localStorage.removeItem(SESSION_KEY);
  localStorage.removeItem(ACTIVE_SUBSYSTEM_KEY);
  localStorage.removeItem(ACTIVE_VIEW_KEY);
  localStorage.removeItem(WORKBENCH_TABS_KEY);
  localStorage.removeItem('user');
  if (typeof window !== 'undefined') {
    window.dispatchEvent(new CustomEvent('platform-session-updated'));
  }
}

function readActiveSubsystemStorage() {
  if (typeof window === 'undefined') {
    return '';
  }
  return String(localStorage.getItem(ACTIVE_SUBSYSTEM_KEY) || '').trim();
}

function getCurrentUser() {
  const session = getSession();
  if (session?.user) {
    return session.user;
  }

  try {
    const raw = localStorage.getItem('user');
    return raw ? JSON.parse(raw) : null;
  } catch {
    return null;
  }
}

function getAccess() {
  return getSession()?.access || {};
}

function getMenus() {
  const session = getSession();
  const rawMenus = Array.isArray(session?.menus) ? session.menus : [];
  return rawMenus.map((menu) => {
    const routeName = String(menu?.routeName || '').trim();
    const subsystemCode = String(menu?.subsystemCode || DEFAULT_SUBSYSTEM_CODE).trim() || DEFAULT_SUBSYSTEM_CODE;
    return {
      ...menu,
      title: MENU_TITLE_MAP[routeName] || menu?.title || '',
      subsystemTitle: SUBSYSTEM_TITLE_MAP[subsystemCode] || menu?.subsystemTitle || ''
    };
  });
}

function getSubsystems() {
  const session = getSession();
  const rawSubsystems = Array.isArray(session?.subsystems) ? session.subsystems : [];
  if (rawSubsystems.length) {
    return rawSubsystems.map((item) => ({
      ...item,
      title: SUBSYSTEM_TITLE_MAP[String(item?.code || '').trim()] || item?.title || ''
    }));
  }

  const menus = getMenus();
  const deduped = new Map();
  menus.forEach((menu, index) => {
    const code = String(menu?.subsystemCode || DEFAULT_SUBSYSTEM_CODE).trim() || DEFAULT_SUBSYSTEM_CODE;
    if (deduped.has(code)) {
      return;
    }

    deduped.set(code, {
      code,
      title: SUBSYSTEM_TITLE_MAP[code] || menu?.subsystemTitle || menu?.groupTitle || menu?.title || code,
      description: menu?.subsystemDescription || '',
      icon: menu?.subsystemIcon || menu?.icon || 'Menu',
      sortIndex: Number(menu?.subsystemSortIndex ?? index),
      routeName: menu?.subsystemRouteName || menu?.routeName || '',
      path: menu?.subsystemRoutePath || menu?.path || '',
      menuCount: 1
    });
  });

  return Array.from(deduped.values()).sort((a, b) => Number(a.sortIndex || 0) - Number(b.sortIndex || 0));
}

function getPreferredSubsystem() {
  const session = getSession();
  const subsystems = getSubsystems();
  const visibleCodes = new Set(subsystems.map((item) => item.code));
  const preferred = String(
    session?.navigation?.preferredSubsystemCode ||
    session?.access?.preferredSubsystemCode ||
    session?.user?.preferredSubsystemCode ||
    DEFAULT_SUBSYSTEM_CODE
  ).trim() || DEFAULT_SUBSYSTEM_CODE;

  if (visibleCodes.has(preferred)) {
    return preferred;
  }

  return subsystems[0]?.code || DEFAULT_SUBSYSTEM_CODE;
}

function getActiveSubsystem() {
  const subsystems = getSubsystems();
  const visibleCodes = new Set(subsystems.map((item) => item.code));
  const stored = readActiveSubsystemStorage();
  if (stored && visibleCodes.has(stored)) {
    return stored;
  }

  return getPreferredSubsystem();
}

function setActiveSubsystem(code) {
  if (typeof window === 'undefined') {
    return String(code || '').trim() || getPreferredSubsystem();
  }

  const nextCode = String(code || '').trim();
  const nextValue = nextCode || getPreferredSubsystem();
  const currentValue = readActiveSubsystemStorage();
  if (currentValue === nextValue) {
    return nextValue;
  }

  localStorage.setItem(ACTIVE_SUBSYSTEM_KEY, nextValue);
  if (typeof window !== 'undefined') {
    window.dispatchEvent(new CustomEvent('platform-session-updated'));
  }
  return nextValue;
}

function findSubsystemByRoute(routeName) {
  const targetRouteName = String(routeName || '').trim();
  if (!targetRouteName) {
    return null;
  }

  const matchedMenu = getMenus().find((item) => item?.routeName === targetRouteName);
  if (!matchedMenu) {
    return null;
  }

  const code = String(matchedMenu?.subsystemCode || DEFAULT_SUBSYSTEM_CODE).trim() || DEFAULT_SUBSYSTEM_CODE;
  return getSubsystems().find((item) => item?.code === code) || null;
}

function getMenusBySubsystem(subsystemCode) {
  const targetCode = String(subsystemCode || '').trim();
  const menus = getMenus();
  if (!targetCode) {
    return menus;
  }

  return menus.filter((item) => {
    const menuCode = String(item?.subsystemCode || DEFAULT_SUBSYSTEM_CODE).trim() || DEFAULT_SUBSYSTEM_CODE;
    return menuCode === targetCode;
  });
}

function hasCapability(capability) {
  if (!capability) return true;
  const access = getAccess();
  const capabilities = Array.isArray(access?.capabilities) ? access.capabilities : [];
  return capabilities.includes(capability) || isAdmin();
}

function readActiveViewStorage() {
  if (typeof window === 'undefined') {
    return '';
  }

  return String(localStorage.getItem(ACTIVE_VIEW_KEY) || '').trim();
}

function getTerminalCode() {
  if (typeof document === 'undefined') {
    return 'web';
  }

  return String(document.documentElement?.dataset?.nativePlatform || 'web').trim() || 'web';
}

function buildShellModel(viewCode = '') {
  return buildPlatformShellModel({
    session: getSession() || {},
    activeViewCode: String(viewCode || '').trim(),
    terminal: getTerminalCode()
  });
}

function getViews() {
  return buildShellModel(readActiveViewStorage()).availableViews;
}

function getPreferredView() {
  const session = getSession();
  const explicit = String(
    session?.navigation?.preferredViewCode ||
    session?.access?.preferredViewCode ||
    session?.user?.preferredViewCode ||
    ''
  ).trim();

  const model = buildShellModel(explicit);
  return model.activeView.code;
}

function getActiveView() {
  const stored = readActiveViewStorage();
  const model = buildShellModel(stored || getPreferredView());
  return model.activeView.code;
}

function setActiveView(code) {
  if (typeof window === 'undefined') {
    return String(code || '').trim() || getPreferredView();
  }

  const nextCode = String(code || '').trim() || getPreferredView();
  const nextModel = buildShellModel(nextCode);
  const nextValue = nextModel.activeView.code;

  localStorage.setItem(ACTIVE_VIEW_KEY, nextValue);
  window.dispatchEvent(new CustomEvent('platform-session-updated'));
  return nextValue;
}

function getMenusByView(viewCode) {
  return buildShellModel(String(viewCode || '').trim() || getActiveView()).visibleMenus;
}
