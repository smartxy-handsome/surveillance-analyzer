import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import VehicleEventTable from './VehicleEventTable.vue'
import type { VehicleEvent } from '../api/client'

function event(overrides: Partial<VehicleEvent>): VehicleEvent {
  return {
    id: 1,
    enter_time: 10,
    exit_time: 25,
    enter_time_formatted: '00:00:10',
    exit_time_formatted: '00:00:25',
    duration_seconds: 15,
    detection_count: 12,
    avg_confidence: 0.8,
    max_confidence: 0.9,
    plate_number: null,
    plate_confidence: null,
    plate_type: null,
    enter_capture: null,
    exit_capture: null,
    plate_capture: null,
    ...overrides,
  }
}

describe('VehicleEventTable', () => {
  it('renders nothing but the empty state when no events', () => {
    const wrapper = mount(VehicleEventTable, { props: { events: [] } })
    expect(wrapper.find('table').exists()).toBe(false)
    expect(wrapper.find('.empty').text()).toContain('未识别到车辆')
  })

  it('shows enter/exit times, plate number and type', () => {
    const wrapper = mount(VehicleEventTable, {
      props: {
        events: [
          event({
            plate_number: '京A12345',
            plate_confidence: 0.97,
            plate_type: 'blue',
          }),
        ],
      },
    })
    const row = wrapper.find('tbody tr')
    expect(row.find('.plate-number').text()).toBe('京A12345')
    expect(row.find('.plate-conf').text()).toContain('97')
    expect(row.find('.plate-type').text()).toContain('蓝牌')
    expect(row.find('.time').text()).toBe('00:00:10')
  })

  it('shows an em-dash with a tooltip when plate recognition failed', () => {
    const wrapper = mount(VehicleEventTable, {
      props: { events: [event({ plate_number: null, plate_type: 'black_hk_macao' })] },
    })
    const plateCell = wrapper.find('.plate-empty')
    expect(plateCell.text()).toBe('—')
    expect(plateCell.attributes('title')).toContain('未能识别')
    expect(wrapper.find('.plate-type').text()).toContain('港澳黑牌')
  })

  it('shows a thumbnail link per capture slot when present', () => {
    const cap = { id: 1, segment_index: 1, timestamp: 10, timestamp_formatted: '', confidence: 0.9, crop_url: '/api/captures/1/image?type=crop', annotated_url: null, kind: 'appearance' }
    const wrapper = mount(VehicleEventTable, {
      props: {
        events: [event({ enter_capture: cap, exit_capture: cap, plate_capture: cap })],
      },
    })
    expect(wrapper.findAll('.thumb').length).toBe(3)
  })

  it('tags rows 确认/疑似 and can hide suspected ones', async () => {
    const wrapper = mount(VehicleEventTable, {
      props: {
        events: [
          event({ id: 1, max_confidence: 0.9, plate_type: 'blue' }),
          event({ id: 2, max_confidence: 0.35, plate_type: 'blue' }),
        ],
      },
    })
    const badges = wrapper.findAll('.tier-badge').map((b) => b.text())
    expect(badges).toEqual(['确认', '疑似'])
    await wrapper.find('input[type="checkbox"]').setValue(false)
    expect(wrapper.findAll('tbody tr').length).toBe(1)
  })
})
