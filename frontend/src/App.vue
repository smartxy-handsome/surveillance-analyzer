<script setup lang="ts">
import { ref } from 'vue'
import VideoUploader from './components/VideoUploader.vue'
import JobList from './components/JobList.vue'
import JobDetail from './components/JobDetail.vue'
import { useJobsStore } from './stores/jobs'

const currentJobId = ref<string | null>(null)
const store = useJobsStore()

function onJobCreated() {
  // New jobs were submitted: refresh the list and stay on the upload page.
  store.fetchJobs()
}

function onOpenJob(id: string) {
  // Open an existing job (e.g. from recent history): navigate to its detail.
  currentJobId.value = id
}

function onBack() {
  currentJobId.value = null
}
</script>

<template>
  <div class="app">
    <header>
      <div class="header-content">
        <h1>
          <span class="icon">📹</span>
          监控视频分析系统
        </h1>
        <p class="subtitle">基于 AI 的智能视频监控分析</p>
      </div>
    </header>
    <main>
      <template v-if="!currentJobId">
        <VideoUploader @job-created="onJobCreated" @open-history="onOpenJob" />
        <JobList @select="(id: string) => (currentJobId = id)" />
      </template>
      <template v-else>
        <button class="back-btn" @click="onBack">
          <span class="arrow">&larr;</span> 返回列表
        </button>
        <JobDetail :job-id="currentJobId" />
      </template>
    </main>
    <footer>
      <p>Powered by YOLOv8 + FastAPI + Vue 3</p>
    </footer>
  </div>
</template>

<style>
.app {
  max-width: 960px;
  margin: 0 auto;
  padding: var(--space-6);
  min-height: 100vh;
  display: flex;
  flex-direction: column;
}

header {
  margin-bottom: var(--space-8);
  padding: var(--space-6) 0;
  border-bottom: 1px solid var(--border-primary);
}

.header-content h1 {
  font-size: var(--text-2xl);
  font-weight: 700;
  display: flex;
  align-items: center;
  gap: var(--space-3);
  background: var(--gradient-tech);
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  background-clip: text;
}

.header-content h1 .icon {
  -webkit-text-fill-color: initial;
  font-size: 1.5em;
}

.subtitle {
  color: var(--text-secondary);
  font-size: var(--text-sm);
  margin-top: var(--space-1);
}

main {
  display: flex;
  flex-direction: column;
  gap: var(--space-6);
  flex: 1;
}

.back-btn {
  align-self: flex-start;
  display: inline-flex;
  align-items: center;
  gap: var(--space-2);
  padding: var(--space-2) var(--space-4);
  background: var(--bg-secondary);
  border: 1px solid var(--border-primary);
  border-radius: var(--radius-md);
  color: var(--text-primary);
  font-size: var(--text-sm);
  cursor: pointer;
  transition: all var(--transition-fast);
}

.back-btn:hover {
  background: var(--bg-hover);
  border-color: var(--accent-blue);
}

.back-btn .arrow {
  transition: transform var(--transition-fast);
}

.back-btn:hover .arrow {
  transform: translateX(-2px);
}

footer {
  margin-top: var(--space-8);
  padding: var(--space-4) 0;
  border-top: 1px solid var(--border-primary);
  text-align: center;
}

footer p {
  color: var(--text-muted);
  font-size: var(--text-xs);
}

/* Responsive */
@media (max-width: 640px) {
  .app {
    padding: var(--space-4);
  }

  .header-content h1 {
    font-size: var(--text-xl);
  }
}
</style>
