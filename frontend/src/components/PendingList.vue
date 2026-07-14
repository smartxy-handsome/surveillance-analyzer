<script setup lang="ts">
import type { PendingItem } from '../utils/submitItems'

defineProps<{ items: PendingItem[] }>()
const emit = defineEmits<{
  remove: [id: string]
  submit: []
}>()
</script>

<template>
  <div v-if="items.length > 0" class="pending-list">
    <div class="header">
      <span class="title">📋 待提交清单 ({{ items.length }})</span>
      <span class="hint">逐条提交，失败的会标红</span>
    </div>

    <div
      v-for="item in items"
      :key="item.id"
      class="item"
      :class="{ error: item.status === 'error', submitting: item.status === 'submitting' }"
    >
      <span class="icon">🎬</span>
      <span class="filename">{{ item.filename }}</span>
      <span class="path">{{ item.path }}</span>
      <span v-if="item.status === 'submitting'" class="status">⏳</span>
      <span v-else-if="item.status === 'error'" class="error-msg">{{ item.error }}</span>
      <button class="remove" title="移除" @click="emit('remove', item.id)">✕</button>
    </div>

    <button class="submit-btn" @click="emit('submit')">
      ▶ 开始分析 ({{ items.length }})
    </button>
  </div>
</template>

<style scoped>
.pending-list {
  margin-top: var(--space-4);
  background: var(--bg-primary);
  border: 1px solid var(--border-secondary);
  border-radius: var(--radius-md);
  padding: var(--space-3) var(--space-4);
}

.header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: var(--space-2);
}

.title {
  font-weight: 600;
  font-size: var(--text-sm);
}

.hint {
  font-size: var(--text-xs);
  color: var(--text-muted);
}

.item {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  padding: var(--space-2) 0;
  border-bottom: 1px solid var(--border-secondary);
  font-size: var(--text-sm);
}

.item.error {
  background: rgba(248, 81, 73, 0.08);
}

.icon {
  flex-shrink: 0;
}

.filename {
  font-weight: 500;
  color: var(--text-primary);
}

.path {
  flex: 1;
  font-family: var(--font-mono);
  font-size: var(--text-xs);
  color: var(--text-muted);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.status {
  color: var(--accent-blue);
}

.error-msg {
  color: var(--accent-red);
  font-size: var(--text-xs);
  flex: 1;
}

.remove {
  background: transparent;
  border: none;
  color: var(--text-muted);
  cursor: pointer;
  font-size: var(--text-sm);
  padding: 0 var(--space-1);
}

.remove:hover {
  color: var(--accent-red);
}

.submit-btn {
  margin-top: var(--space-3);
  padding: var(--space-2) var(--space-5);
  background: var(--gradient-blue);
  border: none;
  border-radius: var(--radius-md);
  color: white;
  font-size: var(--text-sm);
  font-weight: 600;
  cursor: pointer;
  transition: all var(--transition-fast);
}

.submit-btn:hover {
  box-shadow: var(--shadow-glow-blue);
}
</style>
