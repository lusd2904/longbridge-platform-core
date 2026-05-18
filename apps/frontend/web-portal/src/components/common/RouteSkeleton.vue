<template>
  <div class="route-skeleton">
    <div class="skeleton-hero">
      <el-skeleton-item variant="h1" class="skeleton-title" />
      <el-skeleton-item variant="text" class="skeleton-subtitle" />
    </div>
    <div class="skeleton-stats">
      <div v-for="item in 4" :key="item" class="skeleton-stat-card">
        <el-skeleton-item variant="circle" class="skeleton-stat-icon" />
        <div class="skeleton-stat-copy">
          <el-skeleton-item variant="text" class="skeleton-line short" />
          <el-skeleton-item variant="text" class="skeleton-line" />
        </div>
      </div>
    </div>
    <div class="skeleton-panels">
      <div v-for="item in 2" :key="item" class="skeleton-panel">
        <el-skeleton-item variant="text" class="skeleton-line medium" />
        <el-skeleton :rows="6" animated />
      </div>
    </div>
  </div>
</template>

<style scoped lang="scss">
.route-skeleton {
  display: flex;
  flex-direction: column;
  gap: 18px;
  padding: 4px;
}

.skeleton-hero,
.skeleton-stat-card,
.skeleton-panel {
  border-radius: 24px;
  border: 1px solid var(--border-soft);
  background: var(--panel-surface);
  box-shadow: var(--shadow-strong), var(--panel-inset);
  backdrop-filter: var(--panel-backdrop);
}

.skeleton-hero {
  padding: 22px 24px;
}

.skeleton-title {
  width: 240px;
  height: 28px;
  margin-bottom: 14px;
}

.skeleton-subtitle {
  width: min(620px, 100%);
  height: 14px;
}

.skeleton-stats,
.skeleton-panels {
  display: grid;
  gap: 16px;
}

.skeleton-stats {
  grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
}

.skeleton-panels {
  grid-template-columns: repeat(auto-fit, minmax(320px, 1fr));
}

.skeleton-stat-card {
  display: flex;
  align-items: center;
  gap: 14px;
  padding: 18px 20px;
}

.skeleton-stat-icon {
  width: 48px;
  height: 48px;
  flex: 0 0 48px;
}

.skeleton-stat-copy {
  flex: 1;
}

.skeleton-panel {
  padding: 20px;
}

.skeleton-line {
  width: 100%;
  height: 14px;
}

.skeleton-line.short {
  width: 40%;
  margin-bottom: 10px;
}

.skeleton-line.medium {
  width: 30%;
  margin-bottom: 16px;
}

@media (max-width: 768px) {
  .skeleton-panels {
    grid-template-columns: 1fr;
  }
}
</style>
