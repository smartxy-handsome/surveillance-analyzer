import axios from 'axios'

const api = axios.create({
  baseURL: '/api',
})

export interface Job {
  id: string
  filename: string
  status: string
  created_at: string
  total_segments: number
  total_person_time: number
  processing_time_seconds?: number
  dropped_frames?: number | null
  queue_position?: number | null
  progress?: {
    processed: number
    total: number
    percent: number
  } | null
  video_metadata?: {
    duration?: number
    fps?: number
    width?: number
    height?: number
    total_frames?: number
  }
}

export interface Segment {
  id: number
  start_time: number
  end_time: number
  start_time_formatted: string
  end_time_formatted: string
  duration_seconds: number
  detection_count: number
  avg_confidence: number
  max_confidence: number
}

export interface BrowseItem {
  name: string
  path: string
  is_dir: boolean
  size_mb?: number
}

export interface BrowseResult {
  current: string
  parent: string | null
  items: BrowseItem[]
}

export async function browse(path: string): Promise<BrowseResult> {
  const { data } = await api.get<BrowseResult>('/browse', { params: { path } })
  return data
}

export async function createJob(filePath: string): Promise<Job> {
  const { data } = await api.post<Job>('/jobs', { file_path: filePath })
  return data
}

export async function listJobs(): Promise<Job[]> {
  const { data } = await api.get<Job[]>('/jobs')
  return data
}

export async function getJob(id: string): Promise<Job> {
  const { data } = await api.get<Job>(`/jobs/${id}`)
  return data
}

export async function deleteJob(id: string): Promise<void> {
  await api.delete(`/jobs/${id}`)
}

export async function getSegments(jobId: string): Promise<Segment[]> {
  const { data } = await api.get<Segment[]>(`/jobs/${jobId}/segments`)
  return data
}

export interface Capture {
  id: number
  segment_index: number
  timestamp: number
  timestamp_formatted: string
  confidence: number
  crop_url: string
  annotated_url: string
}

export async function getCaptures(jobId: string): Promise<Capture[]> {
  const { data } = await api.get<Capture[]>(`/jobs/${jobId}/captures`)
  return data
}

export interface SystemPath {
  name: string
  path: string
  icon: string
}

export interface SystemPathsResult {
  paths: SystemPath[]
  home: string
}

export async function getSystemPaths(): Promise<SystemPathsResult> {
  const { data } = await api.get<SystemPathsResult>('/system/paths')
  return data
}
