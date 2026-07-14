import { ref, onMounted } from 'vue'
import { getSystemPaths } from '../api/client'

export interface QuickPath {
  name: string
  path: string
  icon: string
}

const STORAGE_KEY = 'surveillance_quick_paths'

const paths = ref<QuickPath[]>([])
const initialized = ref(false)

async function loadPaths() {
  // First try localStorage
  try {
    const stored = localStorage.getItem(STORAGE_KEY)
    if (stored) {
      const parsed = JSON.parse(stored)
      if (Array.isArray(parsed) && parsed.length > 0) {
        paths.value = parsed
        initialized.value = true
        return
      }
    }
  } catch {}

  // Then fetch from backend
  try {
    const result = await getSystemPaths()
    paths.value = result.paths
    localStorage.setItem(STORAGE_KEY, JSON.stringify(paths.value))
  } catch {
    // Fallback to empty
    paths.value = []
  }
  initialized.value = true
}

function savePaths() {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(paths.value))
}

export function useQuickPaths() {
  if (!initialized.value) {
    loadPaths()
  }

  function addPath(name: string, path: string, icon: string = '📁') {
    if (paths.value.some(p => p.path === path)) return
    paths.value.push({ name, path, icon })
    savePaths()
  }

  function removePath(path: string) {
    paths.value = paths.value.filter(p => p.path !== path)
    savePaths()
  }

  function resetToDefaults() {
    localStorage.removeItem(STORAGE_KEY)
    loadPaths()
  }

  return {
    paths,
    addPath,
    removePath,
    resetToDefaults,
  }
}
