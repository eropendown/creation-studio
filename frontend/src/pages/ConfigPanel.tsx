import React, { useEffect, useState, useRef } from 'react'
import { useMangaStore } from '../stores/mangaStore'
import { SystemConfig } from '../api/manga'
import s from './ConfigPanel.module.css'

type Section = 'llm' | 'tts' | 'video' | 'prompts'

interface LlmPreset {
  name: string
  base_url: string
  model: string
  description: string
}

export default function ConfigPanel() {
  const { config, configLoaded, loadConfig, saveConfig } = useMangaStore()
  const [draft, setDraft] = useState<SystemConfig | null>(null)
  const [section, setSection] = useState<Section>('llm')
  const [saved, setSaved] = useState(false)
  const [presets, setPresets] = useState<LlmPreset[]>([])
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  useEffect(() => { if (!configLoaded) loadConfig() }, [])
  useEffect(() => { if (config) setDraft(JSON.parse(JSON.stringify(config))) }, [config])
  useEffect(() => { return () => { if (timerRef.current) clearTimeout(timerRef.current) } }, [])
  useEffect(() => {
    fetch('/api/llm/presets').then(r => r.json()).then(d => setPresets(d.presets || [])).catch(() => {})
  }, [])

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

  const applyPreset = (p: LlmPreset) => {
    setDraft(d => d ? { ...d, llm: { ...d.llm, provider: 'real', base_url: p.base_url, model: p.model } } : d)
  }

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
              <Row label="模式">
                <select
                  className="select"
                  value={draft.llm.provider}
                  onChange={e => setLlm('provider', e.target.value)}
                >
                  <option value="real">真实模型</option>
                  <option value="mock">Mock（测试用）</option>
                </select>
              </Row>

              {draft.llm.provider !== 'mock' && (
                <>
                  <Row label="快速选择">
                    <div className={s.presetGrid}>
                      {presets.map(p => (
                        <button
                          key={p.name}
                          className={`${s.presetBtn} ${draft.llm.base_url === p.base_url && draft.llm.model === p.model ? s.presetActive : ''}`}
                          onClick={() => applyPreset(p)}
                          title={p.description}
                        >
                          <span className={s.presetName}>{p.name}</span>
                        </button>
                      ))}
                    </div>
                  </Row>

                  <Row label="Base URL">
                    <input
                      type="text" className="input input-mono"
                      value={draft.llm.base_url}
                      onChange={e => setLlm('base_url', e.target.value)}
                      placeholder="https://api.example.com/v1"
                    />
                  </Row>
                  <Row label="模型名称">
                    <input
                      type="text" className="input input-mono"
                      value={draft.llm.model}
                      onChange={e => setLlm('model', e.target.value)}
                      placeholder="deepseek-chat / qwen-plus / ..."
                    />
                  </Row>
                  <Row label="API Key">
                    <input
                      type="password" className="input input-mono"
                      value={draft.llm.api_key}
                      onChange={e => setLlm('api_key', e.target.value)}
                      placeholder="sk-..."
                    />
                  </Row>

                  <div className={s.hint}>
                    💡 兼容所有 OpenAI 协议的模型服务。点击上方预设按钮快速配置，
                    或手动填写 Base URL + 模型名称。支持 DeepSeek / 通义千问 / 智谱 / Kimi / 豆包 / Ollama 等。
                  </div>
                </>
              )}

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
                  <option value="edge_tts">Edge TTS（免费推荐）</option>
                  <option value="openai">OpenAI TTS</option>
                  <option value="elevenlabs">ElevenLabs</option>
                  <option value="volcengine">火山引擎 TTS</option>
                  <option value="mock">Mock（测试用）</option>
                </select>
              </Row>

              {draft.tts.provider === 'edge_tts' && (
                <>
                  <Row label="中文音色">
                    <select
                      className="select"
                      value={draft.tts.voice_id}
                      onChange={e => setTts('voice_id', e.target.value)}
                    >
                      <option value="zh-CN-YunxiNeural">云希（元气男声）</option>
                      <option value="zh-CN-YunjianNeural">云健（沉稳男声）</option>
                      <option value="zh-CN-XiaoxiaoNeural">晓晓（活泼女声）</option>
                      <option value="zh-CN-XiaoyiNeural">晓伊（温柔女声）</option>
                      <option value="zh-CN-XiaochenNeural">晓辰（知性女声）</option>
                      <option value="zh-CN-XiaohanNeural">晓涵（温暖女声）</option>
                      <option value="zh-CN-YunyangNeural">云扬（新闻播报）</option>
                      <option value="zh-CN-YunzeNeural">云泽（深沉男声）</option>
                    </select>
                  </Row>
                  <div className={s.hint}>
                    💡 Edge TTS 免费使用微软神经网络语音，中文效果优秀，无需 API Key。
                    情绪会自动匹配不同音色。
                  </div>
                </>
              )}

              {(draft.tts.provider === 'openai' || draft.tts.provider === 'elevenlabs') && (
                <>
                  <Row label="API Key">
                    <input
                      type="password" className="input input-mono"
                      value={draft.tts.api_key}
                      onChange={e => setTts('api_key', e.target.value)}
                      placeholder="API 密钥"
                    />
                  </Row>
                  <Row label="Voice ID">
                    <input
                      type="text" className="input input-mono"
                      value={draft.tts.voice_id}
                      onChange={e => setTts('voice_id', e.target.value)}
                      placeholder={draft.tts.provider === 'openai' ? 'nova / alloy / shimmer' : 'ElevenLabs Voice ID'}
                    />
                  </Row>
                </>
              )}

              {draft.tts.provider === 'volcengine' && (
                <>
                  <Row label="App ID">
                    <input
                      type="text" className="input input-mono"
                      value={draft.tts.volcengine_app_id}
                      onChange={e => setTts('volcengine_app_id', e.target.value)}
                      placeholder="火山引擎应用 ID"
                    />
                  </Row>
                  <Row label="Access Key">
                    <input
                      type="password" className="input input-mono"
                      value={draft.tts.volcengine_access_key}
                      onChange={e => setTts('volcengine_access_key', e.target.value)}
                      placeholder="Access Key"
                    />
                  </Row>
                  <Row label="Secret Key">
                    <input
                      type="password" className="input input-mono"
                      value={draft.tts.volcengine_secret_key}
                      onChange={e => setTts('volcengine_secret_key', e.target.value)}
                      placeholder="Secret Key"
                    />
                  </Row>
                  <Row label="音色">
                    <input
                      type="text" className="input input-mono"
                      value={draft.tts.voice_id}
                      onChange={e => setTts('voice_id', e.target.value)}
                      placeholder="zh_female_shuangkuaisisi_moon_bigtts"
                    />
                  </Row>
                  <div className={s.hint}>
                    💡 火山引擎 TTS 需开通语音合成服务，约 ¥0.02/千次调用。
                    音色列表参考火山引擎控制台。
                  </div>
                </>
              )}

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

              <div className={s.divider} />
              <div className={s.subSectionTitle}>🎥 AI 视频生成（火山引擎 Seedance）</div>

              <Row label="API Key">
                <input
                  type="password" className="input input-mono"
                  value={draft.video.volcengine_api_key}
                  onChange={e => setVideo('volcengine_api_key', e.target.value)}
                  placeholder="火山方舟 API Key"
                />
              </Row>
              <Row label="模型">
                <select
                  className="select"
                  value={draft.video.volcengine_model}
                  onChange={e => setVideo('volcengine_model', e.target.value)}
                >
                  <option value="seedance-2.0">Seedance 2.0（推荐）</option>
                  <option value="seedance-1.0-pro">Seedance 1.0 Pro</option>
                </select>
              </Row>

              <div className={s.hint}>
                💡 配置火山引擎 API Key 后，系统会对每个分镜场景自动生成视频片段。
                未配置则跳过此步骤，使用用户上传的图片/视频。
                <br/>📎 你也可以在分镜列表中直接上传视频，系统会优先使用已上传的素材。
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
