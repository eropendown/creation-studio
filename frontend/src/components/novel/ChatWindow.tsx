import React, { useEffect, useRef, useState, useCallback } from 'react'
import { useNovelStore, ChatMessage } from '../../stores/novelStore'
import s from './ChatWindow.module.css'

interface Props {
  onQuickReply: (text: string) => void
}

export default function ChatWindow({ onQuickReply }: Props) {
  const { messages, isLoading, error, stopStream, sendMessage } = useNovelStore()
  const bottomRef = useRef<HTMLDivElement>(null)
  const messagesRef = useRef<HTMLDivElement>(null)
  const [autoScroll, setAutoScroll] = useState(true)
  const [showJumpBtn, setShowJumpBtn] = useState(false)

  // 检测用户是否手动滚动
  const handleScroll = useCallback(() => {
    const container = messagesRef.current
    if (!container) return

    const { scrollTop, scrollHeight, clientHeight } = container
    const isNearBottom = scrollHeight - scrollTop - clientHeight < 150
    setAutoScroll(isNearBottom)
    setShowJumpBtn(!isNearBottom && messages.length > 2)
  }, [messages.length])

  // 自动滚动到底部
  useEffect(() => {
    if (autoScroll) {
      bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
    }
  }, [messages.length, messages[messages.length - 1]?.content, autoScroll])

  // 重试最后一条消息
  const handleRetry = useCallback(() => {
    // 找到最后一条用户消息并重新发送
    const lastUserMsg = [...messages].reverse().find(m => m.role === 'user')
    if (lastUserMsg) {
      sendMessage(lastUserMsg.content)
    }
  }, [messages, sendMessage])

  return (
    <div className={s.root}>
      <div className={s.messages} ref={messagesRef} onScroll={handleScroll}>
        {messages.map((msg, i) => (
          <MessageBubble
            key={msg.id}
            msg={msg}
            index={i}
            isLast={i === messages.length - 1}
            onRetry={handleRetry}
          />
        ))}

        {/* 流式输出时显示停止按钮 */}
        {isLoading && (
          <div className={s.streamingBar}>
            <div className={s.streamingIndicator}>
              <span className={s.streamingDot} />
              <span>正在生成...</span>
            </div>
            <button
              className={s.stopBtn}
              onClick={stopStream}
              title="停止生成"
            >
              ⏹ 停止
            </button>
          </div>
        )}

        {error && (
          <div className={s.errorMsg}>
            <span>⚠️ {error}</span>
            <button className={s.retryBtn} onClick={handleRetry}>
              重试
            </button>
          </div>
        )}

        {/* 跳转到底部按钮 */}
        {showJumpBtn && (
          <button
            className={s.jumpBtn}
            onClick={() => {
              bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
              setAutoScroll(true)
            }}
          >
            ↓ 回到底部
          </button>
        )}

        <div ref={bottomRef} />
      </div>
    </div>
  )
}

function MessageBubble({
  msg,
  index,
  isLast,
  onRetry
}: {
  msg: ChatMessage
  index: number
  isLast: boolean
  onRetry: () => void
}) {
  const isUser = msg.role === 'user'
  const [copied, setCopied] = useState(false)

  const handleCopy = useCallback(() => {
    navigator.clipboard.writeText(msg.content).then(() => {
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    }).catch(() => {
      // 降级方案
      const textarea = document.createElement('textarea')
      textarea.value = msg.content
      document.body.appendChild(textarea)
      textarea.select()
      document.execCommand('copy')
      document.body.removeChild(textarea)
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    })
  }, [msg.content])

  return (
    <div
      className={`${s.bubble} ${isUser ? s.user : s.assistant} anim-fade-up`}
      style={{ animationDelay: `${Math.min(index * 0.03, 0.2)}s` }}
      role="article"
      aria-label={`${isUser ? '用户' : '助手'}消息`}
    >
      {!isUser && <div className={s.avatar}>✍</div>}

      <div className={s.bubbleInner}>
        {!isUser && msg.phase && (
          <div className={s.phaseTag}>{PHASE_LABELS[msg.phase] || msg.phase}</div>
        )}
        <div
          className={`${s.bubbleContent} ${isUser ? s.userContent : s.assistantContent}`}
          aria-live={isLast && !isUser ? "polite" : undefined}
          aria-atomic="false"
        >
          {isUser
            ? <p>{msg.content}</p>
            : <MarkdownContent content={msg.content} isStreaming={msg.loading && isLast} />
          }
        </div>

        {/* 消息操作栏 */}
        <div className={s.msgActions}>
          <div className={s.timestamp}>{formatTime(msg.ts)}</div>
          {!isUser && !msg.loading && msg.content && (
            <div className={s.actionBtns}>
              <button
                className={s.actionBtn}
                onClick={handleCopy}
                title="复制内容"
              >
                {copied ? '✓' : '📋'}
              </button>
              {isLast && (
                <button
                  className={s.actionBtn}
                  onClick={onRetry}
                  title="重新生成"
                >
                  🔄
                </button>
              )}
            </div>
          )}
        </div>
      </div>

      {isUser && <div className={s.avatarUser}>你</div>}
    </div>
  )
}

/* 简易 Markdown 渲染（不引入额外依赖） */
function MarkdownContent({ content, isStreaming }: { content: string; isStreaming?: boolean }) {
  if (!content) {
    if (isStreaming) {
      return <span className={s.cursor}>▋</span>
    }
    return null
  }

  const lines = content.split('\n')
  const elements: React.ReactNode[] = []

  lines.forEach((line, i) => {
    if (line.startsWith('### ')) {
      elements.push(<h3 key={i}>{parseInline(line.slice(4))}</h3>)
    } else if (line.startsWith('## ')) {
      elements.push(<h2 key={i}>{parseInline(line.slice(3))}</h2>)
    } else if (line.startsWith('# ')) {
      elements.push(<h1 key={i}>{parseInline(line.slice(2))}</h1>)
    } else if (line.startsWith('> ')) {
      elements.push(<blockquote key={i}>{parseInline(line.slice(2))}</blockquote>)
    } else if (line.startsWith('---')) {
      elements.push(<hr key={i} />)
    } else if (line.trim() === '') {
      elements.push(<br key={i} />)
    } else if (line.startsWith('- ')) {
      elements.push(<li key={i}>{parseInline(line.slice(2))}</li>)
    } else {
      elements.push(<p key={i}>{parseInline(line)}</p>)
    }
  })

  if (isStreaming) {
    elements.push(<span key="cursor" className={s.cursor}>▋</span>)
  }

  return <div className="md">{elements}</div>
}

function parseInline(text: string): React.ReactNode {
  const parts = text.split(/(\*\*[^*]+\*\*|\*[^*]+\*|`[^`]+`)/g)
  return parts.map((part, i) => {
    if (part.startsWith('**') && part.endsWith('**')) {
      return <strong key={i}>{part.slice(2, -2)}</strong>
    }
    if (part.startsWith('*') && part.endsWith('*')) {
      return <em key={i}>{part.slice(1, -1)}</em>
    }
    if (part.startsWith('`') && part.endsWith('`')) {
      return <code key={i}>{part.slice(1, -1)}</code>
    }
    return part
  })
}

function formatTime(ts: number) {
  if (!ts) return ''
  const d = new Date(ts)
  return `${d.getHours().toString().padStart(2,'0')}:${d.getMinutes().toString().padStart(2,'0')}`
}

const PHASE_LABELS: Record<string, string> = {
  init: '初始化',
  collecting: '收集创意',
  worldview_building: '构建世界观',
  worldview_review: '世界观确认',
  outline_planning: '规划情节',
  outline_review: '大纲确认',
  chapter_preparing: '章节准备',
  chapter_writing: '创作中',
  chapter_done: '章节完成',
  complete: '全部完成',
}
