<script setup lang="ts">
import { useQuickPaths } from '../composables/useQuickPaths'

const emit = defineEmits<{
  navigate: [path: string]
}>()

const { paths, removePath } = useQuickPaths()

function handleClick(path: string) {
  emit('navigate', path)
}
</script>

<template>
  <div class="quick-path-bar">
    <div class="quick-paths">
      <button
        v-for="item in paths"
        :key="item.path"
        class="quick-path-btn"
        @click="handleClick(item.path)"
        :title="item.path"
      >
        <span class="icon">{{ item.icon }}</span>
        <span class="name">{{ item.name }}</span>
      </button>
    </div>
  </div>
</template>

<style scoped>
.quick-path-bar {
  padding: var(--space-2) 0;
  border-bottom: 1px solid var(--border-secondary);
}

.quick-paths {
  display: flex;
  gap: var(--space-2);
  overflow-x: auto;
  padding: var(--space-1) 0;
  scrollbar-width: none;
}

.quick-paths::-webkit-scrollbar {
  display: none;
}

.quick-path-btn {
  display: inline-flex;
  align-items: center;
  gap: var(--space-1);
  padding: var(--space-1) var(--space-3);
  background: var(--bg-tertiary);
  border: 1px solid var(--border-secondary);
  border-radius: var(--radius-full);
  color: var(--text-secondary);
  font-size: var(--text-xs);
  cursor: pointer;
  transition: all var(--transition-fast);
  white-space: nowrap;
}

.quick-path-btn:hover {
  background: var(--bg-hover);
  border-color: var(--accent-blue);
  color: var(--text-primary);
}

.quick-path-btn .icon {
  font-size: 0.9em;
}

.quick-path-btn .name {
  font-weight: 500;
}
</style>
