import { describe, it, expect, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'
import CollapsibleSection from './CollapsibleSection.vue'

// NOTE: @vue/test-utils' isVisible() is unreliable in jsdom for detached
// trees (getComputedStyle does not cascade inline display:none), so the
// tests assert the explicit is-collapsed class instead.

beforeEach(() => {
  localStorage.clear()
})

describe('CollapsibleSection', () => {
  it('is open by default and shows its content', () => {
    const wrapper = mount(CollapsibleSection, {
      props: { title: '时间段' },
      slots: { header: '📋 时间段 (3)', default: '<p>body</p>' },
    })
    expect(wrapper.find('.section-header').attributes('aria-expanded')).toBe('true')
    expect(wrapper.find('.section-body').classes()).not.toContain('is-collapsed')
    expect(wrapper.text()).toContain('时间段 (3)')
  })

  it('collapses on header click and expands again', async () => {
    const wrapper = mount(CollapsibleSection, {
      props: { title: 'x' },
      slots: { default: '<p>body</p>' },
    })
    await wrapper.find('.section-header').trigger('click')
    expect(wrapper.find('.section-header').attributes('aria-expanded')).toBe('false')
    expect(wrapper.find('.section-body').classes()).toContain('is-collapsed')

    await wrapper.find('.section-header').trigger('click')
    expect(wrapper.find('.section-body').classes()).not.toContain('is-collapsed')
  })

  it('persists collapsed state under its storage key', async () => {
    const wrapper = mount(CollapsibleSection, {
      props: { title: 'x', storageKey: 'segments' },
      slots: { default: '<p>body</p>' },
    })
    await wrapper.find('.section-header').trigger('click')
    expect(localStorage.getItem('section-open:segments')).toBe('0')

    const remounted = mount(CollapsibleSection, {
      props: { title: 'x', storageKey: 'segments' },
      slots: { default: '<p>body</p>' },
    })
    expect(remounted.find('.section-body').classes()).toContain('is-collapsed')
  })

  it('ignores other sections\' stored state', () => {
    localStorage.setItem('section-open:other', '0')
    const wrapper = mount(CollapsibleSection, {
      props: { title: 'x', storageKey: 'segments' },
      slots: { default: '<p>body</p>' },
    })
    expect(wrapper.find('.section-body').classes()).not.toContain('is-collapsed')
  })
})
