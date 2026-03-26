import React, { useState, useEffect, useRef } from 'react'
import s from './InspirationPanel.module.css'

interface InspirationCard {
  title:        string
  type:         string
  genre:        string
  why_relevant: string
  highlights:   string[]
  techniques:   string[]
  caution?:     string
}

interface InspirationResult {
  query:        string
  cards:        InspirationCard[]
  writing_tips: string[]
  source:       string
}

const TYPE_LABEL: Record<string, string> = {
  novel: '📚 小说', film: '🎬 电影', series: '📺 剧集'
}

interface Props {
  idea:  string
  genre?: string   // optional hint, merged into idea for the API call
}

export default function InspirationPanel({ idea, genre }: Props) {
  // Merge genre hint into idea for richer search context
  const fullIdea = genre && !idea.includes(genre) ? `${genre} ${idea}`.trim() : idea
  const [result, setResult]     = useState<InspirationResult | null>(null)
  const [loading, setLoading]   = useState(false)
  const [error, setError]       = useState('')
  const [expanded, setExpanded] = useState<number | null>(0)
  const lastIdea                = useRef('')
  const timerRef                = useRef<ReturnType<typeof setTimeout> | null>(null)

  useEffect(() => {
    const checkIdea = fullIdea
    if (!checkIdea || checkIdea.length < 15 || checkIdea === lastIdea.current) return
    if (timerRef.current) clearTimeout(timerRef.current)
    timerRef.current = setTimeout(() => {
      lastIdea.current = checkIdea
      fetchInspiration(checkIdea)
    }, 1500)
    return () => { if (timerRef.current) clearTimeout(timerRef.current) }
  }, [fullIdea])

  const fetchInspiration = async (text: string) => {
    setLoading(true); setError('')
    try {
      const res = await fetch('/api/novel/inspiration', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ idea: text }),
      })
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      setResult(await res.json())
      setExpanded(0)
    } catch (e) {
      setError('灵感引擎暂时不可用')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className={s.root}>
      <div className={s.header}>
        <div className={s.headerLeft}>
          <span className={s.headerIcon}>✦</span>
          <span className={s.headerTitle}>创作参考</span>
          {result?.source === 'cache' && <span className={s.cacheTag}>缓存</span>}
        </div>
        <button
          className={s.refreshBtn}
          onClick={() => fullIdea && fetchInspiration(fullIdea)}
          disabled={loading || !idea}
          title="重新分析"
        >{loading ? '…' : '↻'}</button>
      </div>

      <div className={s.body}>
        {!loading && !result && !error && (
          <div className={s.empty}>
            <div className={s.emptyIcon}>✦</div>
            <p>输入创意想法后</p>
            <p className={s.emptyHint}>自动推荐相关参考作品</p>
            <p className={s.emptyHint}>分析其设定手法供您借鉴</p>
          </div>
        )}

        {loading && (
          <div className={s.loadingState}>
            <div className={s.loadingDots}><span /><span /><span /></div>
            <p>正在寻找参考作品…</p>
          </div>
        )}

        {error && !loading && (
          <div className={s.errorState}>{error}</div>
        )}

        {result && !loading && (
          <>
            <div className={s.cardList}>
              {result.cards.map((card, i) => (
                <CardItem
                  key={i}
                  card={card}
                  expanded={expanded === i}
                  onToggle={() => setExpanded(expanded === i ? null : i)}
                />
              ))}
            </div>

            {result.writing_tips.length > 0 && (
              <div className={s.tipsSection}>
                <div className={s.tipsSectionTitle}>
                  <span>◈</span> 针对您的创意
                </div>
                {result.writing_tips.map((tip, i) => (
                  <div key={i} className={s.tip}>
                    <span className={s.tipNum}>{i + 1}</span>
                    <p>{tip}</p>
                  </div>
                ))}
              </div>
            )}

            <div className={s.disclaimer}>
              ※ 仅供参考，请勿直接复制他人作品
            </div>
          </>
        )}
      </div>
    </div>
  )
}

function CardItem({
  card, expanded, onToggle
}: {
  card: InspirationCard
  expanded: boolean
  onToggle: () => void
}) {
  return (
    <div className={`${s.card} ${expanded ? s.cardExpanded : ''}`}>
      <button className={s.cardHead} onClick={onToggle}>
        <div className={s.cardMeta}>
          <span className={s.cardType}>{TYPE_LABEL[card.type] || card.type}</span>
          <span className={s.cardGenre}>{card.genre}</span>
        </div>
        <div className={s.cardTitleRow}>
          <span className={s.cardTitle}>{card.title}</span>
          <span className={s.chevron}>{expanded ? '▲' : '▼'}</span>
        </div>
        <p className={s.cardRelevance}>{card.why_relevant}</p>
      </button>

      {expanded && (
        <div className={s.cardBody}>
          {card.highlights.length > 0 && (
            <div className={s.section}>
              <div className={s.sectionTitle}>✦ 值得借鉴</div>
              {card.highlights.map((h, i) => (
                <div key={i} className={s.point}>
                  <span className={s.dot} />
                  <p>{h}</p>
                </div>
              ))}
            </div>
          )}
          {card.techniques.length > 0 && (
            <div className={s.section}>
              <div className={s.sectionTitle}>◈ 具体手法</div>
              {card.techniques.map((t, i) => (
                <div key={i} className={s.technique}>
                  <span className={s.techNum}>{i + 1}</span>
                  <p>{t}</p>
                </div>
              ))}
            </div>
          )}
          {card.caution && (
            <div className={s.caution}>
              <span>⚠</span>
              <p>{card.caution}</p>
            </div>
          )}
        </div>
      )}
    </div>
  )
}
