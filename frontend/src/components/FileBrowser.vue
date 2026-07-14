<script setup lang="ts">
import { ref, computed } from 'vue'
import { browse } from '../api/client'
import type { BrowseItem } from '../api/client'
import QuickPathBar from './QuickPathBar.vue'

const emit = defineEmits<{ select: [paths: string[]] }>()

const currentPath = ref('')
const parentPath = ref<string | null>(null)
const items = ref<BrowseItem[]>([])
const loading = ref(false)
const error = ref<string | null>(null)
const visible = ref(false)
const selected = ref<Set<string>>(new Set())

const selectedPaths = computed(() => Array.from(selected.value))

async function navigate(path: string) {
  loading.value = true
  error.value = null
  try {
    const result = await browse(path)
    currentPath.value = result.current
    parentPath.value = result.parent
    items.value = result.items
  } catch (err: any) {
    error.value = err.response?.data?.detail || '浏览失败'
  } finally {
    loading.value = false
  }
}

function open() {
  visible.value = true
  selected.value = new Set()
  navigate(currentPath.value)
}

function goUp() {
  // parentPath is null when there's no parent (already at root)
  // parentPath is "" when at drive root (should go back to drive list)
  if (parentPath.value !== null) {
    navigate(parentPath.value)
  }
}

function handleClick(item: BrowseItem) {
  if (item.is_dir) {
    navigate(item.path)
    return
  }
  // Toggle file selection
  if (selected.value.has(item.path)) {
    selected.value.delete(item.path)
  } else {
    selected.value.add(item.path)
  }
  // Trigger reactivity for the Set
  selected.value = new Set(selected.value)
}

function isSelected(item: BrowseItem) {
  return selected.value.has(item.path)
}

function confirmSelection() {
  emit('select', selectedPaths.value)
  visible.value = false
  selected.value = new Set()
}

function onQuickPath(path: string) {
  navigate(path)
}

defineExpose({ open })
</script>

<template>
  <Teleport to="body">
    <Transition name="fade">
      <div v-if="visible" class="overlay" @click.self="visible = false">
        <div class="dialog">
          <div class="header">
            <h3>
              <span class="icon">📂</span>
              选择视频文件
            </h3>
            <button class="close" @click="visible = false">&times;</button>
          </div>

          <QuickPathBar @navigate="onQuickPath" />

          <div class="path-bar">
            <button class="nav-btn" @click="goUp" :disabled="parentPath === null" title="返回上级">
              ⬆️
            </button>
            <span class="path">{{ currentPath || '磁盘驱动器' }}</span>
          </div>

          <div v-if="error" class="error">{{ error }}</div>
          <div v-if="loading" class="loading">
            <span class="spinner">⏳</span> 加载中...
          </div>

          <div class="file-list" v-else>
            <div
              v-for="item in items"
              :key="item.path"
              class="file-item"
              :class="{ dir: item.is_dir, selected: !item.is_dir && isSelected(item) }"
              @click="handleClick(item)"
            >
              <span class="icon">{{ item.is_dir ? '📁' : '🎬' }}</span>
              <span class="name">{{ item.name }}</span>
              <span v-if="!item.is_dir && item.size_mb" class="size">{{ item.size_mb }} MB</span>
              <span v-if="!item.is_dir && isSelected(item)" class="check">✓</span>
            </div>
            <p v-if="items.length === 0 && !loading" class="empty">
              <span class="empty-icon">📭</span>
              未找到视频文件
            </p>
          </div>
          <div class="confirm-bar">
            <span class="selected-count">
              已选 {{ selectedPaths.length }} 个
            </span>
            <button class="confirm-btn" @click="confirmSelection">
              确认选择
            </button>
          </div>
        </div>
      </div>
    </Transition>
  </Teleport>
</template>

<style scoped>
.overlay {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.7);
  backdrop-filter: blur(4px);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
}

.dialog {
  background: var(--bg-secondary);
  border: 1px solid var(--border-primary);
  border-radius: var(--radius-xl);
  width: 600px;
  max-height: 75vh;
  display: flex;
  flex-direction: column;
  box-shadow: var(--shadow-lg);
  overflow: hidden;
}

.header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: var(--space-4) var(--space-5);
  border-bottom: 1px solid var(--border-primary);
}

.header h3 {
  margin: 0;
  font-size: var(--text-lg);
  font-weight: 600;
  display: flex;
  align-items: center;
  gap: var(--space-2);
}

.header h3 .icon {
  font-size: 1.2em;
}

.close {
  width: 32px;
  height: 32px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: transparent;
  border: none;
  border-radius: var(--radius-md);
  color: var(--text-secondary);
  font-size: 1.2rem;
  cursor: pointer;
  transition: all var(--transition-fast);
}

.close:hover {
  background: var(--bg-hover);
  color: var(--text-primary);
}

.path-bar {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  padding: var(--space-2) var(--space-4);
  background: var(--bg-primary);
  border-bottom: 1px solid var(--border-secondary);
}

.nav-btn {
  width: 28px;
  height: 28px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--bg-tertiary);
  border: 1px solid var(--border-secondary);
  border-radius: var(--radius-sm);
  cursor: pointer;
  font-size: 0.8rem;
  transition: all var(--transition-fast);
}

.nav-btn:hover:not(:disabled) {
  background: var(--bg-hover);
  border-color: var(--text-secondary);
}

.nav-btn:disabled {
  opacity: 0.3;
  cursor: not-allowed;
}

.path {
  font-family: var(--font-mono);
  font-size: var(--text-xs);
  color: var(--text-secondary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  flex: 1;
}

.file-list {
  flex: 1;
  overflow-y: auto;
  padding: var(--space-2) 0;
}

.file-item {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  padding: var(--space-2) var(--space-4);
  cursor: pointer;
  transition: all var(--transition-fast);
}

.file-item:hover {
  background: var(--bg-hover);
}

.file-item.dir .name {
  font-weight: 600;
  color: var(--text-primary);
}

.file-item:not(.dir) .name {
  color: var(--text-secondary);
}

.icon {
  font-size: 1.1rem;
  width: 24px;
  text-align: center;
  flex-shrink: 0;
}

.name {
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: var(--text-sm);
}

.size {
  color: var(--text-muted);
  font-size: var(--text-xs);
  font-family: var(--font-mono);
}

.error {
  color: var(--accent-red);
  padding: var(--space-3) var(--space-4);
  font-size: var(--text-sm);
}

.loading {
  padding: var(--space-8);
  text-align: center;
  color: var(--text-secondary);
  font-size: var(--text-sm);
}

.loading .spinner {
  display: inline-block;
  animation: spin 1s linear infinite;
}

.empty {
  padding: var(--space-8);
  text-align: center;
  color: var(--text-muted);
  font-size: var(--text-sm);
}

.empty-icon {
  display: block;
  font-size: 2rem;
  margin-bottom: var(--space-2);
}

/* Transitions */
.fade-enter-active,
.fade-leave-active {
  transition: opacity 0.2s ease;
}

.fade-enter-from,
.fade-leave-to {
  opacity: 0;
}

.fade-enter-active .dialog {
  animation: slideUp 0.3s ease;
}

@keyframes slideUp {
  from {
    transform: translateY(20px);
    opacity: 0;
  }
  to {
    transform: translateY(0);
    opacity: 1;
  }
}

@keyframes spin {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}

@media (max-width: 640px) {
  .dialog {
    width: 95%;
    max-height: 85vh;
  }
}

.file-item.selected {
  background: rgba(88, 166, 255, 0.12);
}

.file-item.selected .name {
  color: var(--accent-blue);
}

.check {
  color: var(--accent-blue);
  margin-left: auto;
}

.confirm-bar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: var(--space-3) var(--space-4);
  border-top: 1px solid var(--border-primary);
  background: var(--bg-primary);
}

.selected-count {
  font-size: var(--text-sm);
  color: var(--text-secondary);
}

.confirm-btn {
  padding: var(--space-2) var(--space-4);
  background: var(--gradient-blue);
  border: none;
  border-radius: var(--radius-md);
  color: white;
  font-size: var(--text-sm);
  font-weight: 600;
  cursor: pointer;
}
</style>
