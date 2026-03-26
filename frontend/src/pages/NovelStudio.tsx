import React, { useEffect, useRef, useState } from 'react'
import { useNovelStore } from '../stores/novelStore'
import SessionsSidebar from '../components/novel/SessionsSidebar'
import ChatWindow from '../components/novel/ChatWindow'
import PhaseSidebar from '../components/novel/PhaseSidebar'
import InspirationPanel from '../components/novel/InspirationPanel'
import s from './NovelStudio.module.css'

type RightTab = 'phase' | 'inspiration'

export default function NovelStudio() {
  const { messages, sessionId, phase, isLoading, loadSessions, sendMessage, newSession, worldview } = useNovelStore()
  const [input,        setInput]        = useState('')
  const [showSessions, setShowSessions] = useState(false)
  const [rightTab,     setRightTab]     = useState<RightTab>('inspiration')
  const textareaRef = useRef<HTMLTextAreaElement>(null)

  useEffect(() => { loadSessions() }, [])

  // 首次进入：直接等用户输入，不自动发消息
  // 有章节内容后自动切到进度面板
  useEffect(() => {
    if (phase === 'worldview_review' || phase.startsWith('outline') || phase.startsWith('chapter')) {
      setRightTab('phase')
    }
  }, [phase])

  const handleSend = () => {
    const text = input.trim()
    if (!text || isLoading) return
    setInput('')
    sendMessage(text)
    textareaRef.current?.focus()
  }

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    }
  }

  const handleQuickReply = (text: string) => {
    setInput(text)
    setTimeout(() => textareaRef.current?.focus(), 0)
  }

  // 从 worldview 或消息中提取 idea 摘要供灵感面板使用
  const ideaText = (() => {
    if (worldview) {
      const wv = worldview as Record<string, unknown>
      return `${wv.genre || ''} ${wv.core_theme || ''} ${(wv.protagonist as Record<string,unknown>)?.motivation || ''}`.trim()
    }
    // 取用户发出的第一条非空消息
    const firstUser = messages.find(m => m.role === 'user')
    return firstUser?.content || ''
  })()

  const genreText = (() => {
    if (worldview) return String((worldview as Record<string,unknown>).genre || '')
    return ''
  })()

  return (
    <div className={s.root}>
      {/* ── 顶栏 ── */}
      <header className={s.topbar}>
        <div className={s.topbarLeft}>
          <div className={s.topbarTitle}>
            <span className={s.titleIcon}>✍️</span>
            小说创作助手
          </div>
          <span className={s.phaseBadge}>{PHASE_LABELS[phase] || phase}</span>
        </div>
        <div className={s.topbarRight}>
          <button className="btn btn-ghost btn-sm" onClick={() => setShowSessions(v => !v)}>
            📚 历史会话
          </button>
          <button className="btn btn-secondary btn-sm" onClick={newSession}>
            ＋ 新建
          </button>
        </div>
      </header>

      <div className={s.body}>
        {/* 历史会话抽屉 */}
        {showSessions && (
          <SessionsSidebar onClose={() => setShowSessions(false)} />
        )}

        {/* 聊天主区 */}
        <div className={s.chatCol}>
          {messages.length === 0
            ? <WelcomeScreen onSend={handleQuickReply} />
            : <ChatWindow onQuickReply={handleQuickReply} />
          }

          <div className={s.inputArea}>
            <div className={s.inputBox}>
              <textarea
                ref={textareaRef}
                className={`textarea ${s.chatInput}`}
                value={input}
                onChange={e => setInput(e.target.value)}
                onKeyDown={handleKeyDown}
                placeholder={isLoading ? 'AI 正在思考中…' : '直接描述你的故事想法，或输入任何指令…'}
                disabled={isLoading}
                rows={3}
              />
              <button
                className={`btn btn-primary ${s.sendBtn} ${isLoading ? 'btn-loading' : ''}`}
                onClick={handleSend}
                disabled={isLoading || !input.trim()}
              >
                {isLoading ? <span className="spin" /> : '发送'}
              </button>
            </div>
            <QuickReplies phase={phase} onSelect={handleQuickReply} />
          </div>
        </div>

        {/* 右侧面板 */}
        <aside className={s.rightPanel}>
          <div className={s.rightTabs}>
            <button
              className={`${s.rightTab} ${rightTab === 'inspiration' ? s.rightTabActive : ''}`}
              onClick={() => setRightTab('inspiration')}
            >
              💡 灵感
            </button>
            <button
              className={`${s.rightTab} ${rightTab === 'phase' ? s.rightTabActive : ''}`}
              onClick={() => setRightTab('phase')}
            >
              📋 进度
            </button>
          </div>
          <div className={s.rightContent}>
            {rightTab === 'inspiration'
              ? <InspirationPanel idea={ideaText} genre={genreText} />
              : <PhaseSidebar />
            }
          </div>
        </aside>
      </div>
    </div>
  )
}

/* ── 欢迎屏（无消息时）─────────────────────────── */
const STARTER_IDEAS = [
  '一个失忆的特工发现自己的过去比想象中更黑暗…',
  '末日后的城市里，AI开始学会了说谎…',
  '两个相互竞争的家族，因为一场意外的婚约被迫联手…',
  '一个普通程序员，发现自己设计的算法开始预测未来…',
]

function WelcomeScreen({ onSend }: { onSend: (text: string) => void }) {
  return (
    <div className={s.welcome}>
      <div className={s.welcomeIcon}>✍️</div>
      <h2 className={s.welcomeTitle}>开始你的创作</h2>
      <p className={s.welcomeDesc}>
        直接描述你的故事想法，哪怕只是一个片段、一个人物、一个场景。<br />
        内容越具体，AI 理解越准确，可直接跳过繁琐的问答流程。
      </p>
      <div className={s.starterList}>
        <p className={s.starterLabel}>或者从这些 idea 开始：</p>
        {STARTER_IDEAS.map((idea, i) => (
          <button
            key={i}
            className={s.starterBtn}
            onClick={() => onSend(idea)}
          >
            {idea}
          </button>
        ))}
      </div>
    </div>
  )
}

/* ── 快捷回复（精简版，只在关键阶段出现）─────── */
const QUICK_MAP: Record<string, string[]> = {
  worldview_review: ['确认，进入规划', '需要修改主角', '需要调整世界观'],
  outline_review:   ['开始写作', '调整大纲'],
  chapter_writing:  ['继续', '重写这个场景'],
  chapter_done:     ['下一章'],
}

function QuickReplies({ phase, onSelect }: { phase: string; onSelect: (t: string) => void }) {
  const replies = QUICK_MAP[phase] || []
  if (!replies.length) return null
  return (
    <div className={s.quickReplies}>
      {replies.map(r => (
        <button key={r} className={`btn btn-ghost btn-sm ${s.quickBtn}`} onClick={() => onSelect(r)}>
          {r}
        </button>
      ))}
    </div>
  )
}

const PHASE_LABELS: Record<string, string> = {
  init: '待输入', collecting: '完善中',
  worldview_building: '构建世界观', worldview_review: '确认世界观',
  worldview_confirmed: '世界观✓', outline_planning: '规划情节',
  outline_review: '确认大纲', outline_confirmed: '大纲✓',
  chapter_preparing: '分解场景', chapter_writing: '创作中',
  chapter_done: '章节完成', complete: '完结',
}