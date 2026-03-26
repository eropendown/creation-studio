import React, { useState } from 'react'
import { useNovelStore } from '../../stores/novelStore'
import { novelApi } from '../../api/novel'
import s from './PhaseSidebar.module.css'

const TABS = [
  { id: 'worldview', label: '世界观', icon: '🌍' },
  { id: 'outline',   label: '大纲',   icon: '📋' },
  { id: 'chapter',   label: '章节',   icon: '📄' },
]

export default function PhaseSidebar() {
  const { worldview, outline, currentChapter, sessionId, phase } = useNovelStore()
  const [activeTab, setActiveTab] = useState('worldview')

  const hasWorldview = !!worldview
  const hasOutline   = !!outline
  const hasChapter   = !!currentChapter

  // 根据阶段自动切换活跃 tab
  const effectiveTab = (() => {
    if (phase.startsWith('chapter') && hasChapter) return 'chapter'
    if ((phase.startsWith('outline') || phase.startsWith('chapter')) && hasOutline) return 'outline'
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

      {/* 导出按钮 */}
      {sessionId && (phase === 'chapter_done' || phase === 'complete') && (
        <div className={s.exportArea}>
          <a
            href={novelApi.exportUrl(sessionId)}
            className="btn btn-secondary btn-full btn-sm"
            download
          >
            📥 导出全文 Markdown
          </a>
        </div>
      )}
    </aside>
  )
}

/* ── 世界观面板 ──────────────────────────────────── */
function WorldviewPanel({ data }: { data: Record<string, unknown> }) {
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
function OutlinePanel({ data }: { data: Record<string, unknown> }) {
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
function ChapterPanel({ data }: { data: Record<string, unknown> }) {
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
