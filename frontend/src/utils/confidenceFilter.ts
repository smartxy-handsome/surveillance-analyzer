import type { Capture, Segment } from '../api/client'

/**
 * Client-side confidence filter: show only records whose peak confidence
 * clears the user-selected line. min <= 0 means "show everything".
 */
export function filterByMinConfidence<T extends { max_confidence: number }>(
  items: T[],
  min: number
): T[] {
  if (min <= 0) return items
  return items.filter((item) => item.max_confidence >= min)
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
  min: number
): Capture[] {
  if (min <= 0) return captures
  const keptOrdinals = new Set<number>()
  segments.forEach((seg, i) => {
    if (seg.max_confidence >= min) keptOrdinals.add(i + 1)
  })
  return captures.filter((c) => keptOrdinals.has(c.segment_index))
}
