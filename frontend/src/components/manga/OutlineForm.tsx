import { useState } from 'react'
import { mangaApi } from '../../api/manga'
import { useMangaStore } from '../../stores/mangaStore'
import s from './OutlineForm.module.css'

const GENRES  = ['古风仙侠','都市言情','赛博朋克','热血漫画','悬疑惊悚','历史战争','校园青春']
const STYLES  = ['古风仙侠','赛博朋克','都市言情','热血漫画','悬疑惊悚']
const SOURCES = ['synopsis', 'novel'] as const
type Source = typeof SOURCES[number]

interface Props { onCreated: () => void }

export default function OutlineForm({ onCreated }: Props) {
  const { loadOutlines, setActiveOutline, setError } = useMangaStore()

  const [source, setSource] = useState<Source>('synopsis')
  const [genre,  setGenre]  = useState(GENRES[0])
  const [style,  setStyle]  = useState(STYLES[0])
  const [sceneCount, setSceneCount] = useState(8)
  const [synopsis, setSynopsis] = useState('')
  const [novelText, setNovelText] = useState('')
  const [loading, setLoading] = useState(false)
  const [log, setLog] = useState<string[]>([])

  const addLog = (msg: string) => setLog(p => [...p, msg])

  const handleSubmit = async () => {
    const content = source === 'synopsis' ? synopsis : novelText
    if (!content.trim() || loading) return

    setLoading(true)
    setLog([])
    addLog('开始生成大纲…')

    try {
      let res
      if (source === 'synopsis') {
        addLog('分析故事设定…')
        res = await mangaApi.createOutline({ genre, synopsis, style, scene_count: sceneCount })
      } else {
        addLog('解析小说文本…')
        const r = await fetch('/api/outline/novel', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ novel_text: novelText, style, scene_count: sceneCount }),
        })
        if (!r.ok) {
          const err = await r.json().catch(() => ({}))
          throw new Error(err.detail || `HTTP ${r.status}`)
        }
        res = await r.json()
      }

      addLog(`✓ 《${res.outline.title}》生成完成`)
      await loadOutlines()
      setActiveOutline(res.outline.outline_id)
      onCreated()
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : '生成失败'
      addLog(`✗ ${msg}`)
      setError(msg)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className={s.root}>
      <div className="sec-head">
        <span>📝 创建大纲</span>
      </div>

      <div className={s.body}>
        {/* 来源切换 */}
        <div className={s.sourceBar}>
          <button
            className={`${s.sourceBtn} ${source === 'synopsis' ? s.sourceBtnActive : ''}`}
            onClick={() => setSource('synopsis')}
          >简介生成</button>
          <button
            className={`${s.sourceBtn} ${source === 'novel' ? s.sourceBtnActive : ''}`}
            onClick={() => setSource('novel')}
          >小说导入</button>
        </div>

        {source === 'synopsis' && (
          <div className="form-group">
            <label className="form-label">故事类型</label>
            <div className={s.genreGrid}>
              {GENRES.map(g => (
                <button
                  key={g}
                  className={`${s.genreBtn} ${genre === g ? s.genreBtnActive : ''}`}
                  onClick={() => setGenre(g)}
                >{g}</button>
              ))}
            </div>
          </div>
        )}

        <div className="form-group">
          <label className="form-label">{source === 'synopsis' ? '故事简介' : '小说原文'}</label>
          <textarea
            className={`textarea ${source === 'novel' ? 'novel' : ''}`}
            value={source === 'synopsis' ? synopsis : novelText}
            onChange={e => source === 'synopsis' ? setSynopsis(e.target.value) : setNovelText(e.target.value)}
            placeholder={source === 'synopsis'
              ? '描述故事背景、主角与核心冲突，100字以上效果更佳…'
              : '粘贴小说全文或章节片段，AI 将自动分析并生成漫剧大纲…'
            }
            style={{ minHeight: source === 'novel' ? 180 : 110 }}
          />
        </div>

        <div className={s.twoCol}>
          <div className="form-group">
            <label className="form-label">画风</label>
            <select className="select" value={style} onChange={e => setStyle(e.target.value)}>
              {STYLES.map(s => <option key={s} value={s}>{s}</option>)}
            </select>
          </div>
          <div className="form-group">
            <label className="form-label">分镜数 <strong>{sceneCount}</strong></label>
            <input
              type="range" min={3} max={20} value={sceneCount}
              onChange={e => setSceneCount(Number(e.target.value))}
              className={s.range}
            />
          </div>
        </div>

        <button
          className={`btn btn-primary btn-full ${loading ? 'btn-loading' : ''}`}
          onClick={handleSubmit}
          disabled={loading || !(source === 'synopsis' ? synopsis : novelText).trim()}
        >
          {loading ? <><span className="spin" /> 生成中…</> : '🎬 生成大纲'}
        </button>

        {/* 生成日志 */}
        {log.length > 0 && (
          <div className={s.log}>
            {log.map((l, i) => (
              <div key={i} className={`${s.logLine} ${l.startsWith('✓') ? s.logOk : l.startsWith('✗') ? s.logErr : ''}`}>
                <span className={s.logDot} />
                {l}
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
