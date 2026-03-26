import React, { useEffect, useState, useRef } from 'react'
import { useMangaStore } from '../stores/mangaStore'
import { SystemConfig } from '../api/manga'
import s from './ConfigPanel.module.css'

type Section = 'llm' | 'tts' | 'video' | 'prompts'

export default function ConfigPanel() {
  const { config, configLoaded, loadConfig, saveConfig } = useMangaStore()
  const [draft, setDraft] = useState<SystemConfig | null>(null)
  const [section, setSection] = useState<Section>('llm')
  const [saved, setSaved] = useState(false)
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  useEffect(() => { if (!configLoaded) loadConfig() }, [])
  useEffect(() => { if (config) setDraft(JSON.parse(JSON.stringify(config))) }, [config])
  useEffect(() => { return () => { if (timerRef.current) clearTimeout(timerRef.current) } }, [])

  const handleSave = async () => {
    if (!draft) return
    await saveConfig(draft)
    setSaved(true)
    if (timerRef.current) clearTimeout(timerRef.current)
    timerRef.current = setTimeout(() => setSaved(false), 2000)
  }

  const setLlm  = (k: string, v: unknown) => setDraft(d => d ? { ...d, llm:   { ...d.llm,   [k]: v } } : d)
  const setTts  = (k: string, v: unknown) => setDraft(d => d ? { ...d, tts:   { ...d.tts,   [k]: v } } : d)
  const setVideo = (k: string, v: unknown) => setDraft(d => d ? { ...d, video: { ...d.video, [k]: v } } : d)
  const setPrompt = (k: string, v: string) => setDraft(d => d ? { ...d, prompts: { ...d.prompts, [k]: v } } : d)

  if (!draft) {
    return (
      <div className={s.loading}>
        <span className="spin" /> 加载配置中…
      </div>
    )
  }

  const SECTIONS: { id: Section; label: string; icon: string }[] = [
    { id: 'llm',     label: 'LLM 模型',  icon: '🧠' },
    { id: 'tts',     label: '配音 TTS',  icon: '🎙️' },
    { id: 'video',   label: '视频输出',  icon: '🎬' },
    { id: 'prompts', label: '提示词',    icon: '📝' },
  ]

  return (
    <div className={s.root}>
      <header className={s.topbar}>
        <div className={s.topbarLeft}>
          <span className={s.titleIcon}>⚙️</span>
          <span className={s.title}>系统配置</span>
          <span className="badge badge-paper">v{draft.config_version || '6.0'}</span>
        </div>
        <div className={s.topbarRight}>
          <button
            className={`btn ${saved ? 'btn-gold' : 'btn-primary'}`}
            onClick={handleSave}
          >
            {saved ? '✓ 已保存' : '💾 保存配置'}
          </button>
        </div>
      </header>

      <div className={s.body}>
        {/* 左侧导航 */}
        <nav className={s.sideNav}>
          {SECTIONS.map(sec => (
            <button
              key={sec.id}
              className={`${s.navItem} ${section === sec.id ? s.navActive : ''}`}
              onClick={() => setSection(sec.id)}
            >
              <span>{sec.icon}</span>
              <span>{sec.label}</span>
            </button>
          ))}
        </nav>

        {/* 右侧内容 */}
        <div className={s.content}>
          {section === 'llm' && (
            <Section title="🧠 LLM 大语言模型">
              <Row label="提供商">
                <select
                  className="select"
                  value={draft.llm.provider}
                  onChange={e => setLlm('provider', e.target.value)}
                >
                  <option value="mock">Mock（测试用）</option>
                  <option value="openai">OpenAI</option>
                  <option value="deepseek">DeepSeek</option>
                </select>
              </Row>
              <Row label="API Key">
                <input
                  type="password" className="input input-mono"
                  value={draft.llm.api_key}
                  onChange={e => setLlm('api_key', e.target.value)}
                  placeholder="sk-..."
                />
              </Row>
              <Row label="Base URL">
                <input
                  type="text" className="input input-mono"
                  value={draft.llm.base_url}
                  onChange={e => setLlm('base_url', e.target.value)}
                />
              </Row>
              <Row label="模型名称">
                <input
                  type="text" className="input input-mono"
                  value={draft.llm.model}
                  onChange={e => setLlm('model', e.target.value)}
                  placeholder="gpt-4o-mini / deepseek-chat"
                />
              </Row>
              <Row label={`Temperature: ${draft.llm.temperature}`}>
                <input
                  type="range" min="0" max="2" step="0.1"
                  value={draft.llm.temperature}
                  onChange={e => setLlm('temperature', parseFloat(e.target.value))}
                  className={s.range}
                />
              </Row>
              <Row label={`Max Tokens: ${draft.llm.max_tokens}`}>
                <input
                  type="range" min="512" max="8192" step="256"
                  value={draft.llm.max_tokens}
                  onChange={e => setLlm('max_tokens', parseInt(e.target.value, 10))}
                  className={s.range}
                />
              </Row>

              {draft.llm.provider !== 'mock' && (
                <div className={s.hint}>
                  ⚠️ DeepSeek 用户请将 Base URL 设为 <code>https://api.deepseek.com/v1</code>
                  ，模型名设为 <code>deepseek-chat</code>
                </div>
              )}
            </Section>
          )}

          {section === 'tts' && (
            <Section title="🎙️ 配音 TTS 设置">
              <Row label="提供商">
                <select
                  className="select"
                  value={draft.tts.provider}
                  onChange={e => setTts('provider', e.target.value)}
                >
                  <option value="mock">Mock（测试用）</option>
                  <option value="openai">OpenAI TTS</option>
                  <option value="elevenlabs">ElevenLabs</option>
                </select>
              </Row>
              <Row label="API Key">
                <input
                  type="password" className="input input-mono"
                  value={draft.tts.api_key}
                  onChange={e => setTts('api_key', e.target.value)}
                  placeholder="API 密钥"
                />
              </Row>
              <Row label="Voice ID / 音色">
                <input
                  type="text" className="input input-mono"
                  value={draft.tts.voice_id}
                  onChange={e => setTts('voice_id', e.target.value)}
                  placeholder="nova / alloy / shimmer 或 ElevenLabs Voice ID"
                />
              </Row>
              <Row label={`语速: ${draft.tts.speed}x`}>
                <input
                  type="range" min="0.5" max="2.0" step="0.1"
                  value={draft.tts.speed}
                  onChange={e => setTts('speed', parseFloat(e.target.value))}
                  className={s.range}
                />
              </Row>
            </Section>
          )}

          {section === 'video' && (
            <Section title="🎬 视频输出设置">
              <Row label="输出模式">
                <select
                  className="select"
                  value={draft.video.mode}
                  onChange={e => setVideo('mode', e.target.value)}
                >
                  <option value="jianying">剪映草稿（推荐）</option>
                  <option value="moviepy">直接合成 MP4</option>
                </select>
              </Row>
              <Row label="帧率 FPS">
                <select
                  className="select"
                  value={draft.video.fps}
                  onChange={e => setVideo('fps', parseInt(e.target.value, 10))}
                >
                  <option value={24}>24 fps</option>
                  <option value={30}>30 fps</option>
                  <option value={60}>60 fps</option>
                </select>
              </Row>
              <Row label="分辨率">
                <select
                  className="select"
                  value={draft.video.resolution}
                  onChange={e => setVideo('resolution', e.target.value)}
                >
                  <option value="1920x1080">1920×1080（Full HD）</option>
                  <option value="1280x720">1280×720（HD）</option>
                  <option value="1080x1920">1080×1920（竖屏）</option>
                </select>
              </Row>
              <Row label="字幕">
                <label className={s.toggle}>
                  <input
                    type="checkbox"
                    checked={draft.video.subtitle_enabled}
                    onChange={e => setVideo('subtitle_enabled', e.target.checked)}
                  />
                  <span className={s.toggleLabel}>
                    {draft.video.subtitle_enabled ? '已开启' : '已关闭'}
                  </span>
                </label>
              </Row>

              <div className={s.hint}>
                💡 推荐使用「剪映草稿」模式：生成后将草稿目录导入剪映桌面版，
                可在剪映中调整转场、配乐、字幕样式后导出。
              </div>
            </Section>
          )}

          {section === 'prompts' && (
            <Section title="📝 提示词编辑">
              <div className={s.promptNote}>
                以下提示词控制 AI 生成漫剧大纲的行为，修改后点击保存生效。
              </div>
              {Object.entries(draft.prompts || {}).map(([k, v]) => (
                <div key={k} className={s.promptGroup}>
                  <label className="form-label">{k}</label>
                  <textarea
                    className="textarea textarea-mono"
                    value={v}
                    onChange={e => setPrompt(k, e.target.value)}
                    rows={6}
                  />
                </div>
              ))}
            </Section>
          )}
        </div>
      </div>
    </div>
  )
}

/* ── 子组件 ──────────────────────────────────────── */
function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className={s.section}>
      <div className="sec-head">{title}</div>
      <div className={s.sectionBody}>{children}</div>
    </div>
  )
}

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className={s.row}>
      <label className={s.rowLabel}>{label}</label>
      <div className={s.rowControl}>{children}</div>
    </div>
  )
}
