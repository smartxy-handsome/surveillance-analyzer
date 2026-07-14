<script setup lang="ts">
import { onMounted } from 'vue'
import { useJobsStore } from '../stores/jobs'

const emit = defineEmits<{ select: [id: string] }>()
const store = useJobsStore()

onMounted(() => store.fetchJobs())

function getStatusClass(status: string): string {
  switch (status) {
    case 'completed': return 'badge-completed'
    case 'processing': return 'badge-processing'
    case 'failed': return 'badge-failed'
    default: return 'badge-pending'
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
</script>

<template>
  <div class="job-list">
    <h2>
      <span class="icon">📋</span>
      分析任务
    </h2>
    <div v-if="store.loading" class="loading">
      <span class="spinner">⏳</span> 加载中...
    </div>
    <div v-else-if="store.jobs.length === 0" class="empty">
      <span class="empty-icon">📭</span>
      暂无任务，请先分析一个视频。
    </div>
    <div v-else class="table-wrapper">
      <table>
        <thead>
          <tr>
            <th>文件名</th>
            <th>状态</th>
            <th>时间段</th>
            <th>有人时长</th>
            <th>操作</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="job in store.jobs" :key="job.id" class="table-row">
            <td class="filename">
              <span class="file-icon">🎬</span>
              {{ job.filename }}
            </td>
            <td>
              <span :class="['badge', getStatusClass(job.status)]">
                {{ getStatusText(job.status) }}
              </span>
            </td>
            <td class="number">{{ job.total_segments }}</td>
            <td class="number">{{ job.total_person_time.toFixed(1) }}秒</td>
            <td class="actions">
              <button class="btn-action btn-view" @click="emit('select', job.id)">
                👁️ 查看
              </button>
              <button class="btn-action btn-delete" @click="store.removeJob(job.id)">
                🗑️
              </button>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>

<style scoped>
.job-list {
  background: var(--bg-secondary);
  border: 1px solid var(--border-primary);
  border-radius: var(--radius-lg);
  padding: var(--space-6);
  transition: all var(--transition-normal);
}

.job-list:hover {
  border-color: rgba(88, 166, 255, 0.2);
}

h2 {
  margin-bottom: var(--space-4);
  font-size: var(--text-lg);
  font-weight: 600;
  display: flex;
  align-items: center;
  gap: var(--space-2);
}

h2 .icon {
  font-size: 1.2em;
}

.loading,
.empty {
  padding: var(--space-8);
  text-align: center;
  color: var(--text-secondary);
  font-size: var(--text-sm);
}

.loading .spinner {
  display: inline-block;
  animation: spin 1s linear infinite;
}

.empty-icon {
  display: block;
  font-size: 2rem;
  margin-bottom: var(--space-2);
}

.table-wrapper {
  overflow-x: auto;
}

table {
  width: 100%;
  border-collapse: collapse;
}

th {
  text-align: left;
  padding: var(--space-3) var(--space-4);
  font-size: var(--text-xs);
  font-weight: 600;
  color: var(--text-muted);
  text-transform: uppercase;
  letter-spacing: 0.5px;
  border-bottom: 1px solid var(--border-primary);
}

td {
  padding: var(--space-3) var(--space-4);
  font-size: var(--text-sm);
  border-bottom: 1px solid var(--border-secondary);
  transition: background var(--transition-fast);
}

.table-row {
  transition: all var(--transition-fast);
}

.table-row:hover td {
  background: var(--bg-hover);
}

.filename {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  font-weight: 500;
}

.file-icon {
  font-size: 1.1em;
}

.number {
  font-family: var(--font-mono);
  color: var(--text-secondary);
}

.actions {
  display: flex;
  gap: var(--space-2);
}

.btn-action {
  padding: var(--space-1) var(--space-3);
  background: var(--bg-tertiary);
  border: 1px solid var(--border-secondary);
  border-radius: var(--radius-sm);
  color: var(--text-secondary);
  font-size: var(--text-xs);
  cursor: pointer;
  transition: all var(--transition-fast);
}

.btn-action:hover {
  background: var(--bg-hover);
  border-color: var(--text-muted);
}

.btn-view:hover {
  color: var(--accent-blue);
  border-color: var(--accent-blue);
}

.btn-delete {
  padding: var(--space-1) var(--space-2);
}

.btn-delete:hover {
  color: var(--accent-red);
  border-color: var(--accent-red);
}

@keyframes spin {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}

@media (max-width: 640px) {
  th:nth-child(3),
  td:nth-child(3),
  th:nth-child(4),
  td:nth-child(4) {
    display: none;
  }
}
</style>
