import { ref } from 'vue'

// 当前页面状态
const currentPage = ref('dashboard')

// 页面组件映射
const pageComponents = {
  dashboard: () => import('../views/Dashboard.vue'),
  trading: () => import('../views/TradingView.vue'),
  positions: () => import('../views/Positions.vue'),
  'ai-analysis': () => import('../views/AIAnalysis.vue'),
  'stocks-cn': () => import('../views/StocksCN.vue'),
  'stocks-us': () => import('../views/StocksUS.vue'),
  'stocks-hk': () => import('../views/StocksHK.vue'),
  kline: () => import('../views/Kline.vue'),
  'broker-management': () => import('../views/BrokerManagement.vue'),
  settings: () => import('../views/Settings.vue'),
  'user-management': () => import('../views/UserManagement.vue'),
  'config-management': () => import('../views/ConfigManagement.vue')
}

// 页面标题映射
const pageTitles = {
  dashboard: '总览看板',
  trading: '交易视图',
  positions: '持仓管理',
  'ai-analysis': 'AI研判',
  'stocks-cn': 'A股股票池',
  'stocks-us': '美股股票池',
  'stocks-hk': '港股股票池',
  kline: 'K线数据',
  'broker-management': '券商连接',
  settings: '系统设置',
  'user-management': '用户管理',
  'config-management': '配置管理'
}

export function usePageStore() {
  const setPage = (page) => {
    if (pageComponents[page]) {
      currentPage.value = page
    }
  }

  const getCurrentPage = () => currentPage.value

  const getCurrentComponent = () => pageComponents[currentPage.value]

  const getCurrentTitle = () => pageTitles[currentPage.value] || 'Refactor V2'

  return {
    currentPage,
    setPage,
    getCurrentPage,
    getCurrentComponent,
    getCurrentTitle,
    pageComponents,
    pageTitles
  }
}
