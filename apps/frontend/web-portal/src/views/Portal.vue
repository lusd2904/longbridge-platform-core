<template>
  <div class="portal-container">
    <div class="portal-background"></div>
    <div class="portal-content">
      <header class="portal-header">
        <h1 class="portal-title">量化交易与 AI 研判综合指挥中心</h1>
        <p class="portal-subtitle">QUANTITATIVE TRADING & AI ANALYSIS COMMAND CENTER</p>
      </header>

      <div class="hexagon-grid">
        <div 
          v-for="(subsystem, index) in subsystems" 
          :key="subsystem.name"
          class="hexagon-item"
          @click="navigateTo(subsystem.path)"
        >
          <div class="hexagon-inner" :class="`hexagon-color-${(index % 4) + 1}`">
            <div class="hexagon-content">
              <el-icon class="subsystem-icon"><component :is="subsystem.icon" /></el-icon>
              <span class="subsystem-name">{{ subsystem.name }}</span>
            </div>
          </div>
        </div>
      </div>
      
      <footer class="portal-footer">
        <p>系统版本 V2.0.0 · NVIDIA AI Core Active · 证券级加密通道</p>
      </footer>
    </div>
  </div>
</template>

<script setup>
import { useRouter } from 'vue-router'
import {
  Cpu,
  Histogram,
  TrendCharts,
  Wallet,
  DataLine,
  List,
  Star,
  Setting
} from '@element-plus/icons-vue'

const router = useRouter()

const subsystems = [
  { name: 'AI 研判工作台', path: '/ai-analysis', icon: Cpu },
  { name: '实时市场行情', path: '/market', icon: Histogram },
  { name: '量化策略中心', path: '/strategy', icon: TrendCharts },
  { name: '核心交易台', path: '/trading', icon: Wallet },
  { name: '全局股票池', path: '/stock-pool', icon: DataLine },
  { name: '风控与资产', path: '/positions', icon: List },
  { name: '智能推荐系统', path: '/recommendations', icon: Star },
  { name: '平台系统设置', path: '/settings', icon: Setting }
]

const navigateTo = (path) => {
  router.push(path)
}
</script>

<style scoped>
.portal-container {
  width: 100vw;
  height: 100vh;
  position: relative;
  overflow: hidden;
  display: flex;
  justify-content: center;
  align-items: center;
  font-family: 'PingFang SC', 'Microsoft YaHei', sans-serif;
}

.portal-background {
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  /* Dark tech blue gradient background imitating smart city */
  background: radial-gradient(circle at 50% 50%, #1e3a8a 0%, #0f172a 100%);
  background-size: cover;
  z-index: 1;
}

/* Add a subtle grid overlay for tech feel */
.portal-background::after {
  content: '';
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background-image: 
    linear-gradient(rgba(255, 255, 255, 0.05) 1px, transparent 1px),
    linear-gradient(90deg, rgba(255, 255, 255, 0.05) 1px, transparent 1px);
  background-size: 30px 30px;
  pointer-events: none;
}

.portal-content {
  position: relative;
  z-index: 2;
  display: flex;
  flex-direction: column;
  align-items: center;
  width: 100%;
  max-width: 1200px;
  padding: 40px;
}

.portal-header {
  text-align: center;
  margin-bottom: 60px;
  color: #fff;
  text-shadow: 0 2px 10px rgba(0, 195, 255, 0.5);
}

.portal-title {
  font-size: 2.5rem;
  letter-spacing: 4px;
  margin: 0 0 10px 0;
  font-weight: 600;
  background: linear-gradient(to right, #60a5fa, #c084fc);
  -webkit-background-clip: text;
  color: transparent;
  text-shadow: none;
}

.portal-subtitle {
  font-size: 0.9rem;
  letter-spacing: 8px;
  color: #94a3b8;
  margin: 0;
}

.hexagon-grid {
  display: flex;
  flex-wrap: wrap;
  justify-content: center;
  gap: 30px;
  max-width: 900px;
  padding: 20px;
}

.hexagon-item {
  width: 160px;
  height: 180px;
  position: relative;
  cursor: pointer;
  filter: drop-shadow(0 0 10px rgba(0, 0, 0, 0.3));
  transition: all 0.3s cubic-bezier(0.25, 0.8, 0.25, 1);
  margin: 10px;
}

.hexagon-item:hover {
  transform: translateY(-10px);
  filter: drop-shadow(0 15px 25px rgba(0, 195, 255, 0.5));
}

.hexagon-inner {
  position: absolute;
  top: 0;
  left: 0;
  width: 100%;
  height: 100%;
  /* The hexagon shape */
  clip-path: polygon(50% 0%, 100% 25%, 100% 75%, 50% 100%, 0% 75%, 0% 25%);
  display: flex;
  justify-content: center;
  align-items: center;
  color: white;
  transition: all 0.3s ease;
}

/* Different tech color presets for the hexagons */
.hexagon-color-1 {
  background: linear-gradient(135deg, #3b82f6, #2563eb);
  box-shadow: inset 0 0 20px rgba(255,255,255,0.3);
}
.hexagon-color-2 {
  background: linear-gradient(135deg, #10b981, #059669);
  box-shadow: inset 0 0 20px rgba(255,255,255,0.3);
}
.hexagon-color-3 {
  background: linear-gradient(135deg, #8b5cf6, #7c3aed);
  box-shadow: inset 0 0 20px rgba(255,255,255,0.3);
}
.hexagon-color-4 {
  background: linear-gradient(135deg, #f59e0b, #d97706);
  box-shadow: inset 0 0 20px rgba(255,255,255,0.3);
}

.hexagon-content {
  display: flex;
  flex-direction: column;
  align-items: center;
  text-align: center;
  padding: 20px;
}

.subsystem-icon {
  font-size: 3rem;
  margin-bottom: 12px;
  filter: drop-shadow(0 2px 4px rgba(0,0,0,0.3));
}

.subsystem-name {
  font-size: 1rem;
  font-weight: 500;
  letter-spacing: 1px;
  text-shadow: 0 1px 3px rgba(0,0,0,0.5);
}

.portal-footer {
  margin-top: 80px;
  color: #475569;
  font-size: 0.85rem;
  letter-spacing: 1px;
}
</style>
