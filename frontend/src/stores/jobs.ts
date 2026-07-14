import { defineStore } from 'pinia'
import { ref } from 'vue'
import { listJobs, getJob, getSegments, getCaptures, deleteJob } from '../api/client'
import type { Job, Segment, Capture } from '../api/client'

export const useJobsStore = defineStore('jobs', () => {
  const jobs = ref<Job[]>([])
  const currentJob = ref<Job | null>(null)
  const segments = ref<Segment[]>([])
  const captures = ref<Capture[]>([])
  const loading = ref(false)

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

  async function fetchCaptures(jobId: string) {
    captures.value = await getCaptures(jobId)
  }

  async function removeJob(id: string) {
    await deleteJob(id)
    jobs.value = jobs.value.filter((j) => j.id !== id)
  }

  return { jobs, currentJob, segments, captures, loading, fetchJobs, fetchJob, fetchSegments, fetchCaptures, removeJob }
})
