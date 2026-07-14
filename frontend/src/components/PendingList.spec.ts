import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import PendingList from './PendingList.vue'
import type { PendingItem } from '../utils/submitItems'

function item(overrides: Partial<PendingItem> = {}): PendingItem {
  return {
    id: '1',
    path: 'D:\\vids\\a.mp4',
    filename: 'a.mp4',
    status: 'pending',
    ...overrides,
  }
}

describe('PendingList', () => {
  it('renders nothing when the list is empty', () => {
    const wrapper = mount(PendingList, { props: { items: [] } })
    expect(wrapper.find('.pending-list').exists()).toBe(false)
  })

  it('lists items with their filename and path, and shows the count', () => {
    const wrapper = mount(PendingList, {
      props: {
        items: [
          item({ id: '1', filename: 'a.mp4', path: 'D:\\vids\\a.mp4' }),
          item({ id: '2', filename: 'b.mp4', path: 'D:\\vids\\b.mp4' }),
        ],
      },
    })
    const names = wrapper.findAll('.item .filename').map((n) => n.text())
    expect(names).toEqual(['a.mp4', 'b.mp4'])
    expect(wrapper.find('.title').text()).toContain('2')
    expect(wrapper.find('.submit-btn').text()).toContain('2')
  })

  it('emits remove with the item id when the remove button is clicked', async () => {
    const wrapper = mount(PendingList, {
      props: { items: [item({ id: 'abc', filename: 'a.mp4' })] },
    })
    await wrapper.find('.item .remove').trigger('click')
    expect(wrapper.emitted('remove')).toBeTruthy()
    expect(wrapper.emitted('remove')![0]).toEqual(['abc'])
  })

  it('emits submit when the submit button is clicked', async () => {
    const wrapper = mount(PendingList, {
      props: { items: [item()] },
    })
    await wrapper.find('.submit-btn').trigger('click')
    expect(wrapper.emitted('submit')).toBeTruthy()
  })

  it('shows the error message and marks the row as error for failed items', () => {
    const wrapper = mount(PendingList, {
      props: {
        items: [
          item({
            id: '1',
            filename: 'bad.wmv',
            path: 'D:\\bad.wmv',
            status: 'error',
            error: 'Unsupported format: .wmv',
          }),
        ],
      },
    })
    const row = wrapper.find('.item')
    expect(row.classes()).toContain('error')
    expect(wrapper.find('.error-msg').text()).toBe('Unsupported format: .wmv')
  })

  it('shows a spinner indicator for submitting items', () => {
    const wrapper = mount(PendingList, {
      props: { items: [item({ status: 'submitting' })] },
    })
    const row = wrapper.find('.item')
    expect(row.classes()).toContain('submitting')
    expect(wrapper.find('.status').exists()).toBe(true)
  })
})
