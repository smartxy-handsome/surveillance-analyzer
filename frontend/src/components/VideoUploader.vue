<script setup lang="ts">
import { ref } from 'vue'
import { createJob } from '../api/client'
import FileBrowser from './FileBrowser.vue'
import RecentHistory from './RecentHistory.vue'
import { useRecentHistory } from '../composables/useRecentHistory'

const emit = defineEmits<{ 'job-created': [id: string] }>()
const filePath = ref('')
const submitting = ref(false)
const error = ref<string | null>(null)
const browser = ref<InstanceType<typeof FileBrowser> | null>(null)
const { addEntry } = useRecentHistory()

function onFileSelected(path: string) {
  filePath.value = path
}

async function onSubmit() {
  if (!filePath.value.trim()) return

  submitting.value = true
  error.value = null
  try {
    const job = await createJob(filePath.value.trim())
    addEntry({
      id: job.id,
      filename: job.filename,
      filePath: filePath.value.trim(),
      status: 'pending',
      createdAt: new Date().toISOString(),
    })
    emit('job-created', job.id)
    filePath.value = ''
  } catch (err: any) {
    error.value = err.response?.data?.detail || '创建任务失败'
  } finally {
    submitting.value = false
  }
}

function onHistorySelect(id: string) {
  emit('job-created', id)
}
</script>

<template>
  <div class="uploader">
    <h2>
      <span class="icon">🔍</span>
      分析视频
    </h2>
    <form @submit.prevent="onSubmit">
      <input
        v-model="filePath"
        type="text"
        placeholder="视频文件路径，例如 D:\videos\camera1.mp4"
        :disabled="submitting"
        class="path-input"
      />
      <button type="button" class="browse-btn" @click="browser?.open()" :disabled="submitting">
        📁 浏览...
      </button>
      <button type="submit" class="submit-btn" :disabled="submitting || !filePath.trim()">
        {{ submitting ? '⏳ 启动中...' : '▶ 开始分析' }}
      </button>
    </form>
    <p v-if="error" class="error">{{ error }}</p>

    <FileBrowser ref="browser" @select="onFileSelected" />
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

.browse-btn:hover:not(:disabled) {
  background: var(--bg-hover);
  border-color: var(--text-secondary);
}

.submit-btn {
  padding: var(--space-2) var(--space-5);
  background: var(--gradient-blue);
  border: none;
  border-radius: var(--radius-md);
  color: white;
  font-size: var(--text-sm);
  font-weight: 600;
  cursor: pointer;
  transition: all var(--transition-fast);
  white-space: nowrap;
}

.submit-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.submit-btn:hover:not(:disabled) {
  box-shadow: var(--shadow-glow-blue);
  transform: translateY(-1px);
}

.error {
  color: var(--accent-red);
  font-size: var(--text-sm);
  margin-top: var(--space-2);
}

@media (max-width: 640px) {
  form {
    flex-direction: column;
  }

  .browse-btn,
  .submit-btn {
    width: 100%;
  }
}
</style>
