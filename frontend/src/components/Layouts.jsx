import { Activity, BookOpen, Compass, Database, FileText, Home, LayoutDashboard, LogOut, Map, Menu, Moon, Radar, Smartphone, Sun, User, UserCheck, Users, Monitor } from 'lucide-react'
import { useState } from 'react'
import { NavLink, Outlet, useNavigate } from 'react-router-dom'
import { IS_DEMO } from '../api/client'
import { useAuth } from '../context/AuthContext'
import { useLive } from '../context/LiveContext'
import { useTheme } from '../context/ThemeContext'
import { SampleBadge } from './ui'

export function BrandMark({ size = 34 }) {
  return (
    <div className="brand-mark" style={{ width: size, height: size }}>
      <svg width={size * 0.55} height={size * 0.55} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinejoin="round">
        <path d="M12 3 L17 21 H7 Z" /><path d="M9.2 14 H14.8" /><path d="M10.4 9 H13.6" />
      </svg>
    </div>
  )
}

export function ThemeButton({ className = 'icon-btn' }) {
  const { resolved, toggle } = useTheme()
  return (
    <button className={className} onClick={toggle} aria-label="Switch light or dark mode" title="Light / dark mode">
      {resolved === 'dark' ? <Sun size={17} /> : <Moon size={17} />}
    </button>
  )
}

export function Toasts() {
  const { toasts } = useLive()
  return (
    <div className="toasts" aria-live="polite">
      {toasts.map((t) => (
        <div key={t.id} className={`toast ${t.tone || ''}`}>
          <div>
            <div style={{ fontWeight: 600 }}>{t.title}</div>
            {t.body && <div className="small ink2 mt-4">{t.body}</div>}
          </div>
        </div>
      ))}
    </div>
  )
}

export function OfficeLayout() {
  const { user, logout } = useAuth()
  const { connected, breaches } = useLive()
  const [open, setOpen] = useState(false)
  const nav = useNavigate()
  const openBreaches = breaches.filter((b) => b.is_breach).length
  const links = [
    { to: '/office', end: true, icon: LayoutDashboard, label: 'Overview' },
    { to: '/office/map', icon: Map, label: 'Location map' },
    { to: '/office/offset', icon: Radar, label: 'Offset wells' },
    { to: '/office/knowledge', icon: BookOpen, label: 'Knowledge base' },
    { to: '/office/tracking', icon: Activity, label: 'Live tracking', count: openBreaches },
    { to: '/office/drillers', icon: user.role === 'admin' ? UserCheck : Users, label: user.role === 'admin' ? 'Approvals' : 'Drillers' },
    { to: '/office/documents', icon: FileText, label: 'Document extraction' },
    { to: '/office/data', icon: Database, label: 'Data & models' },
  ]
  return (
    <div className="office">
      <aside className={`sidebar ${open ? 'open' : ''}`} onClick={() => setOpen(false)}>
        <div className="brand"><BrandMark /><div><div className="t1">eRTMAC NWIS</div><div className="t2">Nearby Wells Intelligence</div></div></div>
        <nav className="nav col gap-4">
          {links.map((l) => (
            <NavLink key={l.to} to={l.to} end={l.end}><l.icon size={17} />{l.label}{l.count ? <span className="count">{l.count}</span> : null}</NavLink>
          ))}
        </nav>
        <div className="bottom">
          <button className="btn ghost sm" onClick={() => nav('/field')}><Smartphone size={15} />Field view</button>
          <div className="card tight row" style={{ padding: 10 }}>
            <div className="grow">
              <div style={{ fontWeight: 500 }} className="ellipsis">{user.full_name}</div>
              <div className="tiny muted">{user.role}</div>
            </div>
            <ThemeButton className="icon-btn plain" />
            <button className="icon-btn plain" onClick={logout} aria-label="Log out" title="Log out"><LogOut size={16} /></button>
          </div>
        </div>
      </aside>
      <main className="main">
        <div className="topbar">
          <div className="row">
            <button className="icon-btn mobile-nav-btn" onClick={() => setOpen(true)} aria-label="Menu"><Menu size={18} /></button>
            <SampleBadge text={IS_DEMO ? 'Sample data · browser demo' : 'Sample data'} />
          </div>
          <div className="row small muted"><span className={`live-dot ${connected ? '' : 'off'}`} />{connected ? 'Live' : 'Offline'}</div>
        </div>
        <Outlet />
      </main>
      <Toasts />
    </div>
  )
}

export function FieldLayout() {
  const { user } = useAuth()
  const tabs = [
    { to: '/field', end: true, icon: Home, label: 'Home' },
    { to: '/field/map', icon: Compass, label: 'Map' },
    { to: '/field/wells', icon: BookOpen, label: 'Wells' },
    { to: '/field/me', icon: User, label: 'Me' },
  ]
  return (
    <div className="field-shell">
      <Outlet />
      <nav className="tabbar">
        {tabs.map((t) => <NavLink key={t.to} to={t.to} end={t.end} aria-label={t.label} title={t.label}><t.icon size={19} /></NavLink>)}
        {user.role !== 'driller' && <NavLink to="/office" aria-label="Office view" title="Office view"><Monitor size={19} /></NavLink>}
      </nav>
      <Toasts />
    </div>
  )
}
