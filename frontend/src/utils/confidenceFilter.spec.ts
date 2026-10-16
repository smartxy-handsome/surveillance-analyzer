import { describe, it, expect } from 'vitest'
import { filterByMinConfidence, filterCapturesByMinConfidence } from './confidenceFilter'
import type { Capture, Segment } from '../api/client'

function seg(maxConfidence: number): Segment {
  return {
    id: maxConfidence * 100,
    start_time: 0,
    end_time: 1,
    start_time_formatted: '',
    end_time_formatted: '',
    duration_seconds: 1,
    detection_count: 1,
    avg_confidence: maxConfidence,
    max_confidence: maxConfidence,
  }
}

function cap(segmentIndex: number): Capture {
  return {
    id: segmentIndex,
    segment_index: segmentIndex,
    timestamp: segmentIndex,
    timestamp_formatted: '',
    confidence: 0.9,
    crop_url: '',
    kind: 'appearance',
  }
}

describe('filterByMinConfidence', () => {
  const items = [seg(0.6), seg(0.75), seg(0.9)]

  it('keeps everything when min is 0', () => {
    expect(filterByMinConfidence(items, 0)).toHaveLength(3)
  })

  it('keeps only records at or above the line', () => {
    expect(filterByMinConfidence(items, 0.7).map((s) => s.max_confidence)).toEqual([0.75, 0.9])
    expect(filterByMinConfidence(items, 0.6)).toHaveLength(3) // boundary is inclusive
  })
})

describe('filterCapturesByMinConfidence', () => {
  it('keeps captures whose ORIGINAL segment ordinal survives the filter', () => {
    // segments in start-time order: ordinals 1(0.9) 2(0.4) 3(0.8);
    // a 0.7 filter keeps ordinals 1 and 3 -- NOT filtered-array positions 1,2
    const segments = [seg(0.9), seg(0.4), seg(0.8)]
    const captures = [cap(1), cap(2), cap(3)]
    const kept = filterCapturesByMinConfidence(captures, segments, 0.7)
    expect(kept.map((c) => c.segment_index)).toEqual([1, 3])
  })

  it('keeps everything when min is 0', () => {
    const captures = [cap(1), cap(2)]
    expect(filterCapturesByMinConfidence(captures, [seg(0.1)], 0)).toHaveLength(2)
  })
})
