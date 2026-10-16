import type { Capture, Segment } from '../api/client'

export type ConfidenceMode = 'max' | 'avg'

/** Which per-record aggregate the filter compares against. */
function confidenceKey(mode: ConfidenceMode): 'max_confidence' | 'avg_confidence' {
  return mode === 'avg' ? 'avg_confidence' : 'max_confidence'
}

/**
 * Client-side confidence filter: show only records whose confidence
 * aggregate clears the user-selected line. min <= 0 means "show everything".
 * 'max' keeps records with at least one strong frame; 'avg' requires the
 * whole record to be strong (strictly harder, avg <= max always).
 */
export function filterByMinConfidence<T extends { max_confidence: number; avg_confidence: number }>(
  items: T[],
  min: number,
  mode: ConfidenceMode = 'max'
): T[] {
  if (min <= 0) return items
  const key = confidenceKey(mode)
  return items.filter((item) => item[key] >= min)
}

/**
 * Filter captures down to those whose segment survives the confidence
 * filter. Capture.segment_index is the 1-based ordinal of the segment in
 * the start-time-ordered list, so surviving ordinals must be computed from
 * the ORIGINAL list -- positions within an already-filtered array would
 * renumber and mismatch.
 */
export function filterCapturesByMinConfidence(
  captures: Capture[],
  segments: Segment[],
  min: number,
  mode: ConfidenceMode = 'max'
): Capture[] {
  if (min <= 0) return captures
  const key = confidenceKey(mode)
  const keptOrdinals = new Set<number>()
  segments.forEach((seg, i) => {
    if (seg[key] >= min) keptOrdinals.add(i + 1)
  })
  return captures.filter((c) => keptOrdinals.has(c.segment_index))
}
