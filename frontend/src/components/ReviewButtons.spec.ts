import { describe, it, expect, beforeEach, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'

// The store performs real axios calls; keep the component tests offline.
vi.mock('../api/client', () => ({
  putReview: vi.fn().mockResolvedValue(undefined),
  deleteReview: vi.fn().mockResolvedValue(undefined),
  getReviews: vi.fn().mockResolvedValue([]),
  getMissedEvents: vi.fn().mockResolvedValue([]),
  addMissedEvent: vi.fn(),
  deleteMissedEvent: vi.fn().mockResolvedValue(undefined),
}))

import ReviewButtons from './ReviewButtons.vue'
import { useJobsStore } from '../stores/jobs'

describe('ReviewButtons', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  const mountBtns = () => mount(ReviewButtons, {
    props: { jobId: 'job-1', targetType: 'capture', targetId: 5, goodLabel: '✓ 是人体', badLabel: '✗ 非人体' },
  })

  it('renders both buttons with no active verdict initially', () => {
    const wrapper = mountBtns()
    const good = wrapper.find('.review-btn.good')
    const bad = wrapper.find('.review-btn.bad')
    expect(good.exists()).toBe(true)
    expect(good.classes()).not.toContain('active')
    expect(bad.classes()).not.toContain('active')
  })

  it('marks good optimistically on click and stores the verdict', async () => {
    const wrapper = mountBtns()
    const store = useJobsStore()
    await wrapper.find('.review-btn.good').trigger('click')
    expect(wrapper.find('.review-btn.good').classes()).toContain('active')
    expect(store.verdictFor('capture', 5)).toBe('good')
  })

  it('clicking the active verdict clears the mark', async () => {
    const wrapper = mountBtns()
    const store = useJobsStore()
    await wrapper.find('.review-btn.good').trigger('click')
    await wrapper.find('.review-btn.good').trigger('click')
    expect(store.verdictFor('capture', 5)).toBeUndefined()
    expect(wrapper.find('.review-btn.good').classes()).not.toContain('active')
  })

  it('reflects a verdict already present in the store', async () => {
    const store = useJobsStore()
    await store.setReview('job-1', 'capture', 5, 'bad')
    const wrapper = mountBtns()
    expect(wrapper.find('.review-btn.bad').classes()).toContain('active')
  })

  it('switching from good to bad replaces the verdict', async () => {
    const wrapper = mountBtns()
    const store = useJobsStore()
    await wrapper.find('.review-btn.good').trigger('click')
    await wrapper.find('.review-btn.bad').trigger('click')
    expect(store.verdictFor('capture', 5)).toBe('bad')
    expect(wrapper.find('.review-btn.good').classes()).not.toContain('active')
    expect(wrapper.find('.review-btn.bad').classes()).toContain('active')
  })
})
