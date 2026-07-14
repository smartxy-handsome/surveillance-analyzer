import type { Job } from '../api/client'

export type PendingItemStatus = 'pending' | 'submitting' | 'error'

export interface PendingItem {
  id: string
  path: string
  filename: string
  status: PendingItemStatus
  error?: string
}

export interface SubmitOutcome {
  id: string
  ok: boolean
  jobId?: string
  error?: string
}

/** Extract a human-readable message from a thrown value (axios errors carry `response.data.detail`). */
export function extractError(err: unknown): string {
  if (err && typeof err === 'object') {
    const detail = (err as { response?: { data?: { detail?: unknown } } }).response?.data?.detail
    if (typeof detail === 'string') return detail
  }
  if (err instanceof Error) return err.message
  return '创建任务失败'
}

/** Return the file name portion of a path, handling both `\` and `/` separators. */
export function basename(path: string): string {
  const parts = path.split(/[\\/]/)
  return parts[parts.length - 1] || path
}

/**
 * Submit every pending item by calling `createJob` for each, in order.
 * A failure on one item does not stop the rest. Returns one outcome per input item
 * (same length, same order). The caller is responsible for removing successful items
 * from the UI list and emitting `job-created` for each.
 */
export async function submitItems(
  items: PendingItem[],
  createJob: (path: string) => Promise<Job>
): Promise<SubmitOutcome[]> {
  const outcomes: SubmitOutcome[] = []
  for (const item of items) {
    try {
      const job = await createJob(item.path)
      outcomes.push({ id: item.id, ok: true, jobId: job.id })
    } catch (err) {
      outcomes.push({ id: item.id, ok: false, error: extractError(err) })
    }
  }
  return outcomes
}
