import { describe, it, expect } from 'vitest'
import { confidenceTier, CONFIRMED_THRESHOLD } from './confidenceTier'

describe('confidenceTier', () => {
  it('marks records at or above 0.5 as confirmed', () => {
    expect(confidenceTier(0.5)).toBe('confirmed')
    expect(confidenceTier(0.72)).toBe('confirmed')
    expect(confidenceTier(1.0)).toBe('confirmed')
  })

  it('marks records below 0.5 as suspected', () => {
    expect(confidenceTier(0.49)).toBe('suspected')
    expect(confidenceTier(0.3)).toBe('suspected')
    expect(confidenceTier(0.0)).toBe('suspected')
  })

  it('keeps the rescue threshold boundary aligned with the backend rule', () => {
    // The frontend tier line must equal the aggregation rescue threshold so
    // "confirmed" means "this record would exist even without recall-first".
    expect(CONFIRMED_THRESHOLD).toBe(0.5)
  })
})
