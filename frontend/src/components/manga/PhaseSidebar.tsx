import React, { useState, useEffect, useRef } from 'react'
import { useNovelStore } from '../../stores/novelStore'
import { novelApi } from '../../api/novel'
import { mangaApi } from '../../api/manga'
import { useNavigate } from 'react-router-dom'
import s from './PhaseSidebar.module.css'

const TABS = [
  { id: 'worldview', label: '世界观', icon: '🌍' },
  { id: 'outline',   label: '大纲',   icon: '📋' },
  { id: 'chapter',   label: '章节',   icon: '📄' },
]

export default function PhaseSidebar() {
  const { worldview, outline, currentChapter, sessionId, phase } = useNovelStore()
  const [activeTab, setActiveTab]       = useState('worldview')
  const [showImport, setShowImport]     = useState(false)

  const hasWorldview = !!worldview
  const hasOutline   = !!outline
  const hasChapter   = !!currentChapter
  const hasContent   = phase === 'chapter_done' || phase === 'complete' ||
                       (phase === 'chapter_writing' && !!currentChapter)

  const effectiveTab = (() => {
    if (typeof phase === 'string' && phase.startsWith('chapter') && hasChapter) return 'chapter'
    if (typeof phase === 'string' && (phase.startsWith('outline') || phase.startsWith('chapter')) && hasOutline) return 'outline'
    return activeTab
  })()

  return (
    <aside className={s.root}>
      {/* tab 栏 */}
      <div className={s.tabs}>
        {TABS.map(t => (
          <button
            key={t.id}
            className={`${s.tab} ${effectiveTab === t.id ? s.tabActive : ''}`}
            onClick={() => setActiveTab(t.id)}
          >
            <span>{t.icon}</span>
            <span>{t.label}</span>
            {t.id === 'worldview' && hasWorldview && <span className={s.dot} />}
            {t.id === 'outline'   && hasOutline   && <span className={s.dot} />}
            {t.id === 'chapter'   && hasChapter   && <span className={s.dot} />}
          </button>
        ))}
      </div>

      {/* 内容区 */}
      <div className={s.content}>
        {effectiveTab === 'worldview' && (
          hasWorldview
            ? <WorldviewPanel data={worldview} />
            : <EmptyPanel icon="🌍" text="世界观将在阶段一完成后显示" />
        )}
        {effectiveTab === 'outline' && (
          hasOutline
            ? <OutlinePanel data={outline} />
            : <EmptyPanel icon="📋" text="大纲将在阶段二完成后显示" />
        )}
        {effectiveTab === 'chapter' && (
          hasChapter
            ? <ChapterPanel data={currentChapter} />
            : <EmptyPanel icon="📄" text="章节进度将在创作开始后显示" />
        )}
      </div>

      {/* 底部操作区 */}
      {sessionId && hasContent && (
        <div className={s.exportArea}>
          <a
            href={novelApi.exportUrl(sessionId)}
            className="btn btn-secondary btn-full btn-sm"
            download
          >
            📥 导出全文 Markdown
          </a>
          <button
            className="btn btn-primary btn-full btn-sm"
            onClick={() => setShowImport(true)}
          >
            🎬 导入漫剧工作台
          </button>
        </div>
      )}

      {/* 导入漫剧弹窗 */}
      {showImport && sessionId && (
        <ImportToMangaModal
          sessionId={sessionId}
          title={String((worldview as Record<string,unknown>)?.title || '小说')}
          onClose={() => setShowImport(false)}
        />
      )}
    </aside>
  )
}

/* ── 世界观面板 ──────────────────────────────────── */
function WorldviewPanel({ data }: { data: any }) {
  const ws  = (data.world_setting || {}) as Record<string, string>
  const pro = (data.protagonist   || {}) as Record<string, string>
  const chars = (data.supporting_characters || []) as Record<string, string>[]

  return (
    <div className={s.panel}>
      <div className={s.panelTitle}>
        《{String(data.title || '未命名')}》
        <span className={s.panelGenre}>{String(data.genre || '')}</span>
      </div>
      <p className={s.panelTheme}>{String(data.core_theme || '')}</p>

      {ws.era && (
        <Section title="世界背景">
          {ws.era && <Row k="时代" v={ws.era} />}
          {ws.geography && <Row k="地理" v={ws.geography} />}
          {ws.special_rules && <Row k="特殊设定" v={ws.special_rules} />}
          {ws.atmosphere && <Row k="基调" v={ws.atmosphere} />}
        </Section>
      )}

      {pro.name && (
        <Section title={`主角 · ${pro.name}`}>
          {pro.background  && <Row k="背景" v={pro.background} />}
          {pro.personality && <Row k="性格" v={pro.personality} />}
          {pro.ability     && <Row k="能力" v={pro.ability} />}
          {pro.motivation  && <Row k="动机" v={pro.motivation} />}
        </Section>
      )}

      {chars.length > 0 && (
        <Section title="配角">
          {chars.slice(0, 4).map((c, i) => (
            <div key={i} className={s.charRow}>
              <strong>{c.name}</strong>
              <span className={s.charRole}>{c.role}</span>
              <p>{c.description}</p>
            </div>
          ))}
        </Section>
      )}

      {data.core_conflict && (
        <Section title="核心矛盾">
          <p className={s.conflictText}>{String(data.core_conflict)}</p>
        </Section>
      )}

      {data.story_hook && (
        <Section title="开篇钩子">
          <p className={s.hookText}>「{String(data.story_hook)}」</p>
        </Section>
      )}
    </div>
  )
}

/* ── 大纲面板 ────────────────────────────────────── */
function OutlinePanel({ data }: { data: any }) {
  const chapters = (data.chapters || []) as Record<string, unknown>[]

  return (
    <div className={s.panel}>
      {data.hook && (
        <div className={s.outlineHook}>
          <span className={s.hookLabel}>开篇</span>
          {String(data.hook)}
        </div>
      )}

      <div className={s.chapterList}>
        {chapters.map((ch, i) => {
          const isDone = ch.status === 'done'
          return (
            <div key={i} className={`${s.chapterItem} ${isDone ? s.chapterDone : ''}`}>
              <div className={s.chapterHead}>
                <span className={s.chNum}>第{String(ch.chapter_num)}章</span>
                <span className={s.chTitle}>{String(ch.title)}</span>
                {isDone && <span className="badge badge-green">✓</span>}
              </div>
              <p className={s.chSummary}>{String(ch.summary || '').slice(0, 60)}…</p>
              {ch.emotional_arc && (
                <div className={s.chArc}>{String(ch.emotional_arc)}</div>
              )}
            </div>
          )
        })}
      </div>
    </div>
  )
}

/* ── 章节面板 ────────────────────────────────────── */
function ChapterPanel({ data }: { data: any }) {
  const scenes = (data.scenes || []) as Record<string, unknown>[]
  const done   = scenes.filter(s => s.status === 'done').length

  return (
    <div className={s.panel}>
      <div className={s.chapterProgress}>
        <div className={s.chapterProgressTop}>
          <span>第{String(data.chapter_num)}章 · {String(data.title)}</span>
          <span className={s.progressNum}>{done}/{scenes.length}</span>
        </div>
        <div className="progress-bar" style={{ marginTop: 8 }}>
          <div className="progress-fill" style={{ width: `${scenes.length ? done/scenes.length*100 : 0}%` }} />
        </div>
      </div>

      <div className={s.sceneList}>
        {scenes.map((sc, i) => {
          const status = String(sc.status || 'pending')
          return (
            <div key={i} className={`${s.sceneItem} ${s['scene_' + status]}`}>
              <div className={s.sceneHead}>
                <span className={s.sceneNum}>{String(sc.scene_id)}</span>
                <span className={s.sceneTitle}>{String(sc.title)}</span>
                <SceneStatus status={status} />
              </div>
              {sc.content && (
                <p className={s.scenePreview}>{String(sc.content).slice(0, 50)}…</p>
              )}
            </div>
          )
        })}
      </div>

      {(data.word_count as number) > 0 && (
        <div className={s.wordCount}>
          本章约 <strong>{(data.word_count as number).toLocaleString()}</strong> 字
        </div>
      )}
    </div>
  )
}

function SceneStatus({ status }: { status: string }) {
  const map: Record<string, { cls: string; label: string }> = {
    pending: { cls: 'badge-paper', label: '待写' },
    writing: { cls: 'badge-gold',  label: '写作中' },
    done:    { cls: 'badge-green', label: '完成' },
    skipped: { cls: 'badge-paper', label: '跳过' },
  }
  const { cls, label } = map[status] || { cls: 'badge-paper', label: status }
  return <span className={`badge ${cls}`}>{label}</span>
}

/* ── 通用子组件 ──────────────────────────────────── */
function EmptyPanel({ icon, text }: { icon: string; text: string }) {
  return (
    <div className={s.empty}>
      <div className={s.emptyIcon}>{icon}</div>
      <p>{text}</p>
    </div>
  )
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className={s.section}>
      <div className={s.sectionTitle}>{title}</div>
      {children}
    </div>
  )
}

function Row({ k, v }: { k: string; v: string }) {
  return (
    <div className={s.row}>
      <span className={s.rowKey}>{k}</span>
      <span className={s.rowVal}>{v}</span>
    </div>
  )
}

/* ── 导入漫剧弹窗 ──────────────────────────────────── */
const MANGA_STYLES = ['古风仙侠','都市言情','赛博朋克','热血漫画','悬疑惊悚','历史战争']

function ImportToMangaModal({
  sessionId, title, onClose
}: {
  sessionId: string
  title: string
  onClose: () => void
}) {
  const navigate   = useNavigate()
  const [style, setStyle]           = useState('古风仙侠')
  const [sceneCount, setSceneCount] = useState(10)
  const [focusRange, setFocusRange] = useState('')
  const [loading, setLoading]       = useState(false)
  const [msg, setMsg]               = useState('')
  const [error, setError]           = useState('')
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  useEffect(() => { return () => { if (timerRef.current) clearTimeout(timerRef.current) } }, [])

  const handleImport = async () => {
    setLoading(true); setError(''); setMsg('正在分析小说内容…')
    try {
      const res = await mangaApi.novelToManga(sessionId, { style, scene_count: sceneCount, focus_range: focusRange })
      setMsg(res.message)
      timerRef.current = setTimeout(() => {
        onClose()
        navigate('/manga')
      }, 1500)
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : '导入失败')
      setLoading(false)
    }
  }

  return (
    <div className={s.modalOverlay} onClick={e => e.target === e.currentTarget && onClose()}>
      <div className={s.modal}>
        <div className={s.modalHead}>
          <span className={s.modalTitle}>🎬 导入漫剧工作台</span>
          <button className="btn btn-ghost btn-sm" onClick={onClose}>✕</button>
        </div>
        <div className={s.modalBody}>
          <p className={s.modalDesc}>
            将《{title}》的创作内容自动转化为漫剧分镜大纲。
          </p>

          <div className="form-group">
            <label className="form-label">漫剧画风</label>
            <div className={s.styleGrid}>
              {MANGA_STYLES.map(st => (
                <button
                  key={st}
                  className={`${s.styleBtn} ${style === st ? s.styleBtnActive : ''}`}
                  onClick={() => setStyle(st)}
                >{st}</button>
              ))}
            </div>
          </div>

          <div className="form-group">
            <label className="form-label">分镜数量 <strong>{sceneCount}</strong></label>
            <input
              type="range" min={5} max={20} value={sceneCount}
              onChange={e => setSceneCount(Number(e.target.value))}
              className={s.range}
            />
          </div>

          <div className="form-group">
            <label className="form-label">重点章节（可选）</label>
            <input
              type="text"
              className="input"
              value={focusRange}
              onChange={e => setFocusRange(e.target.value)}
              placeholder="如：第1-3章，留空则全部章节"
            />
          </div>

          {msg   && <div className={s.importOk}>{msg}</div>}
          {error && <div className={s.importErr}>⚠ {error}</div>}
        </div>
        <div className={s.modalFoot}>
          <button className="btn btn-ghost btn-sm" onClick={onClose} disabled={loading}>取消</button>
          <button
            className={`btn btn-primary ${loading ? 'btn-loading' : ''}`}
            onClick={handleImport}
            disabled={loading}
          >
            {loading ? <><span className="spin" /> 导入中…</> : '🎬 确认导入'}
          </button>
        </div>
      </div>
    </div>
  )
}
