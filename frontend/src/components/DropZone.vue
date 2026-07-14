<script setup lang="ts">
import { ref } from 'vue'
import { useDragDrop } from '../composables/useDragDrop'

const emit = defineEmits<{
  drop: [file: File]
}>()

const showFilePickerHint = ref(false)

const { isDragging } = useDragDrop(async (file) => {
  // Try to use File System Access API to get the file handle
  // This works in Chromium-based browsers (Chrome, Edge)
  if ('showOpenFilePicker' in window) {
    try {
      // Open file picker to get the actual file handle with path
      const [handle] = await (window as any).showOpenFilePicker({
        types: [
          {
            description: 'Video Files',
            accept: {
              'video/*': ['.mp4', '.avi', '.mkv', '.mov', '.wmv', '.flv', '.webm'],
            },
          },
        ],
      })
      const fileHandle = await handle.getFile()
      emit('drop', fileHandle)
      return
    } catch (e) {
      // User cancelled the picker
    }
  }
  // Fallback: show hint that we need the full path
  showFilePickerHint.value = true
})

function dismissHint() {
  showFilePickerHint.value = false
}
</script>

<template>
  <div class="drop-zone-wrapper">
    <slot />
    <Transition name="fade">
      <div v-if="isDragging" class="drop-overlay">
        <div class="drop-content">
          <div class="drop-icon">🎬</div>
          <div class="drop-text">Drop video file here</div>
          <div class="drop-hint">Supports MP4, AVI, MKV, MOV</div>
        </div>
      </div>
    </Transition>

    <!-- File picker hint modal -->
    <Transition name="fade">
      <div v-if="showFilePickerHint" class="hint-overlay" @click.self="dismissHint">
        <div class="hint-dialog">
          <h3>📁 Select Video File</h3>
          <p class="hint-text">
            Please use the <strong>Browse</strong> button to select the video file,
            or paste the full path manually in the input field.
          </p>
          <button class="btn-primary" @click="dismissHint">Got it</button>
        </div>
      </div>
    </Transition>
  </div>
</template>

<style scoped>
.drop-zone-wrapper {
  position: relative;
  min-height: 100vh;
}

.drop-overlay {
  position: fixed;
  inset: 0;
  background: rgba(13, 17, 23, 0.9);
  backdrop-filter: blur(8px);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 9999;
  animation: fadeIn 0.2s ease;
}

.drop-content {
  text-align: center;
  padding: var(--space-12);
  border: 2px dashed var(--accent-blue);
  border-radius: var(--radius-xl);
  background: rgba(88, 166, 255, 0.05);
  animation: pulse 2s infinite;
}

.drop-icon {
  font-size: 4rem;
  margin-bottom: var(--space-4);
  animation: bounce 1s infinite;
}

.drop-text {
  font-size: var(--text-xl);
  font-weight: 600;
  color: var(--text-primary);
  margin-bottom: var(--space-2);
}

.drop-hint {
  font-size: var(--text-sm);
  color: var(--text-secondary);
}

.hint-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.7);
  backdrop-filter: blur(4px);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 10000;
}

.hint-dialog {
  background: var(--bg-secondary);
  border: 1px solid var(--border-primary);
  border-radius: var(--radius-xl);
  padding: var(--space-6);
  max-width: 400px;
  text-align: center;
}

.hint-dialog h3 {
  font-size: var(--text-lg);
  margin-bottom: var(--space-3);
}

.file-name {
  font-family: var(--font-mono);
  font-size: var(--text-sm);
  color: var(--accent-blue);
  padding: var(--space-2) var(--space-3);
  background: var(--bg-primary);
  border-radius: var(--radius-md);
  margin-bottom: var(--space-4);
}

.hint-text {
  font-size: var(--text-sm);
  color: var(--text-secondary);
  line-height: 1.6;
  margin-bottom: var(--space-4);
}

.hint-text strong {
  color: var(--text-primary);
}

.btn-primary {
  padding: var(--space-2) var(--space-6);
  background: var(--gradient-blue);
  border: none;
  border-radius: var(--radius-md);
  color: white;
  font-size: var(--text-sm);
  font-weight: 600;
  cursor: pointer;
  transition: all var(--transition-fast);
}

.btn-primary:hover {
  box-shadow: var(--shadow-glow-blue);
}

@keyframes fadeIn {
  from { opacity: 0; }
  to { opacity: 1; }
}

@keyframes pulse {
  0%, 100% {
    border-color: var(--accent-blue);
    box-shadow: 0 0 20px rgba(88, 166, 255, 0.2);
  }
  50% {
    border-color: var(--accent-purple);
    box-shadow: 0 0 40px rgba(188, 140, 255, 0.3);
  }
}

@keyframes bounce {
  0%, 100% { transform: translateY(0); }
  50% { transform: translateY(-10px); }
}

.fade-enter-active,
.fade-leave-active {
  transition: opacity 0.2s ease;
}

.fade-enter-from,
.fade-leave-to {
  opacity: 0;
}
</style>
