<template>
  <div class="portal-container">
    <CyberBackground />
    <div class="portal-top-bar">
      <div class="logo">
        <h2 class="glow-title">NEXUS TRADE</h2>
      </div>
      <div class="top-bar-actions">
        <ThemeSwitcher />
        <el-dropdown>
          <div class="user-dropdown glass-panel">
            <el-avatar :size="32" :src="currentUser.avatar || undefined">
              {{ userInitial }}
            </el-avatar>
            <div class="user-copy">
              <strong>{{ displayName }}</strong>
              <span>{{ roleLabel }}</span>
            </div>
            <el-icon><ArrowDown /></el-icon>
          </div>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item @click="router.push('/profile')">个人中心</el-dropdown-item>
              <el-dropdown-item v-if="isAdmin()" @click="router.push('/settings')">系统设置</el-dropdown-item>
              <el-dropdown-item divided @click="handleLogout">退出登录</el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
      </div>
    </div>
    
    <div class="portal-content">
      <header class="portal-header">
        <h1 class="portal-title">量化交易与 AI 研判综合指挥中心</h1>
        <p class="portal-subtitle">QUANTITATIVE TRADING & AI ANALYSIS COMMAND CENTER</p>
      </header>

      <div class="portal-grid">
        <div 
          v-for="subsystem in subsystems" 
          :key="subsystem.name"
          class="module-card glass-panel"
          @click="navigateTo(subsystem.path)"
        >
          <div class="module-icon-wrap">
            <el-icon class="module-icon"><component :is="subsystem.icon" /></el-icon>
          </div>
          <div class="module-info">
            <h3 class="module-name">{{ subsystem.name }}</h3>
            <p class="module-desc">{{ subsystem.desc }}</p>
          </div>
        </div>
      </div>
      
      <footer class="portal-footer">
        <p>系统版本 V2.0.0 · NEXUS AI Core Active · 证券级加密通道</p>
      </footer>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { useRouter } from 'vue-router'
import {
  Cpu,
  Histogram,
  TrendCharts,
  Wallet,
  DataLine,
  List,
  Star,
  Setting,
  ArrowDown
} from '@element-plus/icons-vue'
import { getCurrentUser, isAdmin, logout } from '../utils/auth.js'
import ThemeSwitcher from '../components/layout/ThemeSwitcher.vue'
import CyberBackground from '../components/layout/CyberBackground.vue'

const router = useRouter()

const currentUser = computed(() => getCurrentUser() || {})
const displayName = computed(() => currentUser.value.nickname || currentUser.value.username || '用户')
const userInitial = computed(() => displayName.value.slice(0, 1).toUpperCase())
const roleLabel = computed(() => {
  const roleCode = currentUser.value.roleCode || currentUser.value.role
  return {
    admin: '管理员',
    user: '普通用户',
    trader: '交易用户',
  }[roleCode] || '平台用户'
})

const handleLogout = () => {
  logout()
  router.push('/login')
}

const subsystems = [
  { name: 'AI 研判工作台', desc: '深度学习模型与多维度大盘研判', path: '/ai-analysis', icon: Cpu },
  { name: '实时市场行情', desc: '全市场极速行情与板块异动', path: '/market', icon: Histogram },
  { name: '量化策略中心', desc: '多因子选股与策略回测分析', path: '/strategy', icon: TrendCharts },
  { name: '核心交易台', desc: '算法交易与多账户委托管理', path: '/trading', icon: Wallet },
  { name: '全局股票池', desc: '核心资产池与动态调仓跟踪', path: '/stock-pool', icon: DataLine },
  { name: '风控与资产', desc: '持仓风险评估与绩效归因', path: '/positions', icon: List },
  { name: '智能推荐系统', desc: '个性化资讯与交易标的推荐', path: '/recommendations', icon: Star },
  { name: '平台系统设置', desc: '权限管理与终端参数配置', path: '/settings', icon: Setting }
]

const navigateTo = (path) => {
  router.push(path)
}
</script>

<style scoped lang="scss">
.portal-container {
  width: 100vw;
  height: 100vh;
  position: relative;
  overflow: hidden;
  display: flex;
  justify-content: center;
  align-items: center;
  font-family: 'Inter', 'PingFang SC', 'Microsoft YaHei', sans-serif;
  background: transparent;
}

.portal-top-bar {
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  padding: 24px 40px;
  display: flex;
  justify-content: space-between;
  align-items: center;
  z-index: 10;
}

.logo .glow-title {
  margin: 0;
  font-size: 1.5rem;
  font-weight: 800;
  color: var(--text-emphasis);
  letter-spacing: 2px;
}

.top-bar-actions {
  display: flex;
  align-items: center;
  gap: 16px;
}

.user-dropdown {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 6px 12px 6px 6px;
  cursor: pointer;
  border-radius: 99px !important;
  color: var(--text-primary);
  transition: transform 0.2s;
}

.user-dropdown:hover {
  transform: translateY(-1px);
}

.user-copy {
  display: flex;
  flex-direction: column;
  line-height: 1.2;
}

.user-copy strong {
  font-size: 13px;
  font-weight: 600;
  color: var(--text-emphasis);
}

.user-copy span {
  font-size: 11px;
  color: var(--text-muted);
  margin-top: 2px;
}

.portal-content {
  position: relative;
  z-index: 2;
  display: flex;
  flex-direction: column;
  align-items: center;
  width: 100%;
  max-width: 1300px;
  padding: 40px;
}

.portal-header {
  text-align: center;
  margin-bottom: 50px;
}

.portal-title {
  font-size: 2.8rem;
  letter-spacing: 4px;
  margin: 0 0 12px 0;
  font-weight: 700;
  color: var(--text-emphasis);
}

.portal-subtitle {
  font-size: 1rem;
  letter-spacing: 6px;
  color: var(--text-secondary);
  margin: 0;
}

.portal-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 24px;
  width: 100%;
}

.module-card {
  display: flex;
  flex-direction: column;
  padding: 30px 24px;
  cursor: pointer;
  transition: all 0.3s cubic-bezier(0.25, 0.8, 0.25, 1);
  text-align: center;
}

.module-card:hover {
  transform: translateY(-8px);
  border-color: color-mix(in srgb, var(--accent) 40%, transparent) !important;
  box-shadow: 0 16px 40px color-mix(in srgb, var(--accent) 15%, transparent) !important;
}

.module-icon-wrap {
  display: flex;
  justify-content: center;
  align-items: center;
  width: 64px;
  height: 64px;
  margin: 0 auto 20px;
  border-radius: 16px;
  background: color-mix(in srgb, var(--accent) 10%, var(--surface-soft));
  color: var(--accent);
  transition: all 0.3s ease;
}

.module-card:hover .module-icon-wrap {
  background: var(--accent);
  color: #fff;
  box-shadow: 0 8px 24px color-mix(in srgb, var(--accent) 40%, transparent);
}

.module-icon {
  font-size: 32px;
}

.module-info {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.module-name {
  margin: 0;
  font-size: 1.1rem;
  font-weight: 600;
  color: var(--text-emphasis);
  letter-spacing: 1px;
}

.module-desc {
  margin: 0;
  font-size: 0.85rem;
  color: var(--text-secondary);
  line-height: 1.5;
}

.portal-footer {
  margin-top: 60px;
  color: var(--text-muted);
  font-size: 0.85rem;
  letter-spacing: 1px;
}

@media (max-width: 1200px) {
  .portal-grid {
    grid-template-columns: repeat(3, 1fr);
  }
}

@media (max-width: 900px) {
  .portal-grid {
    grid-template-columns: repeat(2, 1fr);
  }
}

@media (max-width: 600px) {
  .portal-grid {
    grid-template-columns: 1fr;
  }
}
</style>
