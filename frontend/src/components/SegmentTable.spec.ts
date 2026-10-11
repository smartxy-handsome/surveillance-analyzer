import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import SegmentTable from './SegmentTable.vue'
import type { Segment } from '../api/client'

function seg(overrides: Partial<Segment>): Segment {
  return {
    id: 1,
    start_time: 0,
    end_time: 2,
    start_time_formatted: '00:00:00',
    end_time_formatted: '00:00:02',
    duration_seconds: 2,
    detection_count: 5,
    avg_confidence: 0.5,
    max_confidence: 0.5,
    ...overrides,
  }
}

const rows = (wrapper: ReturnType<typeof mount>) =>
  wrapper.findAll('tbody tr')

describe('SegmentTable confidence tiers', () => {
  const segments = [
    seg({ id: 1, max_confidence: 0.72, avg_confidence: 0.6 }),
    seg({ id: 2, max_confidence: 0.38, avg_confidence: 0.33 }),
    seg({ id: 3, max_confidence: 0.51, avg_confidence: 0.45 }),
  ]

  it('tags each row 确认 or 疑似 by peak confidence', () => {
    const wrapper = mount(SegmentTable, { props: { segments } })
    const tiers = rows(wrapper).map((r) => r.find('.tier-badge').text())
    expect(tiers).toEqual(['确认', '疑似', '确认'])
  })

  it('shows the suspected toggle with a count and hides suspected rows when off', async () => {
    const wrapper = mount(SegmentTable, { props: { segments } })
    expect(wrapper.find('.tier-toggle').text()).toContain('1 条')
    await wrapper.find('input[type="checkbox"]').setValue(false)
    expect(rows(wrapper).length).toBe(2)
    expect(rows(wrapper).map((r) => r.find('.tier-badge').text())).toEqual(['确认', '确认'])
  })

  it('keeps original numbering stable when filtering', async () => {
    const wrapper = mount(SegmentTable, { props: { segments } })
    await wrapper.find('input[type="checkbox"]').setValue(false)
    const indices = rows(wrapper).map((r) => r.find('.index').text())
    expect(indices).toEqual(['1', '3'])
  })

  it('renders no toolbar when every record is confirmed', () => {
    const wrapper = mount(SegmentTable, {
      props: { segments: [seg({ max_confidence: 0.8 })] },
    })
    expect(wrapper.find('.tier-toggle').exists()).toBe(false)
  })
})
