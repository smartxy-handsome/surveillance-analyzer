<script setup lang="ts">
import { computed, ref } from 'vue'
import type { VehicleEvent } from '../api/client'
import { confidenceTier } from '../utils/confidenceTier'
import ReviewButtons from './ReviewButtons.vue'

const props = defineProps<{ events: VehicleEvent[]; jobId: string }>()

const showSuspected = ref(true)

const visibleEvents = computed(() =>
  props.events.filter(
    (e) => showSuspected.value || confidenceTier(e.max_confidence) === 'confirmed'
  )
)

const suspectedCount = computed(
  () => props.events.filter((e) => confidenceTier(e.max_confidence) === 'suspected').length
)

function plateTypeLabel(type: string | null): string {
  const map: Record<string, string> = {
    blue: '蓝牌',
    green: '绿牌(新能源)',
    yellow_single: '黄牌',
    yellow_double: '黄牌',
    white_single: '白牌',
    black_hk_macao: '港澳黑牌',
    hk_single: '香港牌',
    hk_double: '香港牌',
    macao_single: '澳门牌',
    macao_double: '澳门牌',
  }
  return map[type ?? ''] ?? type ?? ''
}

function thumb(url: string | null | undefined): string | null {
  return url ?? null
}
</script>

<template>
  <div class="vehicle-events">
    <div class="table-toolbar" v-if="suspectedCount > 0">
      <label class="tier-toggle">
        <input type="checkbox" v-model="showSuspected" />
        显示疑似记录（{{ suspectedCount }} 条，置信度 &lt; 50%）
      </label>
    </div>
    <div v-if="visibleEvents.length === 0" class="empty">
      <span class="empty-icon">🚗</span>
      未识别到车辆。
    </div>
    <table v-else>
      <thead>
        <tr>
          <th>#</th>
          <th>认定</th>
          <th>驶入时间</th>
          <th>驶出时间</th>
          <th>时长</th>
          <th>车牌号</th>
          <th>车牌类型</th>
          <th>复核</th>
          <th>驶入截图</th>
          <th>驶出截图</th>
          <th>车牌截图</th>
        </tr>
      </thead>
      <tbody>
        <tr
          v-for="(ev, i) in visibleEvents"
          :key="ev.id"
          class="table-row"
          :class="confidenceTier(ev.max_confidence)"
        >
          <td class="index">{{ i + 1 }}</td>
          <td>
            <span
              class="tier-badge"
              :class="confidenceTier(ev.max_confidence)"
              :title="confidenceTier(ev.max_confidence) === 'confirmed'
                ? '峰值置信度达到确认线（50%）'
                : '低置信度记录：宁可多截不要漏截，请人工复核'"
            >
              {{ confidenceTier(ev.max_confidence) === 'confirmed' ? '确认' : '疑似' }}
            </span>
          </td>
          <td class="time">{{ ev.enter_time_formatted }}</td>
          <td class="time">{{ ev.exit_time_formatted }}</td>
          <td class="duration">{{ ev.duration_seconds.toFixed(1) }}秒</td>
          <td class="plate">
            <template v-if="ev.plate_number">
              <span class="plate-number">{{ ev.plate_number }}</span>
              <span
                v-if="ev.plate_confidence != null"
                class="plate-conf"
                :title="`车牌识别置信度 ${(ev.plate_confidence * 100).toFixed(0)}%`"
              >
                {{ (ev.plate_confidence * 100).toFixed(0) }}%
              </span>
            </template>
            <span v-else class="plate-empty" title="未能识别车牌号，请查看车牌截图">—</span>
          </td>
          <td class="plate-type">{{ plateTypeLabel(ev.plate_type) || '—' }}</td>
          <td>
            <ReviewButtons :job-id="jobId" target-type="vehicle_event" :target-id="ev.id" />
          </td>
          <td>
            <a
              v-if="thumb(ev.enter_capture?.crop_url)"
              :href="ev.enter_capture!.crop_url"
              target="_blank"
              rel="noopener"
            >
              <img :src="ev.enter_capture!.crop_url" class="thumb" alt="驶入截图" />
            </a>
            <span v-else>—</span>
          </td>
          <td>
            <a
              v-if="thumb(ev.exit_capture?.crop_url)"
              :href="ev.exit_capture!.crop_url"
              target="_blank"
              rel="noopener"
            >
              <img :src="ev.exit_capture!.crop_url" class="thumb" alt="驶出截图" />
            </a>
            <span v-else>—</span>
          </td>
          <td>
            <a
              v-if="thumb(ev.plate_capture?.crop_url)"
              :href="ev.plate_capture!.crop_url"
              target="_blank"
              rel="noopener"
            >
              <img :src="ev.plate_capture!.crop_url" class="thumb" alt="车牌截图" />
            </a>
            <span v-else>—</span>
          </td>
        </tr>
      </tbody>
    </table>
  </div>
</template>

<style scoped>
.vehicle-events {
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

.empty {
  padding: var(--space-8);
  text-align: center;
  color: var(--text-secondary);
  font-size: var(--text-sm);
}

.empty-icon {
  display: block;
  font-size: 2rem;
  margin-bottom: var(--space-2);
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
  white-space: nowrap;
}

td {
  padding: var(--space-3) var(--space-4);
  font-size: var(--text-sm);
  border-bottom: 1px solid var(--border-secondary);
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
  white-space: nowrap;
}

.duration {
  font-family: var(--font-mono);
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

.plate-number {
  font-family: var(--font-mono);
  font-weight: 600;
  color: var(--text-primary);
}

.plate-conf {
  margin-left: var(--space-2);
  font-size: var(--text-xs);
  color: var(--text-muted);
  cursor: help;
}

.plate-empty {
  color: var(--text-muted);
  cursor: help;
}

.thumb {
  height: 44px;
  border-radius: var(--radius-sm, 4px);
  border: 1px solid var(--border-secondary);
  display: block;
  transition: transform var(--transition-fast);
}

.thumb:hover {
  transform: scale(1.5);
}
</style>
