import { create } from 'zustand'
import { novelApi, SessionSummary } from '../api/novel'

export interface ChatMessage {
  id: string
  role: 'user' | 'assistant'
  content: string
  phase?: string
  phaseData?: Record<string, unknown>
  ts: number
  loading?: boolean
}

interface NovelState {
  sessionId: string | null
  phase: string
  messages: ChatMessage[]
  isLoading: boolean
  error: string | null
  worldview: Record<string, unknown> | null
  outline: Record<string, unknown> | null
  currentChapter: Record<string, unknown> | null
  sessions: SessionSummary[]
  sessionsLoaded: boolean
  abortController: AbortController | null
}

interface NovelActions {
  sendMessage: (text: string) => Promise<void>
  stopStream: () => void
  newSession: () => void
  loadSession: (id: string) => Promise<void>
  loadSessions: () => Promise<void>
  deleteSession: (id: string) => Promise<void>
  setError: (e: string | null) => void
}

let _msgId = 0
const uid = () => `m${++_msgId}_${Date.now()}`

export const useNovelStore = create<NovelState & NovelActions>((set, get) => ({
  sessionId: null,
  phase: 'init',
  messages: [],
  isLoading: false,
  error: null,
  worldview: null,
  outline: null,
  currentChapter: null,
  sessions: [],
  sessionsLoaded: false,
  abortController: null,

  sendMessage: async (text) => {
    const { sessionId, messages, abortController } = get()

    // 取消之前的请求
    if (abortController) {
      abortController.abort()
    }

    const controller = new AbortController()

    // 加入用户消息
    const userMsg: ChatMessage = {
      id: uid(), role: 'user', content: text, ts: Date.now()
    }
    const placeholder: ChatMessage = {
      id: uid(), role: 'assistant', content: '', ts: Date.now(), loading: true
    }

    set({
      messages: [...messages, userMsg, placeholder],
      isLoading: true,
      error: null,
      abortController: controller,
    })

    try {
      await novelApi.chatStream(
        {
          session_id: sessionId ?? undefined,
          message: text,
        },
        (event) => {
          const { messages: currentMessages } = get()

          if (event.type === 'chunk') {
            // 逐字追加内容
            set(s => ({
              messages: s.messages.map(m =>
                m.loading
                  ? { ...m, content: m.content + (event.content as string || '') }
                  : m
              )
            }))
          } else if (event.type === 'phase') {
            // 更新阶段
            const phase = event.phase as string || ''
            const phaseData = event.phase_data as Record<string, unknown> | undefined

            set(s => ({
              phase,
              messages: s.messages.map(m =>
                m.loading ? { ...m, phase } : m
              ),
              ...(phaseData?.worldview ? { worldview: phaseData.worldview as Record<string, unknown> } : {}),
              ...(phaseData?.outline ? { outline: phaseData.outline as Record<string, unknown> } : {}),
              ...(phaseData?.chapter ? { currentChapter: phaseData.chapter as Record<string, unknown> } : {}),
            }))
          } else if (event.type === 'done') {
            // 完成 - 移除 loading 状态
            const sessionId = event.session_id as string
            const phase = event.phase as string
            const phaseData = event.phase_data as Record<string, unknown> | undefined

            set(s => ({
              sessionId,
              phase,
              messages: s.messages.map(m =>
                m.loading ? { ...m, loading: false } : m
              ),
              isLoading: false,
              abortController: null,
              ...(phaseData?.worldview ? { worldview: phaseData.worldview as Record<string, unknown> } : {}),
              ...(phaseData?.outline ? { outline: phaseData.outline as Record<string, unknown> } : {}),
              ...(phaseData?.chapter ? { currentChapter: phaseData.chapter as Record<string, unknown> } : {}),
            }))
          } else if (event.type === 'error') {
            const msg = event.message as string || '未知错误'
            set(s => ({
              messages: s.messages.filter(m => !m.loading),
              isLoading: false,
              error: msg,
              abortController: null,
            }))
          }
        },
        controller.signal
      )
    } catch (e) {
      if ((e as Error).name === 'AbortError') {
        // 用户主动取消
        set(s => ({
          messages: s.messages.map(m =>
            m.loading ? { ...m, loading: false, content: m.content || '（已停止）' } : m
          ),
          isLoading: false,
          abortController: null,
        }))
      } else {
        const msg = e instanceof Error ? e.message : '未知错误'
        set(s => ({
          messages: s.messages.filter(m => !m.loading),
          isLoading: false,
          error: msg,
          abortController: null,
        }))
      }
    }
  },

  stopStream: () => {
    const { abortController } = get()
    if (abortController) {
      abortController.abort()
    }
  },

  newSession: () => {
    const { abortController } = get()
    if (abortController) {
      abortController.abort()
    }
    set({
      sessionId: null, phase: 'init', messages: [],
      worldview: null, outline: null, currentChapter: null,
      error: null, isLoading: false, abortController: null,
    })
  },

  loadSession: async (id) => {
    try {
      const data = await novelApi.session(id) as Record<string, unknown>
      const msgs: ChatMessage[] = ((data.messages as unknown[]) || []).map((m: unknown) => {
        const msg = m as { msg_id: string; role: string; content: string; phase?: string; created_at?: number }
        return {
          id: msg.msg_id, role: msg.role as 'user' | 'assistant',
          content: msg.content, phase: msg.phase, ts: (msg.created_at || 0) * 1000,
        }
      })
      set({
        sessionId: id, phase: (data.phase as string) || 'init',
        messages: msgs,
        worldview: (data.worldview as Record<string, unknown>) || null,
        outline: (data.outline as Record<string, unknown>) || null,
        currentChapter: null, error: null,
      })
    } catch (e) {
      set({ error: '加载会话失败' })
    }
  },

  loadSessions: async () => {
    try {
      const sessions = await novelApi.sessions()
      set({ sessions, sessionsLoaded: true })
    } catch (e) {
      console.error('Failed to load sessions:', e)
    }
  },

  deleteSession: async (id) => {
    try {
      await novelApi.deleteSession(id)
      set(s => ({
        sessions: s.sessions.filter(x => x.session_id !== id),
        ...(s.sessionId === id ? {
          sessionId: null, phase: 'init', messages: [],
          worldview: null, outline: null, currentChapter: null,
        } : {}),
      }))
    } catch (e) {
      const msg = e instanceof Error ? e.message : '删除会话失败'
      set({ error: msg })
    }
  },

  setError: (error) => set({ error }),
}))
