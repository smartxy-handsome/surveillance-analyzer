import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import TimelineViewer from './TimelineViewer.vue'
import type { Segment, VehicleEvent } from '../api/client'

function segment(overrides: Partial<Segment> = {}): Segment {
  return {
    id: 1,
    start_time: 10,
    end_time: 20,
    start_time_formatted: '00:00:10',
    end_time_formatted: '00:00:20',
    duration_seconds: 10,
    detection_count: 5,
    avg_confidence: 0.8,
    max_confidence: 0.9,
    is_suspected: false,
    source_key: null,
    ...overrides,
  } as Segment
}

function event(overrides: Partial<VehicleEvent> = {}): VehicleEvent {
  return {
    id: 1,
    enter_time: 30,
    exit_time: 60,
    enter_time_formatted: '00:00:30',
    exit_time_formatted: '00:01:00',
    duration_seconds: 30,
    detection_count: 8,
    avg_confidence: 0.7,
    max_confidence: 0.85,
    plate_number: null,
    plate_confidence: null,
    plate_type: null,
    enter_capture: null,
    exit_capture: null,
    plate_capture: null,
    ...overrides,
  }
}

describe('TimelineViewer', () => {
  it('renders one bar per vehicle event, positioned by enter/exit time', () => {
    const wrapper = mount(TimelineViewer, {
      props: {
        events: [event(), event({ id: 2, enter_time: 90, exit_time: 120 })],
        totalDuration: 300,
      },
    })
    const bars = wrapper.findAll('.segment-bar')
    expect(bars).toHaveLength(2)
    // enter 30s of 300s -> 10%; span 30s -> 10%
    expect(bars[0].attributes('style')).toContain('left: 10%')
    expect(bars[0].attributes('style')).toContain('width: 10%')
    expect(bars[1].attributes('style')).toContain('left: 30%')
    expect(bars[0].classes()).toContain('vehicle')
  })

  it('shows the plate number and enter/exit times in the tooltip for vehicle events', () => {
    const wrapper = mount(TimelineViewer, {
      props: {
        events: [event({ plate_number: '京A12345' })],
        totalDuration: 300,
      },
    })
    expect(wrapper.find('.tooltip-label').text()).toContain('车辆 1')
    expect(wrapper.find('.tooltip-label').text()).toContain('00:00:30')
    expect(wrapper.find('.tooltip-plate').text()).toContain('京A12345')
  })

  it('omits the plate line when no plate was recognized', () => {
    const wrapper = mount(TimelineViewer, {
      props: { events: [event()], totalDuration: 300 },
    })
    expect(wrapper.find('.tooltip-plate').exists()).toBe(false)
  })

  it('still renders person segments via the segments prop (backward compatible)', () => {
    const wrapper = mount(TimelineViewer, {
      props: { segments: [segment()], totalDuration: 100 },
    })
    const bars = wrapper.findAll('.segment-bar')
    expect(bars).toHaveLength(1)
    expect(bars[0].classes()).not.toContain('vehicle')
    expect(wrapper.find('.tooltip-label').text()).toContain('时间段 1')
  })

  it('renders no bars when total duration is unknown', () => {
    const wrapper = mount(TimelineViewer, {
      props: { events: [event()], totalDuration: 0 },
    })
    expect(wrapper.findAll('.segment-bar')).toHaveLength(0)
  })
})
