import { LogOut, Monitor } from 'lucide-react'
import { useNavigate } from 'react-router-dom'
import { Loading, SampleBadge, StatusPill } from '../../components/ui'
import { useAuth } from '../../context/AuthContext'
import { useTheme } from '../../context/ThemeContext'
import { fmt, useApi } from '../../lib/util'
import { DOC_STATUS, REG_STATUS } from '../DrillersPage'

export default function FieldMe() {
  const { user, logout } = useAuth()
  const { pref, setPref } = useTheme()
  const nav = useNavigate()
  const me = useApi(user.role === 'driller' ? '/api/driller/me' : null)
  const breaches = useApi(user.role === 'driller' ? '/api/driller/breaches' : null)
  return (
    <div className="col gap-16">
      <h1 style={{ fontSize: 28 }}>Me</h1>
      <div className="card">
        <div className="eyebrow">{user.role}</div>
        <h2 className="mt-4">{user.full_name}</h2>
        <div className="muted">{user.email}</div>
        <div className="mt-12"><SampleBadge /></div>
      </div>
      <div className="card">
        <div className="eyebrow" style={{ marginBottom: 8 }}>Appearance</div>
        <div className="seg">{['system', 'light', 'dark'].map((t) => <button key={t} className={pref === t ? 'on' : ''} onClick={() => setPref(t)}>{fmt.title(t)}</button>)}</div>
      </div>
      {user.role === 'driller' && (me.loading ? <Loading /> : me.data && (
        <>
          <div className="card">
            <div className="row between"><div className="eyebrow">Registration</div><StatusPill tone={REG_STATUS[me.data.status].cls} label={REG_STATUS[me.data.status].label} /></div>
            <div className="list mt-8">{me.data.documents.map((d) => (
              <div key={d.id} className="item row between"><span className="small">{d.label}</span><StatusPill tone={DOC_STATUS[d.status].cls} label={DOC_STATUS[d.status].label} /></div>
            ))}</div>
            <button className="btn ghost sm mt-12" onClick={() => nav('/driller')}>Open registration</button>
          </div>
          <div className="card">
            <div className="eyebrow" style={{ marginBottom: 8 }}>My zone history</div>
            {breaches.data?.length ? <div className="list">{breaches.data.slice(0, 10).map((b) => (
              <div key={b.id} className="item"><div className="row between"><span className="small"><b>{b.text}</b></span>
                <StatusPill tone={b.is_breach ? 'critical' : b.event_type === 'RETURNED_TO_ZONE' ? 'good' : 'warn'} label={b.is_breach ? 'Breach' : 'Info'} /></div>
                <div className="tiny muted">{fmt.time(b.created_at)} · {fmt.coord(b.lat, b.lon)}{b.zone_name ? ` · ${b.zone_name}` : ''}</div></div>
            ))}</div> : <p className="small muted">No zone events.</p>}
          </div>
        </>
      ))}
      {user.role !== 'driller' && <button className="btn ghost" onClick={() => nav('/office')}><Monitor size={15} />Office view</button>}
      <button className="btn line" onClick={logout}><LogOut size={15} />Log out</button>
    </div>
  )
}
