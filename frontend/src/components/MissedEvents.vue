<script setup lang="ts">
import { ref } from 'vue'
import { useJobsStore } from '../stores/jobs'

const props = defineProps<{ jobId: string }>()
const store = useJobsStore()

const startMin = ref<number | null>(null)
const startSec = ref<number | null>(null)
const endMin = ref<number | null>(null)
const endSec = ref<number | null>(null)
const note = ref('')
const error = ref('')
const submitting = ref(false)

function toSeconds(min: number | null, sec: number | null): number {
  return (min ?? 0) * 60 + (sec ?? 0)
}

function fmt(seconds: number): string {
  const m = Math.floor(seconds / 60)
  const s = Math.round(seconds % 60)
  return `${m}:${s.toString().padStart(2, '0')}`
}

async function submit() {
  const start = toSeconds(startMin.value, startSec.value)
  const end = toSeconds(endMin.value, endSec.value)
  if (end <= start) {
    error.value = '结束时间必须晚于开始时间'
    return
  }
  error.value = ''
  submitting.value = true
  try {
    await store.appendMissedEvent(props.jobId, start, end, note.value.trim() || null)
    startMin.value = null
    startSec.value = null
    endMin.value = null
    endSec.value = null
    note.value = ''
  } catch {
    error.value = '提交失败，请重试'
  } finally {
    submitting.value = false
  }
}

async function remove(id: number) {
  await store.removeMissedEvent(props.jobId, id)
}
</script>

<template>
  <div class="missed-events">
    <div class="panel">
      <h4>补录遗漏（系统没抓到、但你在视频里看到的人）</h4>
      <p class="hint">
        用播放器看视频时，遇到系统漏掉的人出现，把起止时间填进来。
        这些记录是评估召回率的真值，不会被保存为抓拍。
      </p>
      <form class="row" @submit.prevent="submit">
        <label>
          进入
          <input v-model.number="startMin" type="number" min="0" placeholder="分" /> :
          <input v-model.number="startSec" type="number" min="0" max="59" placeholder="秒" />
        </label>
        <label>
          离开
          <input v-model.number="endMin" type="number" min="0" placeholder="分" /> :
          <input v-model.number="endSec" type="number" min="0" max="59" placeholder="秒" />
        </label>
        <input v-model="note" type="text" class="note" placeholder="备注（可选，如：左侧门口）" />
        <button type="submit" :disabled="submitting">添加</button>
      </form>
      <p v-if="error" class="error">{{ error }}</p>
    </div>

    <ul v-if="store.missedEvents.length > 0" class="list">
      <li v-for="ev in store.missedEvents" :key="ev.id">
        <span class="time">{{ fmt(ev.start_seconds) }} – {{ fmt(ev.end_seconds) }}</span>
        <span class="duration">（{{ (ev.end_seconds - ev.start_seconds).toFixed(0) }} 秒）</span>
        <span v-if="ev.note" class="note-text">{{ ev.note }}</span>
        <button class="remove" title="删除" @click="remove(ev.id)">✕</button>
      </li>
    </ul>
  </div>
</template>

<style scoped>
.missed-events {
  margin-top: var(--space-4);
}

.panel {
  background: var(--bg-secondary);
  border: 1px dashed var(--border-primary);
  border-radius: var(--radius-md);
  padding: var(--space-3) var(--space-4);
}

.panel h4 {
  margin: 0 0 var(--space-1);
  font-size: var(--text-sm);
  color: var(--text-primary);
}

.hint {
  margin: 0 0 var(--space-3);
  font-size: var(--text-xs);
  color: var(--text-secondary);
}

.row {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--space-3);
}

.row label {
  display: flex;
  align-items: center;
  gap: var(--space-1);
  font-size: var(--text-sm);
  color: var(--text-secondary);
  white-space: nowrap;
}

.row input[type='number'] {
  width: 56px;
  padding: var(--space-1) var(--space-2);
  background: var(--bg-primary);
  border: 1px solid var(--border-primary);
  border-radius: var(--radius-sm);
  color: var(--text-primary);
}

.row .note {
  flex: 1;
  min-width: 160px;
  padding: var(--space-1) var(--space-2);
  background: var(--bg-primary);
  border: 1px solid var(--border-primary);
  border-radius: var(--radius-sm);
  color: var(--text-primary);
}

.row button {
  padding: var(--space-1) var(--space-4);
  border: none;
  border-radius: var(--radius-sm);
  background: var(--accent-blue);
  color: white;
  cursor: pointer;
}

.row button:disabled {
  opacity: 0.5;
  cursor: default;
}

.error {
  margin: var(--space-2) 0 0;
  color: var(--accent-red, #f85149);
  font-size: var(--text-xs);
}

.list {
  list-style: none;
  margin: var(--space-3) 0 0;
  padding: 0;
}

.list li {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  padding: var(--space-2) var(--space-3);
  border-bottom: 1px solid var(--border-secondary);
  font-size: var(--text-sm);
}

.time {
  font-family: var(--font-mono);
  color: var(--accent-yellow, #d29922);
}

.duration {
  color: var(--text-muted);
  font-size: var(--text-xs);
}

.note-text {
  color: var(--text-secondary);
  flex: 1;
}

.remove {
  margin-left: auto;
  border: none;
  background: transparent;
  color: var(--text-muted);
  cursor: pointer;
}

.remove:hover {
  color: var(--accent-red, #f85149);
}
</style>
