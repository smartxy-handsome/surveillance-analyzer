import { ref } from 'vue'

export interface RecentVideo {
  id: string
  filename: string
  filePath: string
  status: string
  createdAt: string
}

const STORAGE_KEY = 'surveillance_recent_videos'
const MAX_ITEMS = 10

function loadHistory(): RecentVideo[] {
  try {
    const stored = localStorage.getItem(STORAGE_KEY)
    if (stored) {
      return JSON.parse(stored)
    }
  } catch {}
  return []
}

function saveHistory(items: RecentVideo[]) {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(items))
}

const history = ref<RecentVideo[]>(loadHistory())

export function useRecentHistory() {
  function addEntry(entry: RecentVideo) {
    // Remove duplicate if exists
    history.value = history.value.filter(h => h.filePath !== entry.filePath)

    // Add to front
    history.value.unshift(entry)

    // Trim to max
    if (history.value.length > MAX_ITEMS) {
      history.value = history.value.slice(0, MAX_ITEMS)
    }

    saveHistory(history.value)
  }

  function updateStatus(id: string, status: string) {
    const entry = history.value.find(h => h.id === id)
    if (entry) {
      entry.status = status
      saveHistory(history.value)
    }
  }

  function clearHistory() {
    history.value = []
    saveHistory(history.value)
  }

  function removeEntry(id: string) {
    history.value = history.value.filter(h => h.id !== id)
    saveHistory(history.value)
  }

  return {
    history,
    addEntry,
    updateStatus,
    clearHistory,
    removeEntry,
  }
}
