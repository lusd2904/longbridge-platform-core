<template>
  <div class="mobile-segment-control" role="tablist" :aria-label="label">
    <button
      v-for="item in items"
      :key="item.value"
      type="button"
      class="segment-button"
      :class="{ active: item.value === modelValue }"
      :aria-selected="item.value === modelValue"
      @click="$emit('update:modelValue', item.value)"
    >
      <span class="segment-title">{{ item.label }}</span>
    </button>
  </div>
</template>

<script setup>
defineProps({
  items: {
    type: Array,
    default: () => []
  },
  label: {
    type: String,
    default: '页面分段'
  },
  modelValue: {
    type: String,
    default: ''
  }
})

defineEmits(['update:modelValue'])
</script>

<style scoped lang="scss">
.mobile-segment-control {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(76px, 1fr));
  gap: 6px;
}

.segment-button {
  min-height: 42px;
  padding: 7px 8px;
  display: grid;
  gap: 2px;
  align-content: center;
  justify-items: flex-start;
  border: 1px solid color-mix(in srgb, var(--accent) 12%, var(--border-soft));
  border-radius: 9px;
  background:
    linear-gradient(180deg, rgba(255, 255, 255, 0.08), rgba(255, 255, 255, 0.02)),
    color-mix(in srgb, var(--surface-strong) 88%, black 12%);
  color: var(--text-secondary);
  box-shadow: 0 10px 24px rgba(3, 10, 24, 0.14);
  text-align: left;
  transition: transform 0.2s ease, border-color 0.2s ease, background 0.2s ease, color 0.2s ease;
}

.segment-button.active {
  border-color: color-mix(in srgb, var(--accent) 38%, transparent);
  background:
    linear-gradient(135deg, rgba(120, 230, 255, 0.2), rgba(83, 185, 255, 0.08)),
    color-mix(in srgb, var(--surface-strong) 84%, black 16%);
  color: var(--text-emphasis);
  transform: translateY(-1px);
}

.segment-title {
  font-size: 12px;
  font-weight: 700;
}

</style>
