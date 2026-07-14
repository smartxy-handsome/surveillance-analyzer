import { ref, onMounted, onUnmounted } from 'vue'

const VIDEO_EXTENSIONS = ['.mp4', '.avi', '.mkv', '.mov', '.wmv', '.flv', '.webm']

export function useDragDrop(onDrop: (file: File) => void) {
  const isDragging = ref(false)
  let dragCounter = 0

  function isValidVideoFile(file: File): boolean {
    const ext = '.' + file.name.split('.').pop()?.toLowerCase()
    return VIDEO_EXTENSIONS.includes(ext)
  }

  function handleDragEnter(e: DragEvent) {
    e.preventDefault()
    dragCounter++
    if (e.dataTransfer?.types.includes('Files')) {
      isDragging.value = true
    }
  }

  function handleDragLeave(e: DragEvent) {
    e.preventDefault()
    dragCounter--
    if (dragCounter === 0) {
      isDragging.value = false
    }
  }

  function handleDragOver(e: DragEvent) {
    e.preventDefault()
    if (e.dataTransfer) {
      e.dataTransfer.dropEffect = 'copy'
    }
  }

  function handleDrop(e: DragEvent) {
    e.preventDefault()
    isDragging.value = false
    dragCounter = 0

    const files = e.dataTransfer?.files
    if (files && files.length > 0) {
      const file = files[0]
      if (isValidVideoFile(file)) {
        onDrop(file)
      }
    }
  }

  onMounted(() => {
    document.addEventListener('dragenter', handleDragEnter)
    document.addEventListener('dragleave', handleDragLeave)
    document.addEventListener('dragover', handleDragOver)
    document.addEventListener('drop', handleDrop)
  })

  onUnmounted(() => {
    document.removeEventListener('dragenter', handleDragEnter)
    document.removeEventListener('dragleave', handleDragLeave)
    document.removeEventListener('dragover', handleDragOver)
    document.removeEventListener('drop', handleDrop)
  })

  return {
    isDragging,
  }
}
