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
  gap: 4px;
  padding: 4px;
  border: 1px solid var(--border-soft);
  border-radius: 10px;
  background: color-mix(in srgb, var(--surface-soft) 86%, transparent);
}

.view-switcher__item {
  min-width: 84px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  padding: 6px 10px;
  border: 0;
  border-radius: 8px;
  background: transparent;
  color: var(--text-muted);
  text-align: center;
  cursor: pointer;
  transition: background 0.2s ease, color 0.2s ease, transform 0.2s ease;
}

.view-switcher__item strong {
  font-size: 12px;
  line-height: 1.2;
  color: inherit;
}

.view-switcher__item.active {
  background: color-mix(in srgb, var(--accent) 16%, transparent);
  color: var(--text-emphasis);
}

.view-switcher__item:hover {
  transform: translateY(-1px);
}
</style>
