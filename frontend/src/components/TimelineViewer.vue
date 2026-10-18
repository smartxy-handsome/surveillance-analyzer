<script setup lang="ts">
import { computed } from 'vue'
import type { Segment, VehicleEvent } from '../api/client'

const props = defineProps<{
  segments?: Segment[]
  events?: VehicleEvent[]
  totalDuration: number
}>()

interface Bar {
  left: string
  width: string
  label: string
  plate: string | null
  confidence: number
  kind: 'person' | 'vehicle'
}

const bars = computed<Bar[]>(() => {
  if (!props.totalDuration) return []
  const pct = (seconds: number) => `${(seconds / props.totalDuration) * 100}%`
  if (props.events) {
    return props.events.map((e, i) => ({
      left: pct(e.enter_time),
      width: pct(e.exit_time - e.enter_time),
      label: `车辆 ${i + 1}: ${e.enter_time_formatted} - ${e.exit_time_formatted}`,
      plate: e.plate_number,
      confidence: e.max_confidence,
      kind: 'vehicle',
    }))
  }
  return (props.segments ?? []).map((s, i) => ({
    left: pct(s.start_time),
    width: pct(s.duration_seconds),
    label: `时间段 ${i + 1}: ${s.start_time_formatted} - ${s.end_time_formatted}`,
    plate: null,
    confidence: s.avg_confidence,
    kind: 'person',
  }))
})

function formatTime(seconds: number): string {
  const m = Math.floor(seconds / 60)
  const s = Math.floor(seconds % 60)
  return `${m}:${s.toString().padStart(2, '0')}`
}
</script>

<template>
  <div class="timeline">
    <div class="track">
      <div
        v-for="(bar, i) in bars"
        :key="i"
        class="segment-bar"
        :class="bar.kind"
        :style="{ left: bar.left, width: bar.width }"
        :title="bar.label"
      >
        <div class="bar-fill"></div>
        <div class="bar-tooltip">
          <span class="tooltip-label">{{ bar.label }}</span>
          <span v-if="bar.plate" class="tooltip-plate">车牌: {{ bar.plate }}</span>
          <span class="tooltip-confidence">置信度: {{ (bar.confidence * 100).toFixed(0) }}%</span>
        </div>
      </div>
    </div>
    <div class="labels">
      <span class="time-label">00:00</span>
      <span class="time-label" v-if="totalDuration">{{ formatTime(totalDuration) }}</span>
    </div>
  </div>
</template>

<style scoped>
.timeline {
  margin-bottom: var(--space-4);
}

.track {
  position: relative;
  height: 40px;
  background: var(--bg-primary);
  border: 1px solid var(--border-secondary);
  border-radius: var(--radius-md);
  overflow: visible;
}

.segment-bar {
  position: absolute;
  top: 6px;
  bottom: 6px;
  min-width: 4px;
  cursor: pointer;
  z-index: 1;
}

.bar-fill {
  position: absolute;
  inset: 0;
  background: var(--gradient-blue);
  border-radius: var(--radius-sm);
  transition: all var(--transition-fast);
  box-shadow: 0 0 8px rgba(88, 166, 255, 0.3);
}

.segment-bar:hover .bar-fill {
  background: var(--gradient-green);
  box-shadow: 0 0 16px rgba(63, 185, 80, 0.5);
  transform: scaleY(1.1);
}

/* Vehicle bars reuse this component on the vehicle view; a distinct hue
   keeps them readable at a glance next to the blue person bars. */
.segment-bar.vehicle .bar-fill {
  background: var(--gradient-green);
  box-shadow: 0 0 8px rgba(63, 185, 80, 0.3);
}

.bar-tooltip {
  position: absolute;
  bottom: calc(100% + 8px);
  left: 50%;
  transform: translateX(-50%);
  background: var(--bg-secondary);
  border: 1px solid var(--border-primary);
  border-radius: var(--radius-md);
  padding: var(--space-2) var(--space-3);
  white-space: nowrap;
  opacity: 0;
  pointer-events: none;
  transition: all var(--transition-fast);
  box-shadow: var(--shadow-md);
  z-index: 10;
}

.segment-bar:hover .bar-tooltip {
  opacity: 1;
  transform: translateX(-50%) translateY(-4px);
}

.tooltip-label {
  display: block;
  font-size: var(--text-xs);
  color: var(--text-primary);
  font-weight: 500;
}

.tooltip-confidence {
  display: block;
  font-size: var(--text-xs);
  color: var(--accent-blue);
  margin-top: 2px;
}

.tooltip-plate {
  display: block;
  font-size: var(--text-xs);
  color: var(--accent-green, #3fb950);
  margin-top: 2px;
  font-family: var(--font-mono);
}

.labels {
  display: flex;
  justify-content: space-between;
  margin-top: var(--space-2);
}

.time-label {
  font-family: var(--font-mono);
  font-size: var(--text-xs);
  color: var(--text-muted);
}

@media (max-width: 640px) {
  .track {
    height: 32px;
  }

  .bar-tooltip {
    display: none;
  }
}
</style>
