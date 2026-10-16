<script setup lang="ts">
import { ref } from 'vue'

const props = withDefaults(
  defineProps<{
    title: string
    /** When set, the open/closed state persists across pages under this key. */
    storageKey?: string
    defaultOpen?: boolean
  }>(),
  { defaultOpen: true }
)

const open = ref(
  props.storageKey
    ? localStorage.getItem(`section-open:${props.storageKey}`) !== '0'
    : props.defaultOpen
)

function toggle() {
  open.value = !open.value
  if (props.storageKey) {
    localStorage.setItem(`section-open:${props.storageKey}`, open.value ? '1' : '0')
  }
}
</script>

<template>
  <section class="collapsible-section">
    <button
      class="section-header"
      :aria-expanded="open"
      :title="open ? '收起' : '展开'"
      @click="toggle"
    >
      <span class="chevron" :class="{ open }" aria-hidden="true">▸</span>
      <span class="header-content"><slot name="header">{{ title }}</slot></span>
    </button>
    <div v-show="open" class="section-body" :class="{ 'is-collapsed': !open }">
      <slot />
    </div>
  </section>
</template>

<style scoped>
.section-header {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  width: 100%;
  padding: 0;
  margin-bottom: var(--space-3);
  background: none;
  border: none;
  color: var(--text-primary);
  font-size: var(--text-lg);
  font-weight: 600;
  text-align: left;
  cursor: pointer;
  user-select: none;
}

.section-header:hover .header-content {
  color: var(--accent-blue);
}

.chevron {
  display: inline-block;
  transition: transform var(--transition-fast);
  color: var(--text-muted);
  font-size: 0.9em;
}

.chevron.open {
  transform: rotate(90deg);
}

.header-content {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  transition: color var(--transition-fast);
}

.header-content :deep(.icon) {
  font-size: 1.2em;
}
</style>
