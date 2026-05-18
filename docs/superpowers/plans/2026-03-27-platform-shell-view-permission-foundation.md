# 平台壳层、视角模型与权限编排基础实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为 `apps/web-portal` 建立由“视角 + 权限 + 开关”驱动的统一平台壳层，让头部、侧边导航、移动导航和路由落点共享同一套基础模型，并为后续交易工作台、研究工作台与治理中心重构提供稳定底座。

**Architecture:** 在 `apps/web-portal/src/platform/shell/` 下新增平台壳层模型，把当前 `src/utils/auth.js` 中分散的子系统/菜单/会话逻辑提升为视角、菜单、开关统一编排。先用纯函数与单测锁定视角和菜单过滤规则，再通过 `usePlatformShell` 与 `ViewSwitcher` 渐进接入 `Header`、`Sidebar`、`MobileNav`、`MainLayout` 和 `router/index.js`，保持现有业务页面的数据获取和表格逻辑不动。

**Tech Stack:** Vue 3, Pinia, Vue Router, Element Plus, Sass, Vitest, Vue Test Utils

---

**范围边界：**

- 本计划只覆盖平台基础壳层，不重写交易页、研究页、治理后台具体业务页面。
- 本计划继续沿用 `apps/web-portal` 当前的 Vue 3 + Vite + Pinia + Element Plus 技术栈。
- 后续“交易工作台”“研究工作台”“行动中枢”“治理中心”分别进入单独实施计划。

### Task 1: 建立视角模型与菜单过滤纯函数

**Files:**
- Create: `apps/web-portal/src/platform/shell/viewRegistry.js`
- Create: `apps/web-portal/src/platform/shell/platformShellModel.js`
- Test: `apps/web-portal/tests/unit/platform/platform-shell-model.spec.js`

- [ ] **Step 1: 先写失败中的纯函数单测**

```js
import { describe, expect, it } from 'vitest'
import { VIEW_REGISTRY } from '@/platform/shell/viewRegistry.js'
import {
  buildPlatformShellModel,
  isFeatureEnabled,
  normalizeFeatureFlags
} from '@/platform/shell/platformShellModel.js'

const sessionPayload = {
  user: {
    roleCode: 'trader'
  },
  menus: [
    {
      routeName: 'Dashboard',
      path: '/dashboard',
      title: '仪表盘',
      subsystemCode: 'workspace',
      icon: 'Odometer'
    },
    {
      routeName: 'Trading',
      path: '/trading',
      title: '交易台',
      subsystemCode: 'trading',
      icon: 'Wallet'
    },
    {
      routeName: 'Orders',
      path: '/orders',
      title: '订单管理',
      subsystemCode: 'trading',
      icon: 'List'
    },
    {
      routeName: 'AIAnalysis',
      path: '/ai-analysis',
      title: 'AI研判',
      subsystemCode: 'analysis',
      icon: 'Cpu'
    },
    {
      routeName: 'Settings',
      path: '/settings',
      title: '系统设置',
      subsystemCode: 'platform',
      icon: 'Setting'
    }
  ],
  featureFlags: [
    {
      code: 'view.management',
      enabled: false
    }
  ]
}

describe('platformShellModel', () => {
  it('暴露稳定的视角注册表', () => {
    expect(Object.keys(VIEW_REGISTRY)).toEqual([
      'trading',
      'research',
      'management',
      'composite'
    ])
    expect(VIEW_REGISTRY.trading.allowedSubsystems).toContain('trading')
    expect(VIEW_REGISTRY.research.allowedSubsystems).toContain('analysis')
  })

  it('根据角色、开关和终端生成可用视角与可见菜单', () => {
    const model = buildPlatformShellModel({
      session: sessionPayload,
      activeViewCode: 'trading',
      terminal: 'web'
    })

    expect(model.activeView.code).toBe('trading')
    expect(model.availableViews.map((item) => item.code)).toEqual([
      'trading',
      'composite'
    ])
    expect(model.visibleMenus.map((item) => item.routeName)).toEqual([
      'Dashboard',
      'Trading',
      'Orders'
    ])
  })

  it('在存储视角失效时回退到第一个可用视角', () => {
    const model = buildPlatformShellModel({
      session: sessionPayload,
      activeViewCode: 'management',
      terminal: 'web'
    })

    expect(model.activeView.code).toBe('trading')
  })

  it('按角色与终端判断开关是否开启', () => {
    const flags = normalizeFeatureFlags([
      {
        code: 'view.research',
        enabled: true,
        roles: ['analyst', 'trader'],
        terminals: ['web', 'desktop']
      }
    ])

    expect(isFeatureEnabled(flags, 'view.research', { roleCode: 'trader', terminal: 'web' })).toBe(true)
    expect(isFeatureEnabled(flags, 'view.research', { roleCode: 'viewer', terminal: 'web' })).toBe(false)
    expect(isFeatureEnabled(flags, 'view.research', { roleCode: 'trader', terminal: 'mobile' })).toBe(false)
  })
})
```

- [ ] **Step 2: 运行单测并确认失败**

Run:

```bash
cd /Users/lusd/Documents/New\ project/refactor-v2/apps/web-portal
npx vitest run tests/unit/platform/platform-shell-model.spec.js
```

Expected:

```text
FAIL  tests/unit/platform/platform-shell-model.spec.js
Error: Failed to resolve import "@/platform/shell/viewRegistry.js"
```

- [ ] **Step 3: 新增 `viewRegistry.js`**

```js
export const VIEW_REGISTRY = {
  trading: {
    code: 'trading',
    title: '交易视角',
    description: '聚焦交易执行、订单、持仓与风险响应',
    homeRouteName: 'Trading',
    allowedSubsystems: ['workspace', 'trading', 'market']
  },
  research: {
    code: 'research',
    title: '研究视角',
    description: '聚焦市场扫描、AI 研判、策略与回测',
    homeRouteName: 'AIAnalysis',
    allowedSubsystems: ['workspace', 'market', 'analysis']
  },
  management: {
    code: 'management',
    title: '管理视角',
    description: '聚焦权限治理、系统设置、任务调度与平台运行状态',
    homeRouteName: 'Settings',
    allowedSubsystems: ['workspace', 'platform']
  },
  composite: {
    code: 'composite',
    title: '综合视角',
    description: '面向高权限用户，展示完整平台入口',
    homeRouteName: 'Dashboard',
    allowedSubsystems: ['workspace', 'market', 'trading', 'analysis', 'platform']
  }
}

const ROLE_VIEW_MAP = {
  admin: ['management', 'composite'],
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
  return VIEW_REGISTRY[String(viewCode || '').trim()] || VIEW_REGISTRY.trading
}
```

- [ ] **Step 4: 新增 `platformShellModel.js`**

```js
import { VIEW_REGISTRY, resolveRoleViewCodes, resolveViewDefinition } from './viewRegistry.js'

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
  return rawFlags.reduce((result, flag) => {
    const code = String(flag?.code || '').trim()
    if (!code) {
      return result
    }

    result[code] = {
      enabled: flag?.enabled !== false,
      roles: Array.isArray(flag?.roles) ? flag.roles : [],
      terminals: Array.isArray(flag?.terminals) ? flag.terminals : []
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

  if (flag.roles.length && !flag.roles.includes(context.roleCode)) {
    return false
  }

  if (flag.terminals.length && !flag.terminals.includes(context.terminal)) {
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
  const extraRoles = Array.isArray(session?.access?.roles) ? session.access.roles : []
  const roleCodes = Array.from(new Set([roleCode].concat(extraRoles).filter(Boolean)))
  const menus = (Array.isArray(session?.menus) ? session.menus : [])
    .map(normalizeMenu)
    .filter((item) => !item.hidden)
    .sort((a, b) => a.sortIndex - b.sortIndex)

  const flagMap = normalizeFeatureFlags(session?.featureFlags || [])
  const candidateViewCodes = Array.from(new Set(roleCodes.flatMap((code) => resolveRoleViewCodes(code))))

  const availableViews = candidateViewCodes
    .filter((viewCode) => isFeatureEnabled(flagMap, `view.${viewCode}`, { roleCode, terminal }))
    .map((viewCode) => resolveViewDefinition(viewCode))

  const fallbackViews = availableViews.length ? availableViews : [VIEW_REGISTRY.trading]
  const activeView = fallbackViews.find((item) => item.code === activeViewCode) || fallbackViews[0]

  const visibleMenus = menus.filter((item) => activeView.allowedSubsystems.includes(item.subsystemCode))

  return {
    roleCode,
    availableViews: fallbackViews,
    activeView,
    visibleMenus,
    flagMap
  }
}
```

- [ ] **Step 5: 运行单测并确认通过**

Run:

```bash
cd /Users/lusd/Documents/New\ project/refactor-v2/apps/web-portal
npx vitest run tests/unit/platform/platform-shell-model.spec.js
```

Expected:

```text
✓ tests/unit/platform/platform-shell-model.spec.js
```

- [ ] **Step 6: 提交这一小步**

```bash
cd /Users/lusd/Documents/New\ project/refactor-v2
git add apps/web-portal/src/platform/shell/viewRegistry.js \
  apps/web-portal/src/platform/shell/platformShellModel.js \
  apps/web-portal/tests/unit/platform/platform-shell-model.spec.js
git commit -m "feat: add platform shell view model foundation"
```

### Task 2: 把视角模型接入 `auth.js` 与平台壳层 composable

**Files:**
- Modify: `apps/web-portal/src/utils/auth.js`
- Create: `apps/web-portal/src/platform/shell/usePlatformShell.js`
- Test: `apps/web-portal/tests/unit/platform/platform-shell-auth.spec.js`

- [ ] **Step 1: 先写 `auth.js` 的失败单测**

```js
import { afterEach, beforeEach, describe, expect, it } from 'vitest'
import {
  clearAuth,
  getActiveView,
  getMenusByView,
  getViews,
  setActiveView,
  setSession
} from '@/utils/auth.js'

const sessionPayload = {
  user: {
    roleCode: 'trader'
  },
  menus: [
    {
      routeName: 'Dashboard',
      path: '/dashboard',
      title: '仪表盘',
      subsystemCode: 'workspace'
    },
    {
      routeName: 'Trading',
      path: '/trading',
      title: '交易台',
      subsystemCode: 'trading'
    },
    {
      routeName: 'AIAnalysis',
      path: '/ai-analysis',
      title: 'AI研判',
      subsystemCode: 'analysis'
    }
  ]
}

describe('auth platform shell helpers', () => {
  beforeEach(() => {
    localStorage.clear()
  })

  afterEach(() => {
    clearAuth()
  })

  it('返回视角列表并持久化当前视角', () => {
    setSession(sessionPayload)

    expect(getViews().map((item) => item.code)).toEqual(['trading', 'composite'])
    expect(getActiveView()).toBe('trading')

    setActiveView('composite')

    expect(getActiveView()).toBe('composite')
  })

  it('按视角过滤菜单', () => {
    setSession(sessionPayload)

    expect(getMenusByView('trading').map((item) => item.routeName)).toEqual([
      'Dashboard',
      'Trading'
    ])
    expect(getMenusByView('composite').map((item) => item.routeName)).toEqual([
      'Dashboard',
      'Trading',
      'AIAnalysis'
    ])
  })
})
```

- [ ] **Step 2: 运行单测并确认失败**

Run:

```bash
cd /Users/lusd/Documents/New\ project/refactor-v2/apps/web-portal
npx vitest run tests/unit/platform/platform-shell-auth.spec.js
```

Expected:

```text
FAIL  tests/unit/platform/platform-shell-auth.spec.js
TypeError: getViews is not a function
```

- [ ] **Step 3: 修改 `src/utils/auth.js`，补齐视角存储与菜单过滤 API**

在文件顶部新增导入、常量和导出项：

```js
import { buildPlatformShellModel } from '../platform/shell/platformShellModel.js';

const ACTIVE_VIEW_KEY = 'platform_active_view';

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
```

在 `clearAuth()` 中清理视角存储：

```js
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
```

在文件末尾追加以下函数：

```js
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
```

- [ ] **Step 4: 新增 `usePlatformShell.js` composable**

```js
import { computed, onMounted, onUnmounted, ref } from 'vue'
import {
  getActiveView,
  getCurrentUser,
  getMenusByView,
  getViews,
  setActiveView
} from '../../utils/auth.js'

export function usePlatformShell() {
  const sessionVersion = ref(0)

  const refresh = () => {
    sessionVersion.value += 1
  }

  onMounted(() => {
    window.addEventListener('platform-session-updated', refresh)
  })

  onUnmounted(() => {
    window.removeEventListener('platform-session-updated', refresh)
  })

  const availableViews = computed(() => {
    sessionVersion.value
    return getViews()
  })

  const activeViewCode = computed(() => {
    sessionVersion.value
    return getActiveView()
  })

  const activeView = computed(() => {
    return availableViews.value.find((item) => item.code === activeViewCode.value) || availableViews.value[0] || null
  })

  const visibleMenus = computed(() => {
    sessionVersion.value
    return getMenusByView(activeViewCode.value)
  })

  const currentUser = computed(() => {
    sessionVersion.value
    return getCurrentUser() || {}
  })

  const switchView = (viewCode) => {
    return setActiveView(viewCode)
  }

  return {
    availableViews,
    activeViewCode,
    activeView,
    visibleMenus,
    currentUser,
    switchView,
    refresh
  }
}
```

- [ ] **Step 5: 运行单测并确认通过**

Run:

```bash
cd /Users/lusd/Documents/New\ project/refactor-v2/apps/web-portal
npx vitest run tests/unit/platform/platform-shell-auth.spec.js
```

Expected:

```text
✓ tests/unit/platform/platform-shell-auth.spec.js
```

- [ ] **Step 6: 提交这一小步**

```bash
cd /Users/lusd/Documents/New\ project/refactor-v2
git add apps/web-portal/src/utils/auth.js \
  apps/web-portal/src/platform/shell/usePlatformShell.js \
  apps/web-portal/tests/unit/platform/platform-shell-auth.spec.js
git commit -m "feat: expose platform shell auth helpers"
```

### Task 3: 新增 `ViewSwitcher` 并接入桌面端头部

**Files:**
- Create: `apps/web-portal/src/components/layout/ViewSwitcher.vue`
- Modify: `apps/web-portal/src/components/layout/Header.vue`
- Test: `apps/web-portal/tests/unit/platform/view-switcher.spec.js`

- [ ] **Step 1: 先写 `ViewSwitcher` 失败单测**

```js
import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import ViewSwitcher from '@/components/layout/ViewSwitcher.vue'

describe('ViewSwitcher', () => {
  it('渲染全部可用视角并高亮当前视角', () => {
    const wrapper = mount(ViewSwitcher, {
      props: {
        modelValue: 'trading',
        views: [
          { code: 'trading', title: '交易视角', description: '执行链路' },
          { code: 'research', title: '研究视角', description: '研究链路' }
        ]
      }
    })

    expect(wrapper.text()).toContain('交易视角')
    expect(wrapper.text()).toContain('研究视角')
    expect(wrapper.find('[data-view-code=\"trading\"]').classes()).toContain('active')
  })

  it('点击非当前视角时抛出变更事件', async () => {
    const wrapper = mount(ViewSwitcher, {
      props: {
        modelValue: 'trading',
        views: [
          { code: 'trading', title: '交易视角', description: '执行链路' },
          { code: 'research', title: '研究视角', description: '研究链路' }
        ]
      }
    })

    await wrapper.find('[data-view-code=\"research\"]').trigger('click')

    expect(wrapper.emitted('update:modelValue')).toEqual([['research']])
    expect(wrapper.emitted('change')[0][0]).toMatchObject({ code: 'research' })
  })
})
```

- [ ] **Step 2: 运行单测并确认失败**

Run:

```bash
cd /Users/lusd/Documents/New\ project/refactor-v2/apps/web-portal
npx vitest run tests/unit/platform/view-switcher.spec.js
```

Expected:

```text
FAIL  tests/unit/platform/view-switcher.spec.js
Error: Failed to resolve import "@/components/layout/ViewSwitcher.vue"
```

- [ ] **Step 3: 新增 `ViewSwitcher.vue`**

```vue
<template>
  <div class="view-switcher" role="tablist" aria-label="工作视角切换">
    <button
      v-for="view in views"
      :key="view.code"
      :data-view-code="view.code"
      type="button"
      class="view-switcher__item"
      :class="{ active: view.code === modelValue }"
      :aria-selected="String(view.code === modelValue)"
      @click="handleSelect(view)"
    >
      <strong>{{ view.title }}</strong>
      <span>{{ view.description }}</span>
    </button>
  </div>
</template>

<script setup>
const props = defineProps({
  modelValue: {
    type: String,
    required: true
  },
  views: {
    type: Array,
    default: () => []
  }
})

const emit = defineEmits(['update:modelValue', 'change'])

function handleSelect(view) {
  if (!view || view.code === props.modelValue) {
    return
  }

  emit('update:modelValue', view.code)
  emit('change', view)
}
</script>

<style scoped lang="scss">
.view-switcher {
  display: inline-flex;
  gap: 8px;
  padding: 6px;
  border: 1px solid var(--border-soft);
  border-radius: 18px;
  background: color-mix(in srgb, var(--surface-soft) 86%, transparent);
}

.view-switcher__item {
  min-width: 120px;
  display: grid;
  gap: 4px;
  padding: 10px 12px;
  border: 0;
  border-radius: 14px;
  background: transparent;
  color: var(--text-muted);
  text-align: left;
  cursor: pointer;
  transition: background 0.2s ease, color 0.2s ease, transform 0.2s ease;
}

.view-switcher__item strong {
  font-size: 13px;
  color: inherit;
}

.view-switcher__item span {
  font-size: 11px;
  line-height: 1.35;
}

.view-switcher__item.active {
  background: color-mix(in srgb, var(--accent) 16%, transparent);
  color: var(--text-emphasis);
}

.view-switcher__item:hover {
  transform: translateY(-1px);
}
</style>
```

- [ ] **Step 4: 修改 `Header.vue`，把视角切换放进桌面头部**

在模板中把 `header-left` 区域改成以下结构：

```vue
<div class="header-left">
  <div class="page-context">
    <div class="page-eyebrow">
      <span class="subsystem-pill">{{ currentSubsystemTitle }}</span>
      <span class="context-chip">{{ contextChips[0] }}</span>
      <span class="context-chip muted">{{ contextChips[1] }}</span>
    </div>
    <div class="page-copy">
      <h1>{{ currentPageTitle }}</h1>
      <p>{{ pageSummary }}</p>
    </div>
  </div>

  <ViewSwitcher
    v-if="availableViews.length > 1"
    class="header-view-switcher"
    :model-value="activeViewCode"
    :views="availableViews"
    @change="handleViewChange"
  />
</div>
```

在脚本区新增导入与逻辑：

```js
import ViewSwitcher from './ViewSwitcher.vue'
import { usePlatformShell } from '../../platform/shell/usePlatformShell.js'

const { availableViews, activeViewCode, switchView } = usePlatformShell()

const handleViewChange = async (view) => {
  if (!view) {
    return
  }

  switchView(view.code)
  if (view.homeRouteName && view.homeRouteName !== route.name) {
    await router.push({ name: view.homeRouteName })
  }
}
```

在样式中补充头部布局：

```scss
.header-left {
  display: flex;
  align-items: flex-start;
  gap: 18px;
}

.header-view-switcher {
  margin-top: 4px;
}
```

- [ ] **Step 5: 运行单测并确认通过**

Run:

```bash
cd /Users/lusd/Documents/New\ project/refactor-v2/apps/web-portal
npx vitest run tests/unit/platform/view-switcher.spec.js
```

Expected:

```text
✓ tests/unit/platform/view-switcher.spec.js
```

- [ ] **Step 6: 提交这一小步**

```bash
cd /Users/lusd/Documents/New\ project/refactor-v2
git add apps/web-portal/src/components/layout/ViewSwitcher.vue \
  apps/web-portal/src/components/layout/Header.vue \
  apps/web-portal/tests/unit/platform/view-switcher.spec.js
git commit -m "feat: add platform view switcher to header"
```

### Task 4: 让侧边导航、移动导航、移动头部与路由都跟随当前视角

**Files:**
- Create: `apps/web-portal/src/platform/shell/viewRouting.js`
- Modify: `apps/web-portal/src/router/index.js`
- Modify: `apps/web-portal/src/components/layout/Sidebar.vue`
- Modify: `apps/web-portal/src/components/layout/MobileNav.vue`
- Modify: `apps/web-portal/src/components/layout/MainLayout.vue`
- Test: `apps/web-portal/tests/unit/platform/view-routing.spec.js`

- [ ] **Step 1: 先写路由与视角同步规则的失败单测**

```js
import { describe, expect, it } from 'vitest'
import { resolveViewBySubsystem } from '@/platform/shell/viewRouting.js'

describe('resolveViewBySubsystem', () => {
  it('把 analysis 路由归到研究视角', () => {
    expect(resolveViewBySubsystem('analysis', 'trading')).toBe('research')
  })

  it('把 platform 路由归到管理视角', () => {
    expect(resolveViewBySubsystem('platform', 'trading')).toBe('management')
  })

  it('为 workspace 保留当前视角', () => {
    expect(resolveViewBySubsystem('workspace', 'composite')).toBe('composite')
  })
})
```

- [ ] **Step 2: 运行单测并确认失败**

Run:

```bash
cd /Users/lusd/Documents/New\ project/refactor-v2/apps/web-portal
npx vitest run tests/unit/platform/view-routing.spec.js
```

Expected:

```text
FAIL  tests/unit/platform/view-routing.spec.js
Error: Failed to resolve import "@/platform/shell/viewRouting.js"
```

- [ ] **Step 3: 新增 `viewRouting.js`，并修改 `router/index.js` 同步当前视角**

新增 `apps/web-portal/src/platform/shell/viewRouting.js`：

```js
export function resolveViewBySubsystem(subsystemCode = '', currentViewCode = 'trading') {
  const normalizedCode = String(subsystemCode || '').trim()

  if (normalizedCode === 'analysis') {
    return 'research'
  }

  if (normalizedCode === 'platform') {
    return 'management'
  }

  if (normalizedCode === 'trading') {
    return 'trading'
  }

  return String(currentViewCode || '').trim() || 'trading'
}
```

修改 `apps/web-portal/src/router/index.js` 的导入与守卫：

```js
import {
  getActiveView,
  getMenus,
  hasCapability,
  isAdmin,
  isLoggedIn,
  setActiveSubsystem,
  setActiveView
} from '../utils/auth.js'
import { resolveViewBySubsystem } from '../platform/shell/viewRouting.js'
```

```js
  if (to.meta.subsystem) {
    setActiveSubsystem(String(to.meta.subsystem))
    const nextViewCode = resolveViewBySubsystem(String(to.meta.subsystem), getActiveView())
    setActiveView(nextViewCode)
  }
```

- [ ] **Step 4: 修改 `Sidebar.vue`、`MobileNav.vue`、`MainLayout.vue` 使用当前视角**

在 `Sidebar.vue` 的导入区改为：

```js
import { getActiveView, getMenusByView, getSubsystems } from '../../utils/auth.js'
```

在 `menuTree` 计算属性里把菜单来源替换为：

```js
const activeViewCode = getActiveView()
const rawMenus = getMenusByView(activeViewCode)
```

在 `MobileNav.vue` 的导入区改为：

```js
import {
  getActiveSubsystem,
  getCurrentUser,
  getMenusByView,
  getSubsystems,
  getActiveView,
  isAdmin,
  logout
} from '../../utils/auth.js'
```

在 `normalizedMenus` 计算属性里把菜单来源替换为：

```js
const currentViewCode = getActiveView()
return getMenusByView(currentViewCode)
  .filter((menu) => !menu?.hidden)
  .map((menu, index) => ({
    routeName: menu?.routeName || '',
    path: menu?.path || '',
    title: menu?.title || '菜单',
    subsystemCode: String(menu?.subsystemCode || menu?.subsystem || 'workspace'),
    icon: ICON_MAP[menu?.icon] || Menu,
    targetKey: menu?.routeName || menu?.path || `menu:${index}`
  }))
```

在 `MainLayout.vue` 的脚本导入区新增：

```js
import { usePlatformShell } from '../../platform/shell/usePlatformShell.js'
```

并把 `currentSectionLabel` 改为：

```js
const { activeView } = usePlatformShell()

const currentSectionLabel = computed(() => {
  return activeView.value?.title || '工作台'
})
```

- [ ] **Step 5: 运行目标单测、全量单测与构建**

Run:

```bash
cd /Users/lusd/Documents/New\ project/refactor-v2/apps/web-portal
npx vitest run tests/unit/platform/view-routing.spec.js
npm run test:unit
npm run build
```

Expected:

```text
✓ tests/unit/platform/view-routing.spec.js
✓ tests/unit/ 目录下全部用例通过
vite build completed successfully
```

- [ ] **Step 6: 提交这一小步**

```bash
cd /Users/lusd/Documents/New\ project/refactor-v2
git add apps/web-portal/src/platform/shell/viewRouting.js \
  apps/web-portal/src/router/index.js \
  apps/web-portal/src/components/layout/Sidebar.vue \
  apps/web-portal/src/components/layout/MobileNav.vue \
  apps/web-portal/src/components/layout/MainLayout.vue \
  apps/web-portal/tests/unit/platform/view-routing.spec.js
git commit -m "feat: scope shell navigation by active view"
```

### Task 5: 做完整验证并记录第一阶段结果

**Files:**
- Verify only

- [ ] **Step 1: 运行桌面端冒烟验证**

Run:

```bash
cd /Users/lusd/Documents/New\ project/refactor-v2/apps/web-portal
npm run desktop:smoke
```

Expected:

```text
desktop smoke completed
```

- [ ] **Step 2: 人工验证三类关键路径**

```text
1. 使用 trader 角色登录，默认进入交易视角，并且侧边栏不显示平台治理菜单
2. 点击 Header 里的视角切换到研究视角，路由跳转到 AIAnalysis，侧边栏与移动抽屉同步过滤
3. 直接访问 /settings 时，当前视角自动切为 management，Header / Sidebar / MobileNav 的入口同步变化
```

- [ ] **Step 3: 提交最终验证结果**

```bash
cd /Users/lusd/Documents/New\ project/refactor-v2
git status --short
```

Expected:

```text
working tree clean
```

```bash
git commit --allow-empty -m "chore: verify platform shell foundation rollout"
```

---

## 2026-03-27 执行结果回填

### 已完成

- Task 1 已完成：新增 `viewRegistry.js`、`platformShellModel.js` 与对应单测，建立“视角 + 菜单 + 开关”纯函数模型。
- Task 2 已完成：`auth.js` 已补齐 `getViews/getActiveView/setActiveView/getMenusByView`，并新增 `usePlatformShell.js`。
- Task 3 已完成：新增 `ViewSwitcher.vue`，并接入桌面端 `Header.vue`。
- Task 4 已完成：新增 `viewRouting.js`，并让 `router/index.js`、`Sidebar.vue`、`MobileNav.vue`、`MainLayout.vue` 跟随当前视角。
- 多角色边界已补强：新增“次级角色解锁视角”的失败测试并修复，确保符合前面确认的单用户多角色蓝图。
- 真实界面手工路径验证已完成：已使用“模拟账户 session 注入 + 真实浏览器交互”方式覆盖交易、研究、管理三类视角跳转与菜单过滤。
- 第二轮硬清理已完成：已删除 `vendor/`、顶层 `test_all_api.js`、顶层 `package.json` / `package-lock.json` / `node_modules/`，并清理空目录 `runtime/mobile`。
- 残留运行进程已收口：此前用于手工验证的 `apps/web-portal` Vite 服务已关闭，不再保留后台监听进程。

### 已验证

- `npx vitest run tests/unit/platform/platform-shell-model.spec.js` 通过
- `npx vitest run tests/unit/platform/platform-shell-auth.spec.js` 通过
- `npx vitest run tests/unit/platform/view-switcher.spec.js` 通过
- `npx vitest run tests/unit/platform/view-routing.spec.js` 通过
- `npx vitest run` 再次通过，当前共 `9` 个测试文件、`32` 个用例通过
- `npm run build` 在第二轮硬清理后再次通过
- `npm run desktop:smoke` 通过，输出 `desktop_smoke_passed`
- 人工关键路径验证通过：
  - 路径 1：默认进入 `/trading`，侧边栏不显示平台治理菜单
  - 路径 2：Header 切换到研究视角后跳转 `/ai-analysis`，桌面侧边栏与移动抽屉同步过滤
  - 路径 3：直接访问 `/settings` 后自动切换到 `management`，Header / Sidebar / MobileNav 同步变化
- 运行态已确认收口：`lsof -iTCP:3100 -sTCP:LISTEN` 无输出，`ps aux | rg -i "vite|web-portal|refactor-v2/apps/web-portal"` 无残留相关进程

### 未完成或不适用

- `git status --short` / `git commit` 不作为本轮收口动作：
  - 当前 `refactor-v2` 目录不是独立 git 仓库
  - 上层仓库把整个 `refactor-v2/` 视为未跟踪目录
  - 用户已明确“不上传”，且本地 git identity 也未配置
- 第三轮“兼容链切断型”硬清理暂不执行：
  - 当时 `shared/bootstrap.py` 与 `shared/legacy_compat.py` 仍承担旧模块兼容装配
  - 当时 `apps/trade-service/src/main.py` 仍会动态加载 `services/trade-service/src/main.py`
  - 上述约束后续已在后续轮次中继续收缩，本段仅保留当时状态记录

### 执行说明

- `.worktrees/` 目录已避让，不再占用用户另一个项目的本地 worktree 目录。
- 由于实际改造目录 `refactor-v2` 不是独立 git repo，本轮实现直接在该独立重构目录内落地，而不是依赖上层仓库 worktree 作为真实代码工作区。
- 真实界面验证截图与结果已保存在 `output/playwright/` 目录下，便于后续回看。
- `apps/web-portal/dist/` 仅用于本轮构建验收，验证完成后已再次删除，避免把生成产物留在重构目录中。
