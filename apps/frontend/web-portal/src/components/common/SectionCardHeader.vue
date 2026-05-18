<template>
  <div class="section-card-header">
    <div class="section-card-header__copy">
      <div class="section-card-header__title-row">
        <h3 class="section-card-header__title">{{ title }}</h3>
        <el-tag v-if="badge" size="small" :type="badgeType">{{ badge }}</el-tag>
      </div>
      <p v-if="showDescription && description" class="section-card-header__description">{{ description }}</p>
    </div>

    <div v-if="$slots.actions" class="section-card-header__actions">
      <slot name="actions" />
    </div>
  </div>
</template>

<script setup>
defineProps({
  eyebrow: {
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
  badge: {
    type: String,
    default: ''
  },
  badgeType: {
    type: String,
    default: 'info'
  },
  showDescription: {
    type: Boolean,
    default: false
  }
})
</script>

<style scoped lang="scss">
.section-card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  flex-wrap: wrap;
}

.section-card-header__copy {
  display: grid;
  gap: 2px;
  min-width: 0;
}

.section-card-header__eyebrow {
  color: var(--text-muted);
  font-size: 10px;
  letter-spacing: 0.12em;
  text-transform: uppercase;
}

.section-card-header__title-row {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
}

.section-card-header__title {
  margin: 0;
  color: var(--text-emphasis);
  font-size: 14px;
  line-height: 1.2;
}

.section-card-header__description {
  margin: 0;
  color: var(--text-muted);
  font-size: 13px;
  line-height: 1.6;
}

.section-card-header__actions {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
}
</style>
