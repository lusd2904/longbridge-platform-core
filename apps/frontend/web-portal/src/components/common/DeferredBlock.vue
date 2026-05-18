<template>
  <div class="deferred-block" :style="blockStyle">
    <slot v-if="ready" />
    <slot v-else name="fallback">
      <div class="deferred-block__fallback" />
    </slot>
  </div>
</template>

<script setup>
import { computed, onBeforeUnmount, ref, watch } from 'vue'

const props = defineProps({
  active: {
    type: Boolean,
    default: true
  },
  delay: {
    type: Number,
    default: 120
  },
  minHeight: {
    type: [Number, String],
    default: 0
  }
})

const ready = ref(false)
let timer = null

const clearPending = () => {
  if (timer) {
    window.clearTimeout(timer)
    timer = null
  }
}

const blockStyle = computed(() => {
  if (!props.minHeight) {
    return {}
  }
  const value = typeof props.minHeight === 'number' ? `${props.minHeight}px` : props.minHeight
  return { minHeight: value }
})

watch(() => props.active, (active) => {
  clearPending()
  if (!active) {
    ready.value = false
    return
  }

  timer = window.setTimeout(() => {
    ready.value = true
    timer = null
  }, props.delay)
}, { immediate: true })

onBeforeUnmount(() => {
  clearPending()
})
</script>

<style scoped lang="scss">
.deferred-block {
  width: 100%;
}

.deferred-block__fallback {
  width: 100%;
  min-height: 100%;
  border-radius: 22px;
  background:
    linear-gradient(90deg, rgba(255, 255, 255, 0.04), rgba(255, 255, 255, 0.09), rgba(255, 255, 255, 0.04)),
    color-mix(in srgb, var(--surface-soft) 92%, transparent);
  background-size: 220% 100%;
  animation: deferred-shimmer 1.6s linear infinite;
}

@keyframes deferred-shimmer {
  from {
    background-position: 100% 0;
  }
  to {
    background-position: -100% 0;
  }
}
</style>
