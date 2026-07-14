import { describe, it, expect, vi } from 'vitest'
import { submitItems, extractError, basename } from './submitItems'
import type { PendingItem } from './submitItems'
import type { Job } from '../api/client'

function makeItem(path: string): PendingItem {
  return { id: path, path, filename: basename(path), status: 'pending' }
}

function makeJob(id: string, filename: string): Job {
  return {
    id,
    filename,
    status: 'pending',
    created_at: '',
    total_segments: 0,
    total_person_time: 0,
  }
}

describe('submitItems', () => {
  it('returns ok outcomes for all successful creations, in order', async () => {
    const createJob = vi
      .fn()
      .mockResolvedValueOnce(makeJob('job-1', 'a.mp4'))
      .mockResolvedValueOnce(makeJob('job-2', 'b.mp4'))

    const outcomes = await submitItems(
      [makeItem('D:\\a.mp4'), makeItem('D:\\b.mp4')],
      createJob
    )

    expect(outcomes).toEqual([
      { id: 'D:\\a.mp4', ok: true, jobId: 'job-1' },
      { id: 'D:\\b.mp4', ok: true, jobId: 'job-2' },
    ])
    expect(createJob).toHaveBeenCalledTimes(2)
    expect(createJob).toHaveBeenNthCalledWith(1, 'D:\\a.mp4')
    expect(createJob).toHaveBeenNthCalledWith(2, 'D:\\b.mp4')
  })

  it('marks a failed item with the backend detail without stopping the rest', async () => {
    const createJob = vi
      .fn()
      .mockResolvedValueOnce(makeJob('job-1', 'a.mp4'))
      .mockRejectedValueOnce({ response: { data: { detail: 'Unsupported format: .wmv' } } })

    const outcomes = await submitItems(
      [makeItem('D:\\a.mp4'), makeItem('D:\\bad.wmv')],
      createJob
    )

    expect(outcomes[0].ok).toBe(true)
    expect(outcomes[0].jobId).toBe('job-1')
    expect(outcomes[1].ok).toBe(false)
    expect(outcomes[1].error).toBe('Unsupported format: .wmv')
  })
})

describe('extractError', () => {
  it('extracts detail from an axios-like error', () => {
    expect(extractError({ response: { data: { detail: 'File not found' } } })).toBe('File not found')
  })
  it('falls back to Error.message', () => {
    expect(extractError(new Error('boom'))).toBe('boom')
  })
  it('falls back to a default message for unknown shapes', () => {
    expect(extractError('weird')).toBe('创建任务失败')
  })
})

describe('basename', () => {
  it('handles Windows backslash paths', () => {
    expect(basename('D:\\videos\\cam.mp4')).toBe('cam.mp4')
  })
  it('handles POSIX slash paths', () => {
    expect(basename('/home/u/v.mp4')).toBe('v.mp4')
  })
})
