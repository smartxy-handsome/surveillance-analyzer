<script setup lang="ts">
import { computed } from 'vue'
import { useJobsStore } from '../stores/jobs'
import type { ReviewTargetType, ReviewVerdict } from '../api/client'

const props = defineProps<{
  jobId: string
  targetType: ReviewTargetType
  targetId: number
  /** Button wording: captures ask "is this a person", records ask "real?" */
  goodLabel?: string
  badLabel?: string
}>()

const store = useJobsStore()

const current = computed<ReviewVerdict | undefined>(() =>
  store.verdictFor(props.targetType, props.targetId)
)

async function toggle(verdict: ReviewVerdict) {
  await store.setReview(props.jobId, props.targetType, props.targetId, verdict)
}
</script>

<template>
  <span class="review-buttons" :class="`has-${current ?? 'none'}`">
    <button
      class="review-btn good"
      :class="{ active: current === 'good' }"
      :title="current === 'good' ? '再次点击取消' : '标记为真实'"
      @click="toggle('good')"
    >
      {{ goodLabel ?? '✓ 真实' }}
    </button>
    <button
      class="review-btn bad"
      :class="{ active: current === 'bad' }"
      :title="current === 'bad' ? '再次点击取消' : '标记为误报'"
      @click="toggle('bad')"
    >
      {{ badLabel ?? '✗ 误报' }}
    </button>
  </span>
</template>

<style scoped>
.review-buttons {
  display: inline-flex;
  gap: var(--space-1, 4px);
}

.review-btn {
  padding: 2px var(--space-2, 8px);
  font-size: var(--text-xs, 12px);
  border: 1px solid var(--border-primary);
  border-radius: var(--radius-sm, 4px);
  background: transparent;
  color: var(--text-secondary);
  cursor: pointer;
  white-space: nowrap;
  transition: all var(--transition-fast);
}

.review-btn:hover {
  border-color: var(--accent-blue);
  color: var(--text-primary);
}

.review-btn.good.active {
  background: rgba(63, 185, 80, 0.18);
  border-color: var(--accent-green, #3fb950);
  color: var(--accent-green, #3fb950);
  font-weight: 600;
}

.review-btn.bad.active {
  background: rgba(248, 81, 73, 0.18);
  border-color: var(--accent-red, #f85149);
  color: var(--accent-red, #f85149);
  font-weight: 600;
}
</style>
