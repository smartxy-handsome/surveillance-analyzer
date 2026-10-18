import { describe, it, expect, beforeEach, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'

vi.mock('../api/client', () => ({
  putReview: vi.fn().mockResolvedValue(undefined),
  deleteReview: vi.fn().mockResolvedValue(undefined),
  getReviews: vi.fn().mockResolvedValue([]),
  getMissedEvents: vi.fn().mockResolvedValue([]),
  addMissedEvent: vi.fn().mockResolvedValue({
    id: 9,
    start_seconds: 60,
    end_seconds: 75,
    note: '左侧门口',
  }),
  deleteMissedEvent: vi.fn().mockResolvedValue(undefined),
}))

import MissedEvents from './MissedEvents.vue'
import { useJobsStore } from '../stores/jobs'

describe('MissedEvents', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  const mountPanel = () => mount(MissedEvents, { props: { jobId: 'job-1' } })

  it('submits a valid entry and shows it in the list', async () => {
    const wrapper = mountPanel()
    const inputs = wrapper.findAll('input[type="number"]')
    await inputs[0].setValue(1) // start 分
    await inputs[1].setValue(0) // start 秒
    await inputs[2].setValue(1) // end 分
    await inputs[3].setValue(15) // end 秒
    await wrapper.find('input.note').setValue('左侧门口')
    await wrapper.find('form').trigger('submit')

    const store = useJobsStore()
    expect(store.missedEvents).toHaveLength(1)
    expect(store.missedEvents[0]).toMatchObject({
      id: 9,
      start_seconds: 60,
      end_seconds: 75,
      note: '左侧门口',
    })
    expect(wrapper.find('.list li').text()).toContain('1:00')
  })

  it('rejects an end time earlier than the start', async () => {
    const wrapper = mountPanel()
    const inputs = wrapper.findAll('input[type="number"]')
    await inputs[0].setValue(2)
    await inputs[1].setValue(0)
    await inputs[2].setValue(1)
    await inputs[3].setValue(0)
    await wrapper.find('form').trigger('submit')

    expect(wrapper.find('.error').text()).toContain('结束时间必须晚于开始时间')
    expect(useJobsStore().missedEvents).toHaveLength(0)
  })

  it('removes an entry from the list', async () => {
    const store = useJobsStore()
    await store.appendMissedEvent('job-1', 60, 75, null)
    const wrapper = mountPanel()
    expect(wrapper.findAll('.list li')).toHaveLength(1)
    await wrapper.find('.list .remove').trigger('click')
    expect(store.missedEvents).toHaveLength(0)
  })
})
