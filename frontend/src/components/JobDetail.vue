<script setup lang="ts">
import { computed, onMounted, ref, onUnmounted } from 'vue'
import { useJobsStore } from '../stores/jobs'
import SegmentTable from './SegmentTable.vue'
import TimelineViewer from './TimelineViewer.vue'
import CaptureGallery from './CaptureGallery.vue'
import VehicleEventTable from './VehicleEventTable.vue'

const props = defineProps<{ jobId: string }>()
const store = useJobsStore()
const polling = ref<ReturnType<typeof setInterval> | null>(null)
const progressPercent = computed(() => store.currentJob?.progress?.percent ?? 0)

// Which result pane to show; only reachable for target 'both'.
const view = ref<'person' | 'vehicle'>('person')

const hasVehicleView = computed(
  () => store.currentJob?.detection_target === 'vehicle' || store.currentJob?.detection_target === 'both'
)
const showPersonView = computed(
  () => !hasVehicleView.value || view.value === 'person'
)

onMounted(async () => {
  await store.fetchJob(props.jobId)
  await store.fetchSegments(props.jobId)
  // Person gallery must not see vehicle captures: on 'both' jobs both
  // namespaces number from 1 and would collide in the gallery grouping.
  await store.fetchCaptures(props.jobId, hasVehicleView.value ? 'person' : undefined)
  if (store.currentJob?.detection_target === 'vehicle' || store.currentJob?.detection_target === 'both') {
    view.value = store.currentJob.detection_target === 'vehicle' ? 'vehicle' : 'person'
    await store.fetchVehicleEvents(props.jobId)
  }

  if (store.currentJob?.status === 'processing' || store.currentJob?.status === 'pending') {
    polling.value = setInterval(async () => {
      await store.fetchJob(props.jobId)
      await store.fetchSegments(props.jobId)
      await store.fetchCaptures(props.jobId, hasVehicleView.value ? 'person' : undefined)
      if (hasVehicleView.value) {
        await store.fetchVehicleEvents(props.jobId)
      }
      if (
        store.currentJob?.status === 'completed' ||
        store.currentJob?.status === 'failed'
      ) {
        if (polling.value) clearInterval(polling.value)
      }
    }, 2000)
  }
})

onUnmounted(() => {
  if (polling.value) clearInterval(polling.value)
})

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
  <div class="job-detail" v-if="store.currentJob">
    <div class="header">
      <h2>
        <span class="icon">🎬</span>
        {{ store.currentJob.filename }}
      </h2>
      <span :class="['badge', getStatusClass(store.currentJob.status)]">
        {{ getStatusText(store.currentJob.status) }}
      </span>
    </div>

    <div class="meta">
      <div class="meta-item" v-if="store.currentJob.video_metadata">
        <span class="meta-label">分辨率</span>
        <span class="meta-value">{{ store.currentJob.video_metadata.width }}x{{ store.currentJob.video_metadata.height }}</span>
      </div>
      <div class="meta-item" v-if="store.currentJob.video_metadata">
        <span class="meta-label">帧率</span>
        <span class="meta-value">{{ store.currentJob.video_metadata.fps?.toFixed(1) }} fps</span>
      </div>
      <div class="meta-item" v-if="store.currentJob.video_metadata">
        <span class="meta-label">时长</span>
        <span class="meta-value">{{ store.currentJob.video_metadata.duration?.toFixed(1) }}秒</span>
      </div>
      <div class="meta-item" v-if="store.currentJob.processing_time_seconds != null">
        <span class="meta-label">处理时间</span>
        <span class="meta-value highlight">{{ store.currentJob.processing_time_seconds.toFixed(1) }}秒</span>
      </div>
      <div
        class="meta-item"
        v-if="store.currentJob.dropped_frames"
        :title="`分析时跳过了解码失败的 ${store.currentJob.dropped_frames} 帧（源视频存在损坏片段）`"
      >
        <span class="meta-label">丢帧</span>
        <span class="meta-value">{{ store.currentJob.dropped_frames }}</span>
      </div>
    </div>

    <div v-if="store.currentJob.status === 'pending' && store.currentJob.queue_position" class="queue-note">
      <span class="progress-icon">⏳</span>
      <span>排队中，当前位于第 {{ store.currentJob.queue_position }} 位</span>
    </div>

    <div v-if="store.currentJob.status === 'processing'" class="progress">
      <span class="progress-icon">⏳</span>
      <span>正在处理视频... {{ progressPercent.toFixed(0) }}%</span>
      <div class="progress-bar">
        <div class="progress-fill" :style="{ width: progressPercent + '%' }"></div>
      </div>
    </div>
    <div v-if="store.currentJob.detection_target === 'both'" class="view-toggle">
      <button :class="{ active: view === 'person' }" @click="view = 'person'">🚶 人体结果</button>
      <button :class="{ active: view === 'vehicle' }" @click="view = 'vehicle'">🚗 车辆结果</button>
    </div>

    <div v-if="showPersonView && store.segments.length > 0">
      <h3>
        <span class="icon">📊</span>
        时间轴
      </h3>
      <TimelineViewer
        :segments="store.segments"
        :total-duration="store.currentJob.video_metadata?.duration || 0"
      />

      <h3>
        <span class="icon">📋</span>
        时间段 ({{ store.segments.length }})
      </h3>
      <SegmentTable :segments="store.segments" />

      <CaptureGallery
        v-if="store.captures.length > 0"
        :captures="store.captures"
      />
    </div>
    <div
      v-else-if="showPersonView && store.currentJob.status === 'completed'"
      class="empty"
    >
      <span class="empty-icon">✅</span>
      该视频中未检测到人员。
    </div>

    <div v-if="!showPersonView" class="vehicle-section">
      <h3>
        <span class="icon">🚗</span>
        车辆事件 ({{ store.vehicleEvents.length }})
      </h3>
      <VehicleEventTable :events="store.vehicleEvents" />
    </div>

    <div v-if="store.currentJob.status === 'failed'" class="error">
      <span class="error-icon">❌</span>
      分析失败，请检查视频文件后重试。
    </div>
  </div>
</template>

<style scoped>
.job-detail {
  background: var(--bg-secondary);
  border: 1px solid var(--border-primary);
  border-radius: var(--radius-lg);
  padding: var(--space-6);
  animation: slideIn 0.3s ease;
}

.header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  margin-bottom: var(--space-4);
}

h2 {
  font-size: var(--text-xl);
  font-weight: 600;
  display: flex;
  align-items: center;
  gap: var(--space-2);
}

h2 .icon {
  font-size: 1.2em;
}

h3 {
  margin-top: var(--space-6);
  margin-bottom: var(--space-3);
  font-size: var(--text-base);
  font-weight: 600;
  display: flex;
  align-items: center;
  gap: var(--space-2);
}

h3 .icon {
  font-size: 1.1em;
}

.meta {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-4);
  margin-bottom: var(--space-4);
}

.meta-item {
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
}

.meta-label {
  font-size: var(--text-xs);
  color: var(--text-muted);
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

.meta-value {
  font-size: var(--text-sm);
  color: var(--text-primary);
  font-family: var(--font-mono);
}

.meta-value.highlight {
  color: var(--accent-blue);
  font-weight: 600;
}

.progress {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  padding: var(--space-4);
  background: rgba(88, 166, 255, 0.1);
  border: 1px solid rgba(88, 166, 255, 0.2);
  border-radius: var(--radius-md);
  color: var(--accent-blue);
  font-size: var(--text-sm);
}

.progress-icon {
  animation: pulse 2s infinite;
}

.queue-note {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  padding: var(--space-4);
  background: var(--bg-tertiary);
  border: 1px solid var(--border-primary);
  border-radius: var(--radius-md);
  color: var(--text-secondary);
  font-size: var(--text-sm);
}

.view-toggle {
  display: flex;
  gap: var(--space-2);
  margin-bottom: var(--space-4);
}

.view-toggle button {
  padding: var(--space-2) var(--space-4);
  background: var(--bg-tertiary);
  border: 1px solid var(--border-primary);
  border-radius: var(--radius-md);
  color: var(--text-secondary);
  font-size: var(--text-sm);
  cursor: pointer;
  transition: all var(--transition-fast);
}

.view-toggle button.active {
  background: rgba(88, 166, 255, 0.15);
  border-color: var(--accent-blue);
  color: var(--accent-blue);
  font-weight: 600;
}

.vehicle-section h3 {
  margin-bottom: var(--space-4);
  font-size: var(--text-lg);
  font-weight: 600;
  display: flex;
  align-items: center;
  gap: var(--space-2);
}

.progress-bar {
  flex: 1;
  height: 4px;
  background: var(--bg-tertiary);
  border-radius: var(--radius-full);
  overflow: hidden;
}

.progress-fill {
  height: 100%;
  background: var(--gradient-blue);
  border-radius: var(--radius-full);
  transition: width 0.5s ease;
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

.error {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  padding: var(--space-4);
  background: rgba(248, 81, 73, 0.1);
  border: 1px solid rgba(248, 81, 73, 0.2);
  border-radius: var(--radius-md);
  color: var(--accent-red);
  font-size: var(--text-sm);
}

.error-icon {
  font-size: 1.2em;
}

@keyframes slideIn {
  from {
    opacity: 0;
    transform: translateY(10px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

@keyframes pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.5; }
}

@keyframes shimmer {
  0% { transform: translateX(-100%); }
  100% { transform: translateX(400%); }
}

@media (max-width: 640px) {
  .header {
    flex-direction: column;
    gap: var(--space-2);
  }

  .meta {
    flex-direction: column;
  }
}
</style>
