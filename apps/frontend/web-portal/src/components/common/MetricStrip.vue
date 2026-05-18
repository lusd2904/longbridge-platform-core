<template>
  <section class="metric-strip" :class="{ compact }">
    <article v-for="item in items" :key="item.label" class="metric-strip__item">
      <span class="metric-strip__label">{{ item.label }}</span>
      <strong class="metric-strip__value" :class="resolveTone(item.tone)">{{ item.value }}</strong>
      <small v-if="showNotes && item.note" class="metric-strip__note">{{ item.note }}</small>
    </article>
  </section>
</template>

<script setup>
const toneAliasMap = {
  up: 'healthy',
  positive: 'healthy',
  down: 'error',
  negative: 'error',
  neutral: 'info'
}

const resolveTone = (tone = '') => toneAliasMap[tone] || tone

defineProps({
  items: {
    type: Array,
    default: () => []
  },
  compact: {
    type: Boolean,
    default: false
  },
  showNotes: {
    type: Boolean,
    default: false
  }
})
</script>

<style scoped lang="scss">
.metric-strip {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(132px, 1fr));
  gap: 8px;
}

.metric-strip__item {
  display: grid;
  gap: 3px;
  padding: 7px 8px;
  border-radius: 8px;
  border: 1px solid color-mix(in srgb, var(--border-soft) 84%, transparent);
  background: var(--page-card-bg);
  box-shadow: var(--page-card-shadow);
  min-width: 0;
}

.metric-strip__label,
.metric-strip__note {
  color: var(--text-muted);
  font-size: 11px;
  line-height: 1.4;
}

.metric-strip__value {
  color: var(--text-emphasis);
  font-size: 14px;
  line-height: 1.15;
}

.metric-strip__value.healthy {
  color: var(--success);
}

.metric-strip__value.success {
  color: color-mix(in srgb, var(--success) 84%, white 16%);
}

.metric-strip__value.info {
  color: color-mix(in srgb, var(--accent-strong, var(--accent)) 88%, white 12%);
}

.metric-strip__value.warning {
  color: var(--warning);
}

.metric-strip__value.error {
  color: var(--danger);
}

.metric-strip.compact {
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 8px;
}

.metric-strip.compact .metric-strip__item {
  padding: 7px;
  border-radius: 8px;
}

@media (max-width: 640px) {
  .metric-strip {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}
</style>
