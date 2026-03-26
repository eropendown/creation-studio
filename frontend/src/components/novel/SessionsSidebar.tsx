import { useEffect } from 'react'
import { useNovelStore } from '../../stores/novelStore'
import s from './SessionsSidebar.module.css'

const PHASE_LABELS: Record<string, string> = {
  init: '初始', collecting: '收集创意',
  worldview_review: '世界观阶段', outline_review: '大纲阶段',
  chapter_writing: '创作中', chapter_done: '章节完成', complete: '完结',
}

export default function SessionsSidebar({ onClose }: { onClose: () => void }) {
  const { sessions, sessionsLoaded, loadSessions, loadSession, deleteSession, sessionId } = useNovelStore()

  useEffect(() => {
    if (!sessionsLoaded) loadSessions()
  }, [])

  const handleLoad = async (id: string) => {
    await loadSession(id)
    onClose()
  }

  return (
    <div className={s.root}>
      <div className={s.header}>
        <span className={s.title}>历史会话</span>
        <button className="btn btn-ghost btn-sm" onClick={onClose}>✕</button>
      </div>

      <div className={s.list}>
        {!sessionsLoaded && (
          <div className={s.loading}><span className="spin" /> 加载中…</div>
        )}
        {sessionsLoaded && sessions.length === 0 && (
          <div className={s.empty}>暂无历史会话</div>
        )}
        {sessions.map(ses => (
          <div
            key={ses.session_id}
            className={`${s.item} ${sessionId === ses.session_id ? s.active : ''}`}
          >
            <div className={s.itemMain} onClick={() => handleLoad(ses.session_id)}>
              <div className={s.itemTitle}>
                {ses.title || '未命名小说'}
              </div>
              <div className={s.itemMeta}>
                <span className="badge badge-paper">{PHASE_LABELS[ses.phase] || ses.phase}</span>
                {ses.chapters_done > 0 && (
                  <span className="badge badge-green">{ses.chapters_done}章</span>
                )}
                {ses.total_words > 0 && (
                  <span className={s.words}>{ses.total_words.toLocaleString()}字</span>
                )}
              </div>
              <div className={s.itemDate}>{formatDate(ses.updated_at)}</div>
            </div>
            <button
              className={`btn btn-ghost btn-sm ${s.deleteBtn}`}
              onClick={() => deleteSession(ses.session_id)}
              title="删除"
            >✕</button>
          </div>
        ))}
      </div>
    </div>
  )
}

function formatDate(ts: number) {
  if (!ts) return ''
  const d = new Date(ts * 1000)
  return `${d.getMonth()+1}/${d.getDate()} ${d.getHours()}:${String(d.getMinutes()).padStart(2,'0')}`
}
