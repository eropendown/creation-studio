import { useEffect, useState } from 'react'
import { useMangaStore } from '../stores/mangaStore'
import OutlineForm from '../components/manga/OutlineForm'
import SceneGrid from '../components/manga/SceneGrid'
import PipelinePanel from '../components/manga/PipelinePanel'
import HistoryPanel from '../components/manga/HistoryPanel'
import s from './MangaStudio.module.css'

type Tab = 'create' | 'history' | 'pipeline'

export default function MangaStudio() {
  const { activeOutlineId, activeOutline, loadOutlines, activeJobId } = useMangaStore()
  const [tab, setTab] = useState<Tab>('create')

  useEffect(() => { loadOutlines() }, [])

  // 生成任务开始时自动切换到 pipeline tab
  useEffect(() => {
    if (activeJobId) setTab('pipeline')
  }, [activeJobId])

  const tabs: { id: Tab; label: string; icon: string }[] = [
    { id: 'create',   label: '创建大纲', icon: '📝' },
    { id: 'history',  label: '历史大纲', icon: '📚' },
    { id: 'pipeline', label: '生成任务', icon: '⚙️' },
  ]

  return (
    <div className={s.root}>
      {/* 顶栏 */}
      <header className={s.topbar}>
        <div className={s.topbarLeft}>
          <span className={s.titleIcon}>🎬</span>
          <span className={s.title}>漫剧生成工作台</span>
          {activeOutline && (
            <span className={s.activeTitle}>
              《{String((activeOutline as Record<string,unknown>).title || '')}》
            </span>
          )}
        </div>
        <div className={s.tabs}>
          {tabs.map(t => (
            <button
              key={t.id}
              className={`${s.tabBtn} ${tab === t.id ? s.tabActive : ''}`}
              onClick={() => setTab(t.id)}
            >
              <span>{t.icon}</span>
              <span>{t.label}</span>
              {t.id === 'pipeline' && activeJobId && (
                <span className={s.jobDot} />
              )}
            </button>
          ))}
        </div>
      </header>

      {/* 内容区 */}
      <div className={s.body}>
        {tab === 'create' && (
          <div className={s.twoCol}>
            <div className={s.leftCol}>
              <OutlineForm onCreated={() => setTab('history')} />
            </div>
            <div className={s.rightCol}>
              {activeOutlineId && activeOutline
                ? <SceneGrid />
                : <OutlinePlaceholder onGoHistory={() => setTab('history')} />
              }
            </div>
          </div>
        )}

        {tab === 'history' && (
          <HistoryPanel onSelect={() => setTab('create')} />
        )}

        {tab === 'pipeline' && (
          <PipelinePanel />
        )}
      </div>
    </div>
  )
}

function OutlinePlaceholder({ onGoHistory }: { onGoHistory: () => void }) {
  return (
    <div className={s.placeholder}>
      <div className={s.placeholderIcon}>🎬</div>
      <p className={s.placeholderTitle}>选择或创建一个大纲</p>
      <p className={s.placeholderSub}>在左侧填写故事信息生成新大纲，或从历史中选择</p>
      <button className="btn btn-secondary btn-sm" onClick={onGoHistory}>
        查看历史大纲
      </button>
    </div>
  )
}
