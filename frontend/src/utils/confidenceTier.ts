export const CONFIRMED_THRESHOLD = 0.5

export type ConfidenceTier = 'confirmed' | 'suspected'

/**
 * Record tiering for review efficiency: records whose peak confidence
 * reached the line the pre-tracking pipeline accepted are "confirmed";
 * recall-first lower-confidence records stay visible as "suspected"
 * (宁可多截不要漏截 -- noise is surfaced, not deleted).
 */
export function confidenceTier(maxConfidence: number): ConfidenceTier {
  return maxConfidence >= CONFIRMED_THRESHOLD ? 'confirmed' : 'suspected'
}
