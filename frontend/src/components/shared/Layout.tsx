import { Outlet, NavLink, useLocation } from 'react-router-dom'
import s from './Layout.module.css'

const NAV = [
  { to: '/novel', emoji: '✍️', label: '小说创作', code: 'NOVEL' },
  { to: '/manga', emoji: '🎬', label: '漫剧生成', code: 'MANGA' },
  { to: '/config', emoji: '⚙️', label: '系统配置', code: 'CONFIG' },
]

export default function Layout() {
  const location = useLocation()

  return (
    <div className={s.root}>
      <aside className={s.sidebar}>
        <div className={s.masthead}>
          <div className={s.mastheadTop}>
            <span className={s.monogram}>◈</span>
            <span className={s.version}>v7.0</span>
          </div>
          <div className={s.title}>创作工作室</div>
          <div className={s.subtitle}>MULTI-AGENT STUDIO</div>
          <div className={s.statusLine}>
            <span className="led" /> <span className={s.statusText}>系统运行中</span>
          </div>
        </div>

        <nav className={s.nav}>
          {NAV.map(n => (
            <NavLink
              key={n.to} to={n.to}
              className={({ isActive }) => `${s.navItem} ${isActive ? s.active : ''}`}
            >
              <span className={s.navEmoji}>{n.emoji}</span>
              <span className={s.navLabel}>{n.label}</span>
              <span className={s.navCode}>{n.code}</span>
            </NavLink>
          ))}
        </nav>

        <div className={s.footer}>
          <div className={s.footerRule} />
          <p className={s.footerNote}>AI 创作辅助工具</p>
          <p className={s.footerNote}>基于 FastAPI + React</p>
        </div>
      </aside>

      <main className={s.main}>
        <Outlet />
      </main>

      {/* 移动端底部导航 */}
      <nav className="mobile-nav">
        <div className="mobile-nav-inner">
          {NAV.map(n => (
            <NavLink
              key={n.to} to={n.to}
              className={({ isActive }) => isActive ? 'active' : ''}
            >
              <span className="nav-emoji">{n.emoji}</span>
              <span>{n.label}</span>
            </NavLink>
          ))}
        </div>
      </nav>
    </div>
  )
}
