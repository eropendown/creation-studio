import { useEffect, useRef } from 'react'
import { useMangaStore } from '../../stores/mangaStore'
import s from './PipelinePanel.module.css'

export default function PipelinePanel() {
  const { activeJobId, activeOutlineId, jobs, startGenerate, updateJobStatus, activeOutline, isGenerating } = useMangaStore()
  const wsRef = useRef<WebSocket | null>(null)
  const job = activeJobId ? jobs[activeJobId] : null

  // WebSocket 连接
  useEffect(() => {
    if (!activeJobId) return

    const proto = location.protocol === 'https:' ? 'wss' : 'ws'
    const ws = new WebSocket(`${proto}://${location.host}/ws/${activeJobId}`)
    wsRef.current = ws

    ws.onmessage = (e) => {
      try {
        const data = JSON.parse(e.data)
        if (data.type === 'state_update') {
          updateJobStatus(data)
        }
        if (data.type === 'ping') ws.send(JSON.stringify({ type: 'pong' }))
      } catch (err) {
        console.error('WS message parse error:', err)
      }
    }

    ws.onclose = () => { wsRef.current = null }

    return () => { ws.close() }
  }, [activeJobId])

  const handleStart = async () => {
    if (!activeOutlineId) return
    await startGenerate(activeOutlineId)
  }

  const outlineTitle = activeOutline
    ? String((activeOutline as Record<string,unknown>).title || '')
    : ''

  return (
    <div className={s.root}>
      <div className="sec-head">
        <span>⚙️ 生成流水线</span>
        {job && (
          <span className={`badge ${STATUS_BADGE[job.overall_status] || 'badge-paper'}`}>
            {STATUS_LABEL[job.overall_status] || job.overall_status}
          </span>
        )}
      </div>

      <div className={s.body}>
        {/* 无任务状态 */}
        {!activeJobId && !job && (
          <div className={s.startSection}>
            {activeOutlineId ? (
              <>
                <div className={s.readyInfo}>
                  <div className={s.readyIcon}>🎬</div>
                  <p className={s.readyTitle}>准备生成</p>
                  <p className={s.readyDesc}>
                    「{outlineTitle}」大纲已就绪<br />
                    点击按钮开始配音 + 剪辑流水线
                  </p>
                </div>
                <button
                  className={`btn btn-primary btn-lg ${isGenerating ? 'btn-loading' : ''}`}
                  onClick={handleStart}
                  disabled={isGenerating}
                >
                  {isGenerating ? <><span className="spin" /> 启动中…</> : '🚀 开始生成'}
                </button>
              </>
            ) : (
              <div className={s.noOutline}>
                <p>请先创建或选择一个大纲</p>
              </div>
            )}
          </div>
        )}

        {/* 任务进行中 / 完成 */}
        {job && (
          <div className={s.jobSection}>
            {/* 总进度 */}
            <div className={s.overallProgress}>
              <div className={s.progressLabel}>
                <span>总进度</span>
                <span className={s.progressNum}>{job.overall_progress}%</span>
              </div>
              <div className="progress-bar" style={{ height: 8 }}>
                <div
                  className={`progress-fill ${job.overall_status === 'error' ? 'red' : job.overall_status === 'done' ? '' : 'gold'}`}
                  style={{ width: `${job.overall_progress}%` }}
                />
              </div>
            </div>

            {/* Agent 状态列表 */}
            <div className={s.agentList}>
              {Object.values(job.agents || {}).map((ag: Record<string,unknown>) => (
                <AgentCard key={ag.name as string} agent={ag} />
              ))}
            </div>

            {/* 错误信息 */}
            {job.error_message && (
              <div className={s.errorBox}>
                <strong>错误：</strong>{job.error_message}
              </div>
            )}

            {/* 完成结果 */}
            {job.overall_status === 'done' && (
              <div className={s.resultBox}>
                <div className={s.resultTitle}>✅ 生成完成！</div>
                {job.final_video_url && (
                  <a
                    href={job.final_video_url}
                    className="btn btn-primary"
                    download
                    target="_blank"
                  >
                    📥 下载 MP4
                  </a>
                )}
                {job.jianying_draft_dir && (
                  <div className={s.jianyingInfo}>
                    <div className={s.jianyingTitle}>📁 剪映草稿已就绪</div>
                    <code className={s.jianyingPath}>{job.jianying_draft_dir}</code>
                    <p className={s.jianyingDesc}>
                      将上方文件夹路径粘贴至剪映桌面版「本地草稿」即可导入。
                    </p>
                  </div>
                )}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  )
}

function AgentCard({ agent }: { agent: Record<string,unknown> }) {
  const status = String(agent.status || 'idle')
  const progress = Number(agent.progress || 0)

  return (
    <div className={`${s.agentCard} ${s['agent_' + status]}`}>
      <div className={s.agentHead}>
        <span className={s.agentEmoji}>{String(agent.emoji || '🤖')}</span>
        <div className={s.agentInfo}>
          <div className={s.agentName}>{String(agent.display_name || '')}</div>
          <div className={s.agentMsg}>{String(agent.message || '')}</div>
        </div>
        <div className={s.agentRight}>
          <StatusIcon status={status} />
          {status === 'running' && (
            <span className={s.agentPct}>{progress}%</span>
          )}
        </div>
      </div>
      {status === 'running' && (
        <div className="progress-bar" style={{ marginTop: 8 }}>
          <div className="progress-fill gold" style={{ width: `${progress}%` }} />
        </div>
      )}
    </div>
  )
}

function StatusIcon({ status }: { status: string }) {
  if (status === 'running') return <span className="spin" style={{ width: 14, height: 14 }} />
  if (status === 'done')    return <span style={{ color: 'var(--green)', fontSize: 14 }}>✓</span>
  if (status === 'error')   return <span style={{ color: 'var(--red)',   fontSize: 14 }}>✗</span>
  return <span style={{ color: 'var(--ink-4)', fontSize: 14 }}>○</span>
}

const STATUS_LABEL: Record<string, string> = {
  idle: '空闲', running: '运行中', done: '完成', error: '错误'
}
const STATUS_BADGE: Record<string, string> = {
  idle: 'badge-paper', running: 'badge-gold', done: 'badge-green', error: 'badge-red'
}
