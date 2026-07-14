<script setup lang="ts">
import { computed } from 'vue'
import type { Segment } from '../api/client'

const props = defineProps<{ segments: Segment[]; totalDuration: number }>()

const bars = computed(() => {
  if (!props.totalDuration) return []
  return props.segments.map((s, i) => ({
    left: `${(s.start_time / props.totalDuration) * 100}%`,
    width: `${(s.duration_seconds / props.totalDuration) * 100}%`,
    label: `时间段 ${i + 1}: ${s.start_time_formatted} - ${s.end_time_formatted}`,
    confidence: s.avg_confidence,
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
        :style="{ left: bar.left, width: bar.width }"
        :title="bar.label"
      >
        <div class="bar-fill"></div>
        <div class="bar-tooltip">
          <span class="tooltip-label">{{ bar.label }}</span>
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
