<script setup lang="ts">
import { useRecentHistory } from '../composables/useRecentHistory'
import { timeAgo } from '../utils/time'

const emit = defineEmits<{
  select: [id: string]
}>()

const { history, clearHistory, removeEntry } = useRecentHistory()

function getStatusClass(status: string): string {
  switch (status) {
    case 'completed': return 'status-completed'
    case 'processing': return 'status-processing'
    case 'failed': return 'status-failed'
    default: return 'status-pending'
  }
}

function getStatusText(status: string): string {
  switch (status) {
    case 'completed': return '已完成'
    case 'processing': return '处理中'
    case 'failed': return '失败'
    default: return '等待中'
  }
}

function handleClick(id: string) {
  emit('select', id)
}
</script>

<template>
  <div class="recent-history" v-if="history.length > 0">
    <div class="history-header">
      <h3>
        <span class="icon">🕐</span>
        最近分析
      </h3>
      <button class="clear-btn" @click="clearHistory" title="清除历史">
        清除
      </button>
    </div>

    <div class="history-list">
      <div
        v-for="item in history"
        :key="item.id"
        class="history-item"
        @click="handleClick(item.id)"
      >
        <div class="item-icon">🎬</div>
        <div class="item-info">
          <div class="item-name">{{ item.filename }}</div>
          <div class="item-meta">
            <span :class="['item-status', getStatusClass(item.status)]">
              {{ getStatusText(item.status) }}
            </span>
            <span class="item-time">{{ timeAgo(item.createdAt) }}</span>
          </div>
        </div>
        <button
          class="remove-btn"
          @click.stop="removeEntry(item.id)"
          title="删除"
        >
          &times;
        </button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.recent-history {
  background: var(--bg-secondary);
  border: 1px solid var(--border-primary);
  border-radius: var(--radius-lg);
  padding: var(--space-4);
}

.history-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: var(--space-3);
}

.history-header h3 {
  font-size: var(--text-sm);
  font-weight: 600;
  color: var(--text-primary);
  display: flex;
  align-items: center;
  gap: var(--space-2);
}

.history-header .icon {
  font-size: 1.1em;
}

.clear-btn {
  padding: var(--space-1) var(--space-2);
  background: transparent;
  border: 1px solid var(--border-secondary);
  border-radius: var(--radius-sm);
  color: var(--text-muted);
  font-size: var(--text-xs);
  cursor: pointer;
  transition: all var(--transition-fast);
}

.clear-btn:hover {
  background: var(--bg-hover);
  color: var(--text-secondary);
  border-color: var(--text-muted);
}

.history-list {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
}

.history-item {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  padding: var(--space-2) var(--space-3);
  background: var(--bg-primary);
  border: 1px solid var(--border-secondary);
  border-radius: var(--radius-md);
  cursor: pointer;
  transition: all var(--transition-fast);
}

.history-item:hover {
  background: var(--bg-hover);
  border-color: var(--accent-blue);
}

.item-icon {
  font-size: 1.2rem;
  flex-shrink: 0;
}

.item-info {
  flex: 1;
  min-width: 0;
}

.item-name {
  font-size: var(--text-sm);
  font-weight: 500;
  color: var(--text-primary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.item-meta {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  margin-top: var(--space-1);
}

.item-status {
  font-size: var(--text-xs);
  font-weight: 600;
  text-transform: uppercase;
  padding: 1px 6px;
  border-radius: var(--radius-full);
}

.status-completed {
  background: rgba(63, 185, 80, 0.15);
  color: var(--accent-green);
}

.status-processing {
  background: rgba(88, 166, 255, 0.15);
  color: var(--accent-blue);
}

.status-failed {
  background: rgba(248, 81, 73, 0.15);
  color: var(--accent-red);
}

.status-pending {
  background: rgba(139, 148, 158, 0.15);
  color: var(--text-secondary);
}

.item-time {
  font-size: var(--text-xs);
  color: var(--text-muted);
}

.remove-btn {
  width: 24px;
  height: 24px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: transparent;
  border: none;
  border-radius: var(--radius-sm);
  color: var(--text-muted);
  font-size: 1.1rem;
  cursor: pointer;
  transition: all var(--transition-fast);
  flex-shrink: 0;
}

.remove-btn:hover {
  background: rgba(248, 81, 73, 0.15);
  color: var(--accent-red);
}
</style>
