<template>
  <section class="page-hero hero-panel" :class="{ compact }">
    <div class="page-hero__main">
      <div class="page-hero__copy hero-copy">
        <h1 class="page-hero__title">{{ title }}</h1>
        <p v-if="showDescription && description" class="page-hero__description">{{ description }}</p>

        <div v-if="chips.length" class="page-hero__chips hero-tags">
          <span
            v-for="chip in chips"
            :key="chip.text"
            class="page-hero__chip hero-tag"
            :class="[chip.tone, chip.className]"
          >
            {{ chip.text }}
          </span>
        </div>
      </div>

      <div v-if="$slots.actions" class="page-hero__actions">
        <slot name="actions" />
      </div>
    </div>

    <div v-if="metrics.length || $slots.aside" class="page-hero__footer">
      <div v-if="metrics.length" class="page-hero__metrics">
        <article v-for="item in metrics" :key="item.label" class="page-hero__metric">
          <span class="page-hero__metric-label">{{ item.label }}</span>
          <strong class="page-hero__metric-value" :class="item.tone">{{ item.value }}</strong>
          <small v-if="showMetricNotes && item.note" class="page-hero__metric-note">{{ item.note }}</small>
        </article>
      </div>

      <aside v-if="$slots.aside" class="page-hero__aside">
        <slot name="aside" />
      </aside>
    </div>
  </section>
</template>

<script setup>
defineProps({
  kicker: {
    type: String,
    default: ''
  },
  title: {
    type: String,
    default: ''
  },
  description: {
    type: String,
    default: ''
  },
  chips: {
    type: Array,
    default: () => []
  },
  metrics: {
    type: Array,
    default: () => []
  },
  compact: {
    type: Boolean,
    default: false
  },
  showDescription: {
    type: Boolean,
    default: false
  },
  showMetricNotes: {
    type: Boolean,
    default: false
  }
})
</script>

<style scoped lang="scss">
.page-hero {
  display: grid;
  gap: 8px;
  padding: 10px 12px;
}

.page-hero__main {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 10px;
  flex-wrap: wrap;
}

.page-hero__copy {
  min-width: 0;
  flex: 1;
}

.page-hero__title {
  margin: 0;
  font-size: 20px;
  line-height: 1.16;
  letter-spacing: 0;
}

.page-hero__description {
  max-width: 760px;
}

.page-hero__actions {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 8px;
  flex-wrap: wrap;
}

.page-hero__footer {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 8px;
  align-items: stretch;
}

.page-hero__metrics {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(112px, 1fr));
  gap: 8px;
}

.page-hero__metric {
  display: grid;
  gap: 3px;
  padding: 7px 8px;
  border-radius: 8px;
  border: 1px solid color-mix(in srgb, var(--border-soft) 84%, transparent);
  background: color-mix(in srgb, var(--surface-soft) 92%, transparent);
  min-width: 0;
}

.page-hero__metric-label,
.page-hero__metric-note {
  color: var(--text-muted);
  font-size: 11px;
}

.page-hero__metric-value {
  color: var(--text-emphasis);
  font-size: 14px;
  line-height: 1.15;
}

.page-hero__metric-value.healthy,
.page-hero__chip.healthy {
  color: var(--success);
}

.page-hero__metric-value.success,
.page-hero__chip.success {
  color: color-mix(in srgb, var(--success) 84%, white 16%);
}

.page-hero__metric-value.info,
.page-hero__chip.info {
  color: color-mix(in srgb, var(--accent-strong, var(--accent)) 88%, white 12%);
}

.page-hero__metric-value.warning,
.page-hero__chip.warning {
  color: var(--warning);
}

.page-hero__metric-value.error,
.page-hero__chip.error {
  color: var(--danger);
}

.page-hero__aside {
  display: flex;
  min-width: min(100%, 220px);
}

.page-hero.compact {
  padding: 8px 10px;
  gap: 8px;
}

@media (max-width: 900px) {
  .page-hero__footer {
    grid-template-columns: 1fr;
  }

  .page-hero__actions {
    width: 100%;
    justify-content: flex-start;
  }
}

@media (max-width: 640px) {
  .page-hero {
    padding: 9px;
    border-radius: 10px;
  }

  .page-hero__metrics {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}
</style>
