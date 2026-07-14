<script setup lang="ts">
import { computed, ref } from 'vue'
import type { Capture } from '../api/client'

const props = defineProps<{
  captures: Capture[]
}>()

const selectedImage = ref<Capture | null>(null)
const viewMode = ref<'crop' | 'annotated'>('annotated')
const zoomLevel = ref(1)
const panX = ref(0)
const panY = ref(0)
const isDragging = ref(false)
const dragStartX = ref(0)
const dragStartY = ref(0)
const dragStartPanX = ref(0)
const dragStartPanY = ref(0)

// Group captures by segment
const groupedCaptures = computed(() => {
  const groups: Record<number, Capture[]> = {}
  for (const capture of props.captures) {
    if (!groups[capture.segment_index]) {
      groups[capture.segment_index] = []
    }
    groups[capture.segment_index].push(capture)
  }
  return groups
})

const segmentIndices = computed(() => {
  return Object.keys(groupedCaptures.value)
    .map(Number)
    .sort((a, b) => a - b)
})

function openImage(capture: Capture) {
  selectedImage.value = capture
  zoomLevel.value = 1
  panX.value = 0
  panY.value = 0
}

function closeImage() {
  selectedImage.value = null
  zoomLevel.value = 1
  panX.value = 0
  panY.value = 0
}

function zoomIn() {
  zoomLevel.value = Math.min(zoomLevel.value + 0.25, 3)
}

function zoomOut() {
  zoomLevel.value = Math.max(zoomLevel.value - 0.25, 0.5)
  // Reset pan if zoomed out to 1x or less
  if (zoomLevel.value <= 1) {
    panX.value = 0
    panY.value = 0
  }
}

function resetZoom() {
  zoomLevel.value = 1
  panX.value = 0
  panY.value = 0
}

function startDrag(e: MouseEvent) {
  if (zoomLevel.value <= 1) return
  isDragging.value = true
  dragStartX.value = e.clientX
  dragStartY.value = e.clientY
  dragStartPanX.value = panX.value
  dragStartPanY.value = panY.value
  e.preventDefault()
}

function onDrag(e: MouseEvent) {
  if (!isDragging.value) return
  const dx = e.clientX - dragStartX.value
  const dy = e.clientY - dragStartY.value
  panX.value = dragStartPanX.value + dx
  panY.value = dragStartPanY.value + dy
}

function endDrag() {
  isDragging.value = false
}

function onWheel(e: WheelEvent) {
  e.preventDefault()
  if (e.deltaY < 0) {
    zoomIn()
  } else {
    zoomOut()
  }
}
</script>

<template>
  <div class="capture-gallery" v-if="captures.length > 0">
    <div class="gallery-header">
      <h3>📸 截取图片</h3>
      <div class="view-toggle">
        <button
          :class="{ active: viewMode === 'annotated' }"
          @click="viewMode = 'annotated'"
        >
          标注图
        </button>
        <button
          :class="{ active: viewMode === 'crop' }"
          @click="viewMode = 'crop'"
        >
          裁剪图
        </button>
      </div>
    </div>

    <div v-for="segIdx in segmentIndices" :key="segIdx" class="segment-group">
      <h4>时间段 {{ segIdx }}</h4>
      <div class="capture-grid">
        <div
          v-for="capture in groupedCaptures[segIdx]"
          :key="capture.id"
          class="capture-card"
          @click="openImage(capture)"
        >
          <img
            :src="viewMode === 'crop' ? capture.crop_url : capture.annotated_url"
            :alt="`${capture.timestamp_formatted} 的截取`"
            loading="lazy"
          />
          <div class="capture-info">
            <span class="timestamp">{{ capture.timestamp_formatted }}</span>
            <span class="confidence">{{ (capture.confidence * 100).toFixed(0) }}%</span>
          </div>
        </div>
      </div>
    </div>

    <!-- Lightbox -->
    <div v-if="selectedImage" class="lightbox" @click="closeImage">
      <div class="lightbox-content" @click.stop>
        <div class="lightbox-header">
          <div class="lightbox-toggle">
            <button
              :class="{ active: viewMode === 'annotated' }"
              @click="viewMode = 'annotated'"
            >
              标注图
            </button>
            <button
              :class="{ active: viewMode === 'crop' }"
              @click="viewMode = 'crop'"
            >
              裁剪图
            </button>
          </div>
          <div class="zoom-controls">
            <button @click="zoomOut" title="缩小">➖</button>
            <span class="zoom-level">{{ Math.round(zoomLevel * 100) }}%</span>
            <button @click="zoomIn" title="放大">➕</button>
            <button @click="resetZoom" title="重置">↺</button>
          </div>
          <button class="close-btn" @click="closeImage">&times;</button>
        </div>
        <div
          class="lightbox-image-wrapper"
          @mousedown="startDrag"
          @mousemove="onDrag"
          @mouseup="endDrag"
          @mouseleave="endDrag"
          @wheel="onWheel"
          :class="{ dragging: isDragging }"
        >
          <img
            :src="viewMode === 'crop' ? selectedImage.crop_url : selectedImage.annotated_url"
            :alt="`${selectedImage.timestamp_formatted} 的截取`"
            :style="{
              transform: `scale(${zoomLevel}) translate(${panX / zoomLevel}px, ${panY / zoomLevel}px)`,
              cursor: zoomLevel > 1 ? (isDragging ? 'grabbing' : 'grab') : 'default'
            }"
          />
        </div>
        <div class="lightbox-info">
          <span>时间: {{ selectedImage.timestamp_formatted }}</span>
          <span>置信度: {{ (selectedImage.confidence * 100).toFixed(1) }}%</span>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.capture-gallery {
  margin-top: var(--space-6);
}

.gallery-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: var(--space-4);
}

.gallery-header h3 {
  margin: 0;
  font-size: var(--text-base);
  font-weight: 600;
  display: flex;
  align-items: center;
  gap: var(--space-2);
}

.view-toggle {
  display: flex;
  gap: 2px;
  background: var(--bg-primary);
  border: 1px solid var(--border-secondary);
  border-radius: var(--radius-md);
  padding: 2px;
}

.view-toggle button {
  padding: var(--space-1) var(--space-3);
  border: none;
  background: transparent;
  cursor: pointer;
  border-radius: var(--radius-sm);
  font-size: var(--text-xs);
  color: var(--text-muted);
  transition: all var(--transition-fast);
}

.view-toggle button:hover {
  color: var(--text-secondary);
}

.view-toggle button.active {
  background: var(--bg-tertiary);
  color: var(--text-primary);
  box-shadow: var(--shadow-sm);
}

.segment-group {
  margin-bottom: var(--space-5);
}

.segment-group h4 {
  margin: 0 0 var(--space-3) 0;
  color: var(--text-secondary);
  font-size: var(--text-sm);
  font-weight: 500;
}

.capture-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
  gap: var(--space-3);
}

.capture-card {
  background: var(--bg-secondary);
  border: 1px solid var(--border-secondary);
  border-radius: var(--radius-lg);
  overflow: hidden;
  cursor: pointer;
  transition: all var(--transition-normal);
}

.capture-card:hover {
  transform: translateY(-4px);
  border-color: var(--accent-blue);
  box-shadow: var(--shadow-glow-blue);
}

.capture-card img {
  width: 100%;
  height: 220px;
  object-fit: cover;
  border-bottom: 1px solid var(--border-secondary);
}

.capture-info {
  padding: var(--space-2) var(--space-3);
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.timestamp {
  font-size: var(--text-xs);
  color: var(--text-secondary);
  font-family: var(--font-mono);
}

.confidence {
  font-size: var(--text-xs);
  font-weight: 600;
  color: var(--accent-blue);
  font-family: var(--font-mono);
}

/* Lightbox */
.lightbox {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.9);
  backdrop-filter: blur(8px);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
  animation: fadeIn 0.2s ease;
  padding: var(--space-4);
}

.lightbox-content {
  display: flex;
  flex-direction: column;
  width: 90vw;
  height: 90vh;
  background: var(--bg-secondary);
  border: 1px solid var(--border-primary);
  border-radius: var(--radius-xl);
  overflow: hidden;
  box-shadow: var(--shadow-lg);
}

.lightbox-header {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  padding: var(--space-3) var(--space-4);
  border-bottom: 1px solid var(--border-primary);
  background: var(--bg-tertiary);
  flex-shrink: 0;
}

.lightbox-toggle {
  display: flex;
  gap: 2px;
  background: var(--bg-primary);
  border: 1px solid var(--border-secondary);
  border-radius: var(--radius-md);
  padding: 2px;
}

.lightbox-toggle button {
  padding: var(--space-1) var(--space-3);
  border: none;
  background: transparent;
  color: var(--text-muted);
  cursor: pointer;
  border-radius: var(--radius-sm);
  font-size: var(--text-xs);
  transition: all var(--transition-fast);
}

.lightbox-toggle button:hover {
  color: var(--text-secondary);
}

.lightbox-toggle button.active {
  background: var(--bg-tertiary);
  color: var(--text-primary);
}

.zoom-controls {
  display: flex;
  align-items: center;
  gap: var(--space-1);
  background: var(--bg-primary);
  border: 1px solid var(--border-secondary);
  border-radius: var(--radius-md);
  padding: 2px;
  margin-left: auto;
}

.zoom-controls button {
  width: 28px;
  height: 28px;
  display: flex;
  align-items: center;
  justify-content: center;
  border: none;
  background: transparent;
  color: var(--text-muted);
  cursor: pointer;
  border-radius: var(--radius-sm);
  font-size: 0.8rem;
  transition: all var(--transition-fast);
}

.zoom-controls button:hover {
  background: var(--bg-hover);
  color: var(--text-primary);
}

.zoom-level {
  font-size: var(--text-xs);
  color: var(--text-secondary);
  min-width: 40px;
  text-align: center;
  font-family: var(--font-mono);
}

.close-btn {
  width: 32px;
  height: 32px;
  border: none;
  background: var(--bg-primary);
  border: 1px solid var(--border-secondary);
  color: var(--text-secondary);
  font-size: 1.2rem;
  border-radius: var(--radius-md);
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all var(--transition-fast);
  flex-shrink: 0;
}

.close-btn:hover {
  background: rgba(248, 81, 73, 0.2);
  border-color: var(--accent-red);
  color: var(--accent-red);
}

.lightbox-image-wrapper {
  flex: 1;
  overflow: hidden;
  display: flex;
  justify-content: center;
  align-items: center;
  padding: var(--space-4);
  background: var(--bg-primary);
  user-select: none;
}

.lightbox-image-wrapper.dragging {
  cursor: grabbing !important;
}

.lightbox-image-wrapper img {
  max-width: 100%;
  max-height: 100%;
  object-fit: contain;
  transition: transform 0.1s ease;
  transform-origin: center center;
  pointer-events: none;
}

.lightbox-info {
  padding: var(--space-3) var(--space-4);
  display: flex;
  gap: var(--space-4);
  font-size: var(--text-sm);
  color: var(--text-primary);
  border-top: 1px solid var(--border-primary);
  font-family: var(--font-mono);
  background: var(--bg-tertiary);
  flex-shrink: 0;
}

@keyframes fadeIn {
  from { opacity: 0; }
  to { opacity: 1; }
}

@media (max-width: 640px) {
  .gallery-header {
    flex-direction: column;
    gap: var(--space-2);
    align-items: flex-start;
  }

  .capture-grid {
    grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
  }

  .capture-card img {
    height: 160px;
  }

  .lightbox-toolbar {
    flex-direction: column;
    gap: var(--space-2);
    align-items: flex-start;
  }
}
</style>
