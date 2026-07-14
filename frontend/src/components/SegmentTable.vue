<script setup lang="ts">
import type { Segment } from '../api/client'

defineProps<{ segments: Segment[] }>()

function getConfidenceColor(conf: number): string {
  if (conf >= 0.8) return 'var(--accent-green)'
  if (conf >= 0.6) return 'var(--accent-yellow)'
  return 'var(--accent-red)'
}
</script>

<template>
  <div class="segment-table">
    <table>
      <thead>
        <tr>
          <th>#</th>
          <th>开始</th>
          <th>结束</th>
          <th>时长</th>
          <th>检测次数</th>
          <th>平均置信度</th>
          <th>最高置信度</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="(seg, i) in segments" :key="seg.id" class="table-row">
          <td class="index">{{ i + 1 }}</td>
          <td class="time">{{ seg.start_time_formatted }}</td>
          <td class="time">{{ seg.end_time_formatted }}</td>
          <td class="duration">{{ seg.duration_seconds.toFixed(1) }}秒</td>
          <td class="count">{{ seg.detection_count }}</td>
          <td class="confidence">
            <span
              class="confidence-badge"
              :style="{ color: getConfidenceColor(seg.avg_confidence) }"
            >
              {{ (seg.avg_confidence * 100).toFixed(0) }}%
            </span>
          </td>
          <td class="confidence">
            <span
              class="confidence-badge"
              :style="{ color: getConfidenceColor(seg.max_confidence) }"
            >
              {{ (seg.max_confidence * 100).toFixed(0) }}%
            </span>
          </td>
        </tr>
      </tbody>
    </table>
  </div>
</template>

<style scoped>
.segment-table {
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

.table-row:hover td {
  background: var(--bg-hover);
}

.index {
  color: var(--text-muted);
  font-family: var(--font-mono);
}

.time {
  font-family: var(--font-mono);
  color: var(--text-secondary);
}

.duration {
  font-family: var(--font-mono);
  color: var(--text-primary);
}

.count {
  font-family: var(--font-mono);
  color: var(--text-secondary);
}

.confidence-badge {
  font-family: var(--font-mono);
  font-weight: 600;
}

@media (max-width: 640px) {
  th:nth-child(6),
  td:nth-child(6) {
    display: none;
  }
}
</style>
