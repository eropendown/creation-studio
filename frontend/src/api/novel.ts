const BASE = '/api'

export interface ChatRequest {
  session_id?: string
  message: string
}

export interface ChatResponse {
  session_id: string
  reply: string
  phase: string
  phase_data?: Record<string, unknown>
}

export interface SessionSummary {
  session_id: string
  title: string
  phase: string
  chapters_done: number
  total_words: number
  created_at: number
  updated_at: number
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

export const novelApi = {
  chat: (req: ChatRequest) =>
    post<ChatResponse>('/novel/chat', req),

  /**
   * 流式聊天 - 使用 fetch + ReadableStream 接收 SSE
   * @param req 请求参数
   * @param onEvent 收到每个事件时的回调
   * @param signal AbortSignal 用于取消
   */
  chatStream: async (
    req: ChatRequest,
    onEvent: (event: Record<string, unknown>) => void,
    signal?: AbortSignal,
  ) => {
    const res = await fetch(BASE + '/novel/chat/stream', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(req),
      signal,
    })

    if (!res.ok) {
      const err = await res.json().catch(() => ({}))
      throw new Error(err.detail || `HTTP ${res.status}`)
    }

    const reader = res.body?.getReader()
    if (!reader) throw new Error('No response body')

    const decoder = new TextDecoder()
    let buffer = ''

    while (true) {
      const { done, value } = await reader.read()
      if (done) break

      buffer += decoder.decode(value, { stream: true })

      // 解析 SSE 格式: data: {...}\n\n
      const lines = buffer.split('\n')
      buffer = lines.pop() || ''

      for (const line of lines) {
        if (line.startsWith('data: ')) {
          try {
            const data = JSON.parse(line.slice(6))
            onEvent(data)
          } catch {
            // 忽略解析错误
          }
        }
      }
    }
  },

  sessions: () =>
    get<SessionSummary[]>('/novel/sessions'),

  session: (id: string) =>
    get<Record<string, unknown>>(`/novel/sessions/${id}`),

  deleteSession: (id: string) =>
    del(`/novel/sessions/${id}`),

  exportUrl: (id: string) =>
    `${BASE}/novel/sessions/${id}/export`,
}
