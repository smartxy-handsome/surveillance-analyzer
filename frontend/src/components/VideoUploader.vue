<script setup lang="ts">
import { ref, computed } from 'vue'
import { createJob } from '../api/client'
import type { DetectionTarget } from '../api/client'
import FileBrowser from './FileBrowser.vue'
import PendingList from './PendingList.vue'
import RecentHistory from './RecentHistory.vue'
import { useRecentHistory } from '../composables/useRecentHistory'
import { submitItems, extractError, basename, type PendingItem } from '../utils/submitItems'

const emit = defineEmits<{
  'job-created': []
  'open-history': [id: string]
}>()

const draftPath = ref('')
const submitting = ref(false)
const error = ref<string | null>(null)
const browser = ref<InstanceType<typeof FileBrowser> | null>(null)
const items = ref<PendingItem[]>([])
const detectionTarget = ref<DetectionTarget>('person')
const { addEntry } = useRecentHistory()

const canSubmit = computed(() => items.value.length > 0 && !submitting.value)

const targetOptions: { value: DetectionTarget; label: string }[] = [
  { value: 'person', label: '🚶 人体识别' },
  { value: 'vehicle', label: '🚗 车辆识别' },
  { value: 'both', label: '两者都选' },
]

function addPath(path: string) {
  const trimmed = path.trim()
  if (!trimmed) return
  const normalized = trimmed.toLowerCase()
  if (items.value.some((it) => it.path.toLowerCase() === normalized)) return // dedupe (case-insensitive)
  items.value.push({
    id: crypto.randomUUID(),
    path: trimmed,
    filename: basename(trimmed),
    status: 'pending',
  })
}

function onAddDraft() {
  addPath(draftPath.value)
  draftPath.value = ''
}

function onFilesSelected(paths: string[]) {
  for (const p of paths) {
    addPath(p)
  }
}

function onRemove(id: string) {
  items.value = items.value.filter((it) => it.id !== id)
}

async function onSubmit() {
  if (!canSubmit.value) return
  submitting.value = true
  error.value = null
  try {
    const outcomes = await submitItems(items.value, createJob, detectionTarget.value)
    const remaining: PendingItem[] = []
    for (let i = 0; i < items.value.length; i++) {
      const item = items.value[i]
      const outcome = outcomes[i]
      if (outcome.ok) {
        addEntry({
          id: outcome.jobId!,
          filename: item.filename,
          filePath: item.path,
          status: 'pending',
          createdAt: new Date().toISOString(),
        })
        emit('job-created')
      } else {
        remaining.push({ ...item, status: 'error', error: outcome.error })
      }
    }
    items.value = remaining
    if (remaining.some((it) => it.status === 'error')) {
      error.value = '部分视频提交失败，请查看标红项'
    }
  } catch (err) {
    error.value = extractError(err)
  } finally {
    submitting.value = false
  }
}

function onHistorySelect(id: string) {
  emit('open-history', id)
}
</script>

<template>
  <div class="uploader">
    <h2>
      <span class="icon">🔍</span>
      分析视频
    </h2>
    <form @submit.prevent="onAddDraft">
      <input
        v-model="draftPath"
        type="text"
        placeholder="视频文件路径，可逐条追加，例如 D:\videos\camera1.mp4"
        :disabled="submitting"
        class="path-input"
      />
      <button type="submit" class="add-btn" :disabled="submitting || !draftPath.trim()">
        ＋ 追加
      </button>
      <button
        type="button"
        class="browse-btn"
        @click="browser?.open()"
        :disabled="submitting"
      >
        📁 浏览...
      </button>
    </form>
    <p v-if="error" class="error">{{ error }}</p>

    <div class="target-selector" role="radiogroup" aria-label="检测目标">
      <span class="target-label">检测目标：</span>
      <label v-for="opt in targetOptions" :key="opt.value" class="target-option">
        <input
          type="radio"
          name="detection-target"
          :value="opt.value"
          v-model="detectionTarget"
          :disabled="submitting"
        />
        {{ opt.label }}
      </label>
    </div>

    <PendingList
      :items="items"
      :submitting="submitting"
      @remove="onRemove"
      @submit="onSubmit"
    />

    <FileBrowser ref="browser" @select="onFilesSelected" />
  </div>

  <RecentHistory @select="onHistorySelect" />
</template>

<style scoped>
.uploader {
  background: var(--bg-secondary);
  border: 1px solid var(--border-primary);
  border-radius: var(--radius-lg);
  padding: var(--space-6);
  transition: all var(--transition-normal);
}

.uploader:hover {
  border-color: rgba(88, 166, 255, 0.3);
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

form {
  display: flex;
  gap: var(--space-2);
}

.path-input {
  flex: 1;
  padding: var(--space-2) var(--space-3);
  background: var(--bg-primary);
  border: 1px solid var(--border-primary);
  border-radius: var(--radius-md);
  color: var(--text-primary);
  font-family: var(--font-mono);
  font-size: var(--text-sm);
  transition: all var(--transition-fast);
}

.path-input:focus {
  outline: none;
  border-color: var(--accent-blue);
  box-shadow: 0 0 0 3px rgba(88, 166, 255, 0.15);
}

.path-input::placeholder {
  color: var(--text-muted);
}

.add-btn,
.browse-btn {
  padding: var(--space-2) var(--space-4);
  background: var(--bg-tertiary);
  border: 1px solid var(--border-primary);
  border-radius: var(--radius-md);
  color: var(--text-primary);
  font-size: var(--text-sm);
  cursor: pointer;
  transition: all var(--transition-fast);
  white-space: nowrap;
}

.add-btn:hover:not(:disabled),
.browse-btn:hover:not(:disabled) {
  background: var(--bg-hover);
  border-color: var(--text-secondary);
}

.add-btn:disabled,
.browse-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.error {
  color: var(--accent-red);
  font-size: var(--text-sm);
  margin-top: var(--space-2);
}

.target-selector {
  display: flex;
  align-items: center;
  gap: var(--space-4);
  margin-top: var(--space-3);
  padding: var(--space-2) var(--space-3);
  background: var(--bg-tertiary);
  border: 1px solid var(--border-primary);
  border-radius: var(--radius-md);
  font-size: var(--text-sm);
}

.target-label {
  color: var(--text-secondary);
}

.target-option {
  display: flex;
  align-items: center;
  gap: var(--space-1);
  cursor: pointer;
  user-select: none;
}

.target-option input {
  accent-color: var(--accent-blue);
}

@media (max-width: 640px) {
  form {
    flex-direction: column;
  }

  .add-btn,
  .browse-btn {
    width: 100%;
  }
}
</style>
