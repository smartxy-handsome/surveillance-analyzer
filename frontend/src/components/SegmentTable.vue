<script setup lang="ts">
import { computed, ref } from 'vue'
import type { Segment } from '../api/client'
import { confidenceTier } from '../utils/confidenceTier'

const props = defineProps<{ segments: Segment[] }>()

const showSuspected = ref(true)

const suspectedCount = computed(
  () => props.segments.filter((s) => confidenceTier(s.max_confidence) === 'suspected').length
)

const visibleSegments = computed(() =>
  props.segments
    .map((seg, originalIndex) => ({ seg, originalIndex }))
    .filter(
      ({ seg }) => showSuspected.value || confidenceTier(seg.max_confidence) === 'confirmed'
    )
)

function getConfidenceColor(conf: number): string {
  if (conf >= 0.8) return 'var(--accent-green)'
  if (conf >= 0.6) return 'var(--accent-yellow)'
  return 'var(--accent-red)'
}
</script>

<template>
  <div class="segment-table">
    <div class="table-toolbar" v-if="suspectedCount > 0">
      <label class="tier-toggle">
        <input type="checkbox" v-model="showSuspected" />
        显示疑似记录（{{ suspectedCount }} 条，置信度 &lt; 50%）
      </label>
    </div>
    <table>
      <thead>
        <tr>
          <th>#</th>
          <th>认定</th>
          <th>开始</th>
          <th>结束</th>
          <th>时长</th>
          <th>检测次数</th>
          <th>平均置信度</th>
          <th>最高置信度</th>
        </tr>
      </thead>
      <tbody>
        <tr
          v-for="{ seg, originalIndex } in visibleSegments"
          :key="seg.id"
          class="table-row"
          :class="confidenceTier(seg.max_confidence)"
        >
          <td class="index">{{ originalIndex + 1 }}</td>
          <td>
            <span
              class="tier-badge"
              :class="confidenceTier(seg.max_confidence)"
              :title="confidenceTier(seg.max_confidence) === 'confirmed'
                ? '峰值置信度达到确认线（50%）'
                : '低置信度记录：宁可多截不要漏截，请人工复核'"
            >
              {{ confidenceTier(seg.max_confidence) === 'confirmed' ? '确认' : '疑似' }}
            </span>
          </td>
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

.table-toolbar {
  display: flex;
  justify-content: flex-end;
  margin-bottom: var(--space-2);
}

.tier-toggle {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  font-size: var(--text-xs);
  color: var(--text-secondary);
  cursor: pointer;
  user-select: none;
}

.tier-badge {
  display: inline-block;
  padding: 2px var(--space-2);
  border-radius: var(--radius-full, 999px);
  font-size: var(--text-xs);
  font-weight: 600;
}

.tier-badge.confirmed {
  background: rgba(63, 185, 80, 0.15);
  color: var(--accent-green, #3fb950);
}

.tier-badge.suspected {
  background: rgba(210, 153, 34, 0.15);
  color: var(--accent-yellow, #d29922);
}

tr.suspected td {
  opacity: 0.75;
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
  td:nth-child(6),
  th:nth-child(7),
  td:nth-child(7) {
    display: none;
  }
}
</style>
