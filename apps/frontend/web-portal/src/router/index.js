import { createRouter, createWebHistory } from 'vue-router'
import {
  getActiveView,
  getMenus,
  hasCapability,
  isAdmin,
  isLoggedIn,
  setActiveSubsystem,
  setActiveView
} from '../utils/auth.js'
import { getStoredSystemName } from '../utils/api.js'
import { resolveViewBySubsystem } from '../platform/shell/viewRouting.js'

// 布局组件
import MainLayout from '../components/layout/MainLayout.vue'

// 页面组件 - 懒加载
const Dashboard = () => import('../views/Dashboard.vue')
const Trading = () => import('../views/Trading.vue')
const Positions = () => import('../views/Positions.vue')
const Orders = () => import('../views/Orders.vue')
const StockPool = () => import('../views/StockPool.vue')
const WatchlistPool = () => import('../views/WatchlistPool.vue')
const AIAnalysis = () => import('../views/AIAnalysis.vue')
const Strategy = () => import('../views/Strategy.vue')
const Backtest = () => import('../views/Backtest.vue')
const RiskManagement = () => import('../views/RiskManagement.vue')
const MarketData = () => import('../views/MarketData.vue')
const Kline = () => import('../views/Kline.vue')
const Recommendations = () => import('../views/Recommendations.vue')
const Settings = () => import('../views/Settings.vue')
const UserManagement = () => import('../views/UserManagement.vue')
const Login = () => import('../views/Login.vue')
const Profile = () => import('../views/Profile.vue')
const BrokerManagement = () => import('../views/BrokerManagement.vue')
const Notifications = () => import('../views/Notifications.vue')
const FinanceNews = () => import('../views/FinanceNews.vue')
const SchedulerCenter = () => import('../views/system/SchedulerCenter.vue')
const HistoryCoverage = () => import('../views/system/HistoryCoverage.vue')
const SymbolDetail = () => import('../views/SymbolDetail.vue')

const routes = [
  {
    path: '/login',
    name: 'Login',
    component: Login,
    meta: { public: true, title: '登录' }
  },
  {
    path: '/',
    component: MainLayout,
    redirect: '/dashboard',
    meta: { requiresAuth: true },
    children: [
      // 仪表盘
      {
        path: 'dashboard',
        name: 'Dashboard',
        component: Dashboard,
        meta: { title: '仪表盘', icon: 'Odometer', group: 'overview', subsystem: 'workspace', capability: 'dashboard.view' }
      },

      // 交易管理
      {
        path: 'trading',
        name: 'Trading',
        component: Trading,
        meta: { title: '交易台', icon: 'Wallet', group: 'trading', subsystem: 'trading', capability: 'trade.live' }
      },
      {
        path: 'positions',
        name: 'Positions',
        component: Positions,
        meta: { title: '持仓管理', icon: 'Coin', group: 'trading', subsystem: 'trading', capability: 'positions.view' }
      },
      {
        path: 'orders',
        name: 'Orders',
        component: Orders,
        meta: { title: '订单管理', icon: 'List', group: 'trading', subsystem: 'trading', capability: 'orders.view' }
      },

      // 股票池
      {
        path: 'stock-pool',
        name: 'StockPool',
        component: StockPool,
        meta: { title: '股票池', icon: 'Collection', group: 'stocks', subsystem: 'market', capability: 'stock.pool.view' }
      },
      {
        path: 'watchlist-pool',
        name: 'WatchlistPool',
        component: WatchlistPool,
        meta: { title: '自选股票池', icon: 'Star', group: 'stocks', subsystem: 'market', capability: 'stock.pool.view' }
      },
      {
        path: 'symbol/:symbol',
        name: 'SymbolDetail',
        component: SymbolDetail,
        meta: { title: '标的详情', icon: 'TrendCharts', group: 'stocks', subsystem: 'market', capability: 'market.detail.view', hidden: true }
      },

      // AI分析
      {
        path: 'ai-analysis',
        name: 'AIAnalysis',
        component: AIAnalysis,
        meta: { title: 'AI研判', icon: 'Cpu', group: 'analysis', subsystem: 'analysis', capability: 'ai.analysis' }
      },

      // 量化策略
      {
        path: 'strategy',
        name: 'Strategy',
        component: Strategy,
        meta: { title: '策略管理', icon: 'TrendCharts', group: 'strategy', subsystem: 'analysis', capability: 'strategy.manage' }
      },
      {
        path: 'backtest',
        name: 'Backtest',
        component: Backtest,
        meta: { title: '策略回测', icon: 'DataLine', group: 'strategy', subsystem: 'analysis', capability: 'strategy.backtest' }
      },

      // 风控管理
      {
        path: 'risk',
        name: 'RiskManagement',
        component: RiskManagement,
        meta: { title: '风控管理', icon: 'Warning', group: 'risk', subsystem: 'trading', capability: 'risk.manage' }
      },

      // 市场行情
      {
        path: 'market',
        name: 'MarketData',
        component: MarketData,
        meta: { title: '实时行情', icon: 'Histogram', group: 'market', subsystem: 'market', capability: 'market.view' }
      },
      {
        path: 'kline',
        name: 'Kline',
        component: Kline,
        meta: { title: '历史K线', icon: 'TrendCharts', group: 'market', subsystem: 'market', capability: 'market.detail.view' }
      },

      // 智能推荐
      {
        path: 'recommendations',
        name: 'Recommendations',
        component: Recommendations,
        meta: { title: '智能推荐', icon: 'Star', group: 'market', subsystem: 'market', capability: 'recommendations.view' }
      },
      {
        path: 'finance-news',
        name: 'FinanceNews',
        component: FinanceNews,
        meta: { title: '财经快讯', icon: 'Bell', group: 'market', subsystem: 'market', capability: 'market.news.view' }
      },

      // 个人中心
      {
        path: 'profile',
        name: 'Profile',
        component: Profile,
        meta: { title: '个人中心', icon: 'User', group: 'user', subsystem: 'platform', capability: 'profile.view' }
      },
      {
        path: 'broker-management',
        name: 'BrokerManagement',
        component: BrokerManagement,
        meta: { title: '券商连接', icon: 'Wallet', group: 'user', subsystem: 'platform', capability: 'profile.view' }
      },
      {
        path: 'notifications',
        name: 'Notifications',
        component: Notifications,
        meta: { title: '消息通知', icon: 'Bell', group: 'user', subsystem: 'platform', capability: 'notifications.view' }
      },

      // 系统设置
      {
        path: 'settings',
        name: 'Settings',
        component: Settings,
        meta: { title: '系统设置', icon: 'Setting', group: 'system', subsystem: 'platform', capability: 'settings.manage' }
      },
      {
        path: 'user-management',
        name: 'UserManagement',
        component: UserManagement,
        meta: { title: '用户管理', icon: 'User', group: 'system', subsystem: 'platform', capability: 'users.manage' }
      },
      {
        path: 'scheduler-center',
        name: 'SchedulerCenter',
        component: SchedulerCenter,
        meta: { title: '任务中心', icon: 'Timer', group: 'system', subsystem: 'platform', capability: 'tasks.manage' }
      },
      {
        path: 'history-coverage',
        name: 'HistoryCoverage',
        component: HistoryCoverage,
        meta: { title: '历史补价覆盖', icon: 'DataLine', group: 'system', subsystem: 'platform', capability: 'tasks.manage' }
      }
    ]
  },
  {
    path: '/:pathMatch(.*)*',
    redirect: '/'
  }
]

const router = createRouter({
  history: createWebHistory(),
  routes,
  scrollBehavior() {
    return { top: 0 }
  }
})

// 路由守卫
router.beforeEach((to, from, next) => {
  // 设置页面标题
  const systemName = getStoredSystemName()
  if (to.meta.title) {
    document.title = to.path === '/login' ? systemName : `${to.meta.title} - ${systemName}`
  }
  
  // 公开页面直接放行
  if (to.meta.public) {
    if (isLoggedIn() && to.path === '/login') {
      next('/dashboard')
      return
    }
    next()
    return
  }

  // 需要登录的页面
  if (to.meta.requiresAuth) {
    if (!isLoggedIn()) {
      next('/login')
      return
    }
  }

  const menus = getMenus()
  if (to.meta.capability && menus.length && !hasCapability(to.meta.capability) && !isAdmin()) {
    const firstMenu = menus[0]
    next(firstMenu?.path || '/dashboard')
    return
  }

  if (to.meta.subsystem) {
    setActiveSubsystem(String(to.meta.subsystem))
    const nextViewCode = resolveViewBySubsystem(String(to.meta.subsystem), getActiveView())
    setActiveView(nextViewCode)
  }

  next()
})

// 全局错误处理
router.onError((error) => {
  console.error('路由错误:', error)
  if (error.message?.includes('401') || error.message?.includes('登录')) {
    router.push('/login')
  }
})

export default router
