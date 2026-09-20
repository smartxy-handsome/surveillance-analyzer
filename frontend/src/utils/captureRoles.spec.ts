import { describe, it, expect } from 'vitest'
import { captureRole, captureRoleLabel } from './captureRoles'

describe('captureRole', () => {
  it('returns "both" for a single capture (single-frame segment)', () => {
    expect(captureRole(0, 1)).toBe('both')
  })

  it('labels the earliest capture as appearance and the latest as departure', () => {
    expect(captureRole(0, 2)).toBe('appearance')
    expect(captureRole(1, 2)).toBe('departure')
  })

  it('treats middle captures (legacy jobs) as appearance', () => {
    expect(captureRole(0, 3)).toBe('appearance')
    expect(captureRole(1, 3)).toBe('appearance')
    expect(captureRole(2, 3)).toBe('departure')
  })
})

describe('captureRoleLabel', () => {
  it('maps roles to Chinese labels', () => {
    expect(captureRoleLabel('appearance')).toBe('出现')
    expect(captureRoleLabel('departure')).toBe('离开')
    expect(captureRoleLabel('both')).toBe('出现·离开')
  })
})
