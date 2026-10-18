import axios from 'axios'

const api = axios.create({
  baseURL: '/api',
})

// Optional API-key guard (server config web.auth_enabled). The key is
// remembered in localStorage; on a 401 the SPA asks once and retries.
const API_KEY_STORAGE = 'surveillance-api-key'

export function getStoredApiKey(): string {
  return localStorage.getItem(API_KEY_STORAGE) ?? ''
}

export function setStoredApiKey(key: string): void {
  localStorage.setItem(API_KEY_STORAGE, key)
}

api.interceptors.request.use((config) => {
  const key = getStoredApiKey()
  if (key) {
    config.headers['X-API-Key'] = key
  }
  return config
})

api.interceptors.response.use(undefined, (error) => {
  const config = error?.config
  if (error?.response?.status === 401 && config && !config._retriedAuth) {
    const key = window.prompt('服务器已开启 API Key 验证，请输入密钥：')
    if (key) {
      setStoredApiKey(key.trim())
      config._retriedAuth = true
      config.headers['X-API-Key'] = key.trim()
      return api.request(config)
    }
  }
  return Promise.reject(error)
})

export interface Job {
  id: string
  filename: string
  status: string
  created_at: string
  detection_target: string
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

export type DetectionTarget = 'person' | 'vehicle' | 'both'

export interface VehicleEvent {
  id: number
  enter_time: number
  exit_time: number
  enter_time_formatted: string
  exit_time_formatted: string
  duration_seconds: number
  detection_count: number
  avg_confidence: number
  max_confidence: number
  plate_number: string | null
  plate_confidence: number | null
  plate_type: string | null
  enter_capture: Capture | null
  exit_capture: Capture | null
  plate_capture: Capture | null
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

export async function createJob(
  filePath: string,
  detectionTarget: DetectionTarget = 'person'
): Promise<Job> {
  const { data } = await api.post<Job>('/jobs', {
    file_path: filePath,
    detection_target: detectionTarget,
  })
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
  annotated_url?: string | null
  kind?: string
}

export async function getCaptures(
  jobId: string,
  target?: 'person' | 'vehicle'
): Promise<Capture[]> {
  const { data } = await api.get<Capture[]>(`/jobs/${jobId}/captures`, {
    params: target ? { target } : undefined,
  })
  return data
}

export async function getVehicleEvents(jobId: string): Promise<VehicleEvent[]> {
  const { data } = await api.get<VehicleEvent[]>(`/jobs/${jobId}/vehicle-events`)
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


export type ReviewTargetType = 'capture' | 'segment' | 'vehicle_event'
export type ReviewVerdict = 'good' | 'bad'

export interface ReviewMark {
  target_type: ReviewTargetType
  target_id: number
  verdict: ReviewVerdict
}

export interface MissedEvent {
  id: number
  start_seconds: number
  end_seconds: number
  note: string | null
}

export async function getReviews(jobId: string): Promise<ReviewMark[]> {
  const { data } = await api.get<ReviewMark[]>(`/jobs/${jobId}/reviews`)
  return data
}

export async function putReview(
  jobId: string,
  targetType: ReviewTargetType,
  targetId: number,
  verdict: ReviewVerdict
): Promise<void> {
  await api.put(`/jobs/${jobId}/reviews`, {
    target_type: targetType,
    target_id: targetId,
    verdict,
  })
}

export async function deleteReview(
  jobId: string,
  targetType: ReviewTargetType,
  targetId: number
): Promise<void> {
  await api.delete(`/jobs/${jobId}/reviews/${targetType}/${targetId}`)
}

export async function getMissedEvents(jobId: string): Promise<MissedEvent[]> {
  const { data } = await api.get<MissedEvent[]>(`/jobs/${jobId}/missed-events`)
  return data
}

export async function addMissedEvent(
  jobId: string,
  startSeconds: number,
  endSeconds: number,
  note?: string | null
): Promise<MissedEvent> {
  const { data } = await api.post<MissedEvent>(`/jobs/${jobId}/missed-events`, {
    start_seconds: startSeconds,
    end_seconds: endSeconds,
    note: note ?? null,
  })
  return data
}

export async function deleteMissedEvent(jobId: string, eventId: number): Promise<void> {
  await api.delete(`/jobs/${jobId}/missed-events/${eventId}`)
}
