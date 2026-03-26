import { useMangaStore } from '../../stores/mangaStore'
import s from './HistoryPanel.module.css'

interface Props { onSelect: () => void }

export default function HistoryPanel({ onSelect }: Props) {
  const { outlines, outlinesLoaded, deleteOutline, setActiveOutline, activeOutlineId } = useMangaStore()

  const handleSelect = (id: string) => {
    setActiveOutline(id)
    onSelect()
  }

  return (
    <div className={s.root}>
      <div className="sec-head">
        <span>📚 历史大纲</span>
        <span className="badge badge-paper">{outlines.length} 条</span>
      </div>

      <div className={s.body}>
        {!outlinesLoaded && (
          <div className={s.loading}><span className="spin" /> 加载中…</div>
        )}

        {outlinesLoaded && outlines.length === 0 && (
          <div className={s.empty}>
            <div className={s.emptyIcon}>📭</div>
            <p>暂无历史大纲</p>
            <p className={s.emptyHint}>在「创建大纲」页面创建您的第一个项目</p>
          </div>
        )}

        <div className={s.grid}>
          {outlines.map(o => (
            <div
              key={o.outline_id}
              className={`${s.card} ${activeOutlineId === o.outline_id ? s.cardActive : ''}`}
            >
              <div className={s.cardMain} onClick={() => handleSelect(o.outline_id)}>
                <div className={s.cardHeader}>
                  <span className={s.cardTitle}>{o.title || '未命名'}</span>
                  <span className={`badge ${STATUS_BADGE[o.outline_status] || 'badge-paper'}`}>
                    {STATUS_LABEL[o.outline_status] || o.outline_status}
                  </span>
                </div>

                <div className={s.cardMeta}>
                  <span className="badge badge-paper">{o.genre}</span>
                  <span className="badge badge-paper">{o.style}</span>
                  {o.source_type === 'novel' && (
                    <span className="badge badge-blue">📖 小说导入</span>
                  )}
                </div>

                <div className={s.cardStats}>
                  <span className={s.stat}>
                    <span className={s.statIcon}>📽️</span>
                    {o.total_scenes} 分镜
                  </span>
                  <span className={s.stat}>
                    <span className={s.statIcon}>🖼️</span>
                    {o.images_done}/{o.total_scenes} 图片
                  </span>
                  <span className={s.stat}>
                    <span className={s.statIcon}>⏱️</span>
                    ≈{isNaN(o.estimated_duration) ? 0 : Math.round(o.estimated_duration)}秒
                  </span>
                </div>

                <div className={s.cardDate}>{formatDate(o.created_at)}</div>
              </div>

              <div className={s.cardActions}>
                <button
                  className="btn btn-secondary btn-sm"
                  onClick={() => handleSelect(o.outline_id)}
                >查看</button>
                <button
                  className="btn btn-ghost btn-sm"
                  onClick={() => deleteOutline(o.outline_id)}
                >删除</button>
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}

const STATUS_LABEL: Record<string, string> = {
  draft: '草稿', generating: '生成中', done: '完成', error: '出错'
}
const STATUS_BADGE: Record<string, string> = {
  draft: 'badge-paper', generating: 'badge-gold', done: 'badge-green', error: 'badge-red'
}

function formatDate(ts: number) {
  if (!ts || isNaN(ts)) return ''
  const d = new Date(ts * 1000)
  if (isNaN(d.getTime())) return ''
  return `${d.getFullYear()}/${d.getMonth()+1}/${d.getDate()}`
}
