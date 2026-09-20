export type CaptureRole = 'appearance' | 'departure' | 'both'

/**
 * Role of a capture within its segment group, by timestamp position.
 * The pipeline keeps one capture when the person appears (earliest) and one
 * when they leave (latest); a single capture means a single-frame segment,
 * so it is both. Legacy jobs may have middle captures (old top-3 policy);
 * those are treated as appearance.
 */
export function captureRole(position: number, total: number): CaptureRole {
  if (total <= 1) return 'both'
  if (position === total - 1) return 'departure'
  return 'appearance'
}

export function captureRoleLabel(role: CaptureRole): string {
  switch (role) {
    case 'appearance':
      return '出现'
    case 'departure':
      return '离开'
    case 'both':
      return '出现·离开'
  }
}
