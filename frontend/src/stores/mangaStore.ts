import { create } from 'zustand'
import { mangaApi, OutlineSummary, JobStatus, SystemConfig } from '../api/manga'

interface MangaState {
  outlines: OutlineSummary[]
  outlinesLoaded: boolean
  activeOutlineId: string | null
  activeOutline: Record<string, unknown> | null
  // 生成任务
  jobs: Record<string, JobStatus>
  activeJobId: string | null
  // 配置
  config: SystemConfig | null
  configLoaded: boolean
  // UI
  isGenerating: boolean
  error: string | null
}

interface MangaActions {
  loadOutlines: () => Promise<void>
  loadOutline: (id: string) => Promise<void>
  deleteOutline: (id: string) => Promise<void>
  startGenerate: (outlineId: string) => Promise<string>
  updateJobStatus: (job: JobStatus) => void
  loadConfig: () => Promise<void>
  saveConfig: (cfg: SystemConfig) => Promise<void>
  setActiveOutline: (id: string | null) => void
  setError: (e: string | null) => void
}

export const useMangaStore = create<MangaState & MangaActions>((set, get) => ({
  outlines: [],
  outlinesLoaded: false,
  activeOutlineId: null,
  activeOutline: null,
  jobs: {},
  activeJobId: null,
  config: null,
  configLoaded: false,
  isGenerating: false,
  error: null,

  loadOutlines: async () => {
    try {
      const outlines = await mangaApi.outlines()
      set({ outlines, outlinesLoaded: true })
    } catch (e) {
      console.error('Failed to load outlines:', e)
    }
  },

  loadOutline: async (id) => {
    try {
      const outline = await mangaApi.outline(id)
      set({ activeOutline: outline, activeOutlineId: id })
    } catch (e) {
      set({ error: '加载大纲失败' })
    }
  },

  deleteOutline: async (id) => {
    try {
      await mangaApi.deleteOutline(id)
      set(s => ({
        outlines: s.outlines.filter(o => o.outline_id !== id),
        ...(s.activeOutlineId === id ? { activeOutlineId: null, activeOutline: null } : {})
      }))
    } catch (e) {
      const msg = e instanceof Error ? e.message : '删除大纲失败'
      set({ error: msg })
    }
  },

  startGenerate: async (outlineId) => {
    set({ isGenerating: true, error: null })
    try {
      const resp = await mangaApi.generate({ outline_id: outlineId })
      set({ activeJobId: resp.job_id, isGenerating: false })
      return resp.job_id
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : '生成失败'
      set({ isGenerating: false, error: msg })
      return ''
    }
  },

  updateJobStatus: (job) => set(s => ({
    jobs: { ...s.jobs, [job.job_id]: job }
  })),

  loadConfig: async () => {
    try {
      const config = await mangaApi.getConfig()
      set({ config, configLoaded: true })
    } catch (e) {
      console.error('Failed to load config:', e)
    }
  },

  saveConfig: async (cfg) => {
    try {
      const saved = await mangaApi.saveConfig(cfg)
      set({ config: saved })
    } catch (e) {
      set({ error: '保存配置失败' })
    }
  },

  setActiveOutline: (id) => {
    set({ activeOutlineId: id })
    if (id) get().loadOutline(id)
  },

  setError: (error) => set({ error }),
}))
