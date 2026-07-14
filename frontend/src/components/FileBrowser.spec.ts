import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import FileBrowser from './FileBrowser.vue'
import * as api from '../api/client'

vi.mock('../api/client', () => ({
  browse: vi.fn(),
  getSystemPaths: vi.fn().mockResolvedValue({ paths: [], home: '' }),
}))

function fileItems(): Awaited<ReturnType<typeof api.browse>> {
  return {
    current: 'D:\\vids',
    parent: '',
    items: [
      { name: 'a.mp4', path: 'D:\\vids\\a.mp4', is_dir: false, size_mb: 1 },
      { name: 'b.mp4', path: 'D:\\vids\\b.mp4', is_dir: false, size_mb: 2 },
    ],
  }
}

describe('FileBrowser multi-select', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    document.body.innerHTML = ''
  })

  it('toggles file selection and emits the selected paths on confirm', async () => {
    vi.mocked(api.browse).mockResolvedValue(fileItems())
    const wrapper = mount(FileBrowser)
    ;(wrapper.vm as any).open()
    await flushPromises()

    const files = document.querySelectorAll('.file-item:not(.dir)')
    expect(files.length).toBe(2)

    await (files[0] as HTMLElement).click()
    await (files[1] as HTMLElement).click()

    const confirm = document.querySelector('.confirm-btn') as HTMLButtonElement
    await confirm.click()

    const emitted = wrapper.emitted('select')
    expect(emitted).toBeTruthy()
    expect(emitted![0][0]).toEqual(['D:\\vids\\a.mp4', 'D:\\vids\\b.mp4'])
  })

  it('deselects a file when clicked again', async () => {
    vi.mocked(api.browse).mockResolvedValue(fileItems())
    const wrapper = mount(FileBrowser)
    ;(wrapper.vm as any).open()
    await flushPromises()

    const file = document.querySelector('.file-item') as HTMLElement
    await file.click() // select
    await file.click() // deselect

    const confirm = document.querySelector('.confirm-btn') as HTMLButtonElement
    await confirm.click()

    const emitted = wrapper.emitted('select')
    expect(emitted![0][0]).toEqual([])
  })

  it('navigates into a directory instead of selecting it', async () => {
    vi.mocked(api.browse)
      .mockResolvedValueOnce({
        current: 'D:\\vids',
        parent: '',
        items: [{ name: 'sub', path: 'D:\\vids\\sub', is_dir: true }],
      })
      .mockResolvedValueOnce({ current: 'D:\\vids\\sub', parent: 'D:\\vids', items: [] })

    const wrapper = mount(FileBrowser)
    ;(wrapper.vm as any).open()
    await flushPromises()

    const dir = document.querySelector('.file-item.dir') as HTMLElement
    await dir.click()
    await flushPromises()

    // Two browse calls: initial open + navigating into the dir
    expect(api.browse).toHaveBeenCalledTimes(2)
    expect(vi.mocked(api.browse).mock.calls[1][0]).toBe('D:\\vids\\sub')
    // Nothing selected yet
    const confirm = document.querySelector('.confirm-btn') as HTMLButtonElement
    await confirm.click()
    expect(wrapper.emitted('select')![0][0]).toEqual([])
  })
})
