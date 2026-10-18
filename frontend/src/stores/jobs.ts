import { defineStore } from 'pinia'
import { computed, ref } from 'vue'
import {
  listJobs,
  getJob,
  getSegments,
  getCaptures,
  getVehicleEvents,
  deleteJob,
  getReviews,
  putReview,
  deleteReview,
  getMissedEvents,
  addMissedEvent,
  deleteMissedEvent,
} from '../api/client'
import type {
  Job,
  Segment,
  Capture,
  VehicleEvent,
  ReviewMark,
  ReviewTargetType,
  ReviewVerdict,
  MissedEvent,
} from '../api/client'

export const useJobsStore = defineStore('jobs', () => {
  const jobs = ref<Job[]>([])
  const currentJob = ref<Job | null>(null)
  const segments = ref<Segment[]>([])
  const captures = ref<Capture[]>([])
  const vehicleEvents = ref<VehicleEvent[]>([])
  const loading = ref(false)
  const reviewMarks = ref<Map<string, ReviewVerdict>>(new Map())
  const missedEvents = ref<MissedEvent[]>([])

  const reviewKey = (type: ReviewTargetType, id: number) => `${type}:${id}`

  function verdictFor(type: ReviewTargetType, id: number): ReviewVerdict | undefined {
    return reviewMarks.value.get(reviewKey(type, id))
  }

  const reviewedCount = computed(() => reviewMarks.value.size)

  async function fetchReviews(jobId: string) {
    const marks = await getReviews(jobId)
    reviewMarks.value = new Map(marks.map((m) => [reviewKey(m.target_type, m.target_id), m.verdict]))
  }

  async function setReview(
    jobId: string,
    type: ReviewTargetType,
    id: number,
    verdict: ReviewVerdict
  ) {
    // Optimistic: the button should flip instantly while the request flies.
    const key = reviewKey(type, id)
    const previous = reviewMarks.value.get(key)
    if (previous === verdict) {
      // Clicking the active verdict clears the mark.
      reviewMarks.value.delete(key)
      reviewMarks.value = new Map(reviewMarks.value)
      await deleteReview(jobId, type, id)
      return
    }
    reviewMarks.value.set(key, verdict)
    reviewMarks.value = new Map(reviewMarks.value)
    try {
      await putReview(jobId, type, id, verdict)
    } catch (error) {
      if (previous === undefined) {
        reviewMarks.value.delete(key)
      } else {
        reviewMarks.value.set(key, previous)
      }
      reviewMarks.value = new Map(reviewMarks.value)
      throw error
    }
  }

  async function fetchMissedEvents(jobId: string) {
    missedEvents.value = await getMissedEvents(jobId)
  }

  async function appendMissedEvent(
    jobId: string,
    startSeconds: number,
    endSeconds: number,
    note?: string | null
  ) {
    const ev = await addMissedEvent(jobId, startSeconds, endSeconds, note)
    missedEvents.value = [...missedEvents.value, ev].sort(
      (a, b) => a.start_seconds - b.start_seconds
    )
  }

  async function removeMissedEvent(jobId: string, eventId: number) {
    await deleteMissedEvent(jobId, eventId)
    missedEvents.value = missedEvents.value.filter((e) => e.id !== eventId)
  }

  function resetDetailState() {
    segments.value = []
    captures.value = []
    vehicleEvents.value = []
    reviewMarks.value = new Map()
    missedEvents.value = []
  }

  async function fetchJobs() {
    loading.value = true
    try {
      jobs.value = await listJobs()
    } finally {
      loading.value = false
    }
  }

  async function fetchJob(id: string) {
    loading.value = true
    try {
      currentJob.value = await getJob(id)
    } finally {
      loading.value = false
    }
  }

  async function fetchSegments(jobId: string) {
    segments.value = await getSegments(jobId)
  }

  async function fetchCaptures(jobId: string, target?: 'person' | 'vehicle') {
    captures.value = await getCaptures(jobId, target)
  }

  async function fetchVehicleEvents(jobId: string) {
    vehicleEvents.value = await getVehicleEvents(jobId)
  }

  async function removeJob(id: string) {
    await deleteJob(id)
    jobs.value = jobs.value.filter((j) => j.id !== id)
  }

  return {
    jobs,
    currentJob,
    segments,
    captures,
    vehicleEvents,
    loading,
    reviewMarks,
    missedEvents,
    reviewedCount,
    fetchJobs,
    fetchJob,
    fetchSegments,
    fetchCaptures,
    fetchVehicleEvents,
    fetchReviews,
    setReview,
    verdictFor,
    fetchMissedEvents,
    appendMissedEvent,
    removeMissedEvent,
    resetDetailState,
    removeJob,
  }
})
