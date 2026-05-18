<template>
  <div class="readmodel-source-strip" :class="{ compact }">
    <div v-if="label || (showDetail && detail)" class="source-copy">
      <span class="source-label">{{ label }}</span>
      <strong v-if="showDetail && detail" class="source-detail">{{ detail }}</strong>
    </div>
    <div class="source-meta">
      <el-tag v-if="statusText" size="small" :type="statusType">{{ statusText }}</el-tag>
      <el-tag
        v-for="(tag, index) in tags"
        :key="`${tag.text}-${index}`"
        size="small"
        :type="tag.type || 'info'"
      >
        {{ tag.text }}
      </el-tag>
      <span v-if="updatedAt" class="source-time">{{ updatedPrefix }} {{ updatedAt }}</span>
    </div>
  </div>
</template>

<script setup>
defineProps({
  label: { type: String, default: '' },
  detail: { type: String, default: '' },
  statusText: { type: String, default: '' },
  statusType: { type: String, default: 'info' },
  updatedAt: { type: String, default: '' },
  updatedPrefix: { type: String, default: '更新于' },
  compact: { type: Boolean, default: false },
  showDetail: { type: Boolean, default: false },
  tags: {
    type: Array,
    default: () => []
  }
})
</script>

<style scoped lang="scss">
.readmodel-source-strip {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  padding: 6px 8px;
  border-radius: 8px;
  border: 1px solid var(--border-soft);
  background: color-mix(in srgb, var(--surface-soft) 92%, transparent);

  &.compact {
    padding: 5px 7px;
  }
}

.source-copy,
.source-meta {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
}

.source-copy {
  min-width: 0;
}

.source-label,
.source-time {
  color: var(--text-muted);
  font-size: 11px;
}

.source-detail {
  color: var(--text-primary);
  font-size: 11px;
  line-height: 1.5;
}

@media (max-width: 860px) {
  .readmodel-source-strip {
    align-items: flex-start;
    flex-direction: column;
  }
}
</style>
