import React, { useRef } from 'react'
import { useMangaStore } from '../../stores/mangaStore'
import { mangaApi } from '../../api/manga'
import s from './SceneGrid.module.css'

const EMOTION_COLORS: Record<string, string> = {
  '震惊': '#C0392B', '愤怒': '#E74C3C', '柔情': '#E67E22',
  '紧张': '#1B4F72', '释然': '#1E6B44', '悲伤': '#6C5CE7',
  '喜悦': '#8B6914', '坚定': '#1A1916', '迷茫': '#636E72',
}

export default function SceneGrid() {
  const { activeOutline, activeOutlineId, loadOutline } = useMangaStore()

  if (!activeOutline) return null

  const o = activeOutline as any
  const scenes = (o.scene_breakdown || []) as any[]
  const totalScenes  = scenes.length
  const imagesUploaded = scenes.filter(s => s.image_uploaded).length
  const audioReady   = scenes.filter(s => s.audio_path).length

  return (
    <div className={s.root}>
      {/* 大纲信息头 */}
      <div className={s.outlineHeader}>
        <div className={s.outlineInfo}>
          <h2 className={s.outlineTitle}>《{String(o.title || '')}》</h2>
          <div className={s.outlineMeta}>
            <span className="badge badge-paper">{String(o.genre || '')}</span>
            <span className="badge badge-paper">{String(o.style || '')}</span>
            <span className="badge badge-blue">{totalScenes} 分镜</span>
            <span className="badge badge-paper">≈ {Math.round((o.estimated_duration as number || 0))}秒</span>
          </div>
        </div>
        <div className={s.outlineStats}>
          <Stat label="图片" value={`${imagesUploaded}/${totalScenes}`} color={imagesUploaded === totalScenes ? 'green' : 'ink'} />
          <Stat label="配音" value={`${audioReady}/${totalScenes}`}   color={audioReady === totalScenes ? 'green' : 'ink'} />
        </div>
      </div>

      {/* 核心剧情 */}
      {o.synopsis && (
        <div className={s.synopsis}>
          <span className={s.synopsisLabel}>剧情简介</span>
          {String(o.synopsis)}
        </div>
      )}

      {/* 分镜网格 */}
      <div className={s.gridSection}>
        <div className="sec-head">
          <span>📽️ 分镜列表</span>
          <span className="badge badge-paper">
            {imagesUploaded}/{totalScenes} 图片已上传
          </span>
        </div>
        <div className={s.grid}>
          {scenes.map((sc, i) => (
            <SceneCard
              key={i}
              scene={sc}
              outlineId={activeOutlineId!}
              onUploaded={() => loadOutline(activeOutlineId!)}
            />
          ))}
        </div>
      </div>
    </div>
  )
}

/* ── 单个分镜卡片 ──────────────────────────────── */
function SceneCard({
  scene, outlineId, onUploaded
}: {
  scene: any
  outlineId: string
  onUploaded: () => void
}) {
  const fileRef = useRef<HTMLInputElement>(null)
  const sid = scene.scene_id as number
  const emotion = String(scene.emotion || '')
  const accentColor = EMOTION_COLORS[emotion] || 'var(--ink-0)'
  const hasImage = !!scene.image_uploaded

  const handleUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file) return
    await mangaApi.uploadImage(outlineId, sid, file)
    onUploaded()
  }

  return (
    <div className={`${s.card} ${hasImage ? s.cardDone : ''}`}>
      {/* 序号 + 情绪 */}
      <div className={s.cardTop} style={{ borderLeftColor: accentColor }}>
        <div className={s.cardNum}>
          <span className={s.numBadge}>{String(sid).padStart(2, '0')}</span>
          <span className={s.actBadge}>ACT {scene.act}</span>
        </div>
        <span className={s.emotionTag} style={{ color: accentColor }}>
          {emotion}
        </span>
      </div>

      {/* 图片区 */}
      <div className={s.imageArea} onClick={() => fileRef.current?.click()}>
        {scene.image_url ? (
          <img src={String(scene.image_url)} alt={String(scene.title)} className={s.sceneImg} />
        ) : (
          <div className={s.imagePlaceholder}>
            <span className={s.uploadIcon}>📷</span>
            <span>点击上传分镜图</span>
          </div>
        )}
        <div className={s.imageOverlay}>
          <span>更换图片</span>
        </div>
        <input
          ref={fileRef}
          type="file"
          accept="image/*"
          style={{ display: 'none' }}
          onChange={handleUpload}
        />
      </div>

      {/* 分镜信息 */}
      <div className={s.cardBody}>
        <div className={s.sceneTitle}>{String(scene.title || '')}</div>
        <p className={s.narration}>「{String(scene.narration || '')}」</p>
        <div className={s.sceneDetail}>
          <span className={s.detail}>{String(scene.camera_shot || '')}</span>
          <span className={s.duration}>{Number(scene.duration_estimate || 0).toFixed(1)}s</span>
        </div>
      </div>

      {/* Prompt 区 */}
      {scene.image_prompt && (
        <details className={s.promptDetail}>
          <summary className={s.promptSummary}>SD Prompt</summary>
          <div className={s.promptText}>{String(scene.image_prompt)}</div>
          <button
            className="btn btn-ghost btn-sm"
            style={{ margin: '6px 0 0' }}
            onClick={() => navigator.clipboard.writeText(String(scene.image_prompt))}
          >📋 复制</button>
        </details>
      )}

      {/* 状态指示 */}
      <div className={s.cardFooter}>
        <span className={`badge ${hasImage ? 'badge-green' : 'badge-paper'}`}>
          {hasImage ? '✓ 图片已就绪' : '⏳ 待上传图片'}
        </span>
        {scene.audio_path && (
          <span className="badge badge-blue">🎙️ 配音完成</span>
        )}
      </div>
    </div>
  )
}

function Stat({ label, value, color }: { label: string; value: string; color: string }) {
  return (
    <div style={{ textAlign: 'center' }}>
      <div style={{
        fontFamily: 'var(--font-mono)', fontSize: 16, fontWeight: 700,
        color: color === 'green' ? 'var(--green)' : 'var(--ink-0)',
      }}>{value}</div>
      <div style={{ fontFamily: 'var(--font-mono)', fontSize: 9, color: 'var(--ink-3)', letterSpacing: 1 }}>
        {label}
      </div>
    </div>
  )
}
