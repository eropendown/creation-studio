const BASE = '/api'

export interface OutlineRequest {
  genre: string
  synopsis: string
  style: string
  scene_count: number
}

export interface OutlineSummary {
  outline_id: string
  title: string
  source_type: string
  style: string
  genre: string
  total_scenes: number
  estimated_duration: number
  outline_status: string
  images_done: number
  created_at: number
}

export interface GenerateRequest {
  outline_id: string
}

export interface GenerateResponse {
  job_id: string
  message: string
  ws_url: string
}

export interface JobStatus {
  job_id: string
  overall_status: string
  overall_progress: number
  error_message: string
  agents: Record<string, { status: string; message: string; progress: number }>
  outline: Record<string, unknown> | null
  final_video_url: string
  jianying_draft_dir: string
}

export interface SystemConfig {
  llm: { provider: string; api_key: string; base_url: string; model: string; temperature: number; max_tokens: number }
  tts: { provider: string; api_key: string; voice_id: string; speed: number }
  video: { mode: string; fps: number; resolution: string; subtitle_enabled: boolean }
  prompts: Record<string, string>
}

async function post<T>(url: string, body: unknown): Promise<T> {
  const res = await fetch(BASE + url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({}))
    throw new Error(err.detail || `HTTP ${res.status}`)
  }
  return res.json()
}

async function get<T>(url: string): Promise<T> {
  const res = await fetch(BASE + url)
  if (!res.ok) throw new Error(`HTTP ${res.status}`)
  return res.json()
}

async function del(url: string): Promise<void> {
  const res = await fetch(BASE + url, { method: 'DELETE' })
  if (!res.ok) {
    const err = await res.json().catch(() => ({}))
    throw new Error(err.detail || `HTTP ${res.status}`)
  }
}

export const mangaApi = {
  createOutline: (req: OutlineRequest) =>
    post<{ outline: Record<string, unknown>; message: string }>('/outline', req),

  outlines: () => get<OutlineSummary[]>('/outlines'),

  outline: (id: string) => get<Record<string, unknown>>(`/outline/${id}`),

  deleteOutline: (id: string) => del(`/outline/${id}`),

  generate: (req: GenerateRequest) =>
    post<GenerateResponse>('/generate', req),

  jobs: () => get<{ jobs: JobStatus[] }>('/jobs'),

  job: (id: string) => get<JobStatus>(`/jobs/${id}`),

  uploadImage: async (outlineId: string, sceneId: number, file: File) => {
    const fd = new FormData()
    fd.append('file', file)
    const res = await fetch(`${BASE}/outline/${outlineId}/scene/${sceneId}/image`, {
      method: 'POST', body: fd,
    })
    if (!res.ok) {
      const err = await res.json().catch(() => ({}))
      throw new Error(err.detail || `HTTP ${res.status}`)
    }
    return res.json()
  },

  getConfig: () => get<SystemConfig>('/config'),

  saveConfig: (config: SystemConfig) =>
    post<SystemConfig>('/config', { config }),

  resetConfig: () =>
    post<SystemConfig>('/config/reset', {}),

  /** 将已完成的小说会话直接导入为漫剧大纲 */
  novelToManga: (sessionId: string, opts: {
    style?: string
    scene_count?: number
    focus_range?: string
  }) =>
    post<{ outline: Record<string, unknown>; message: string }>(
      `/novel/sessions/${sessionId}/to-manga`,
      {
        session_id:  sessionId,
        style:       opts.style ?? '古风仙侠',
        scene_count: opts.scene_count ?? 10,
        focus_range: opts.focus_range ?? '',
      }
    ),

  /** 直接测试工具调用 */
  toolCall: (tool: string, query: string) =>
    post<{ tool: string; success: boolean; summary: string; content: string }>(
      '/tools/call', { tool, query }
    ),
}
