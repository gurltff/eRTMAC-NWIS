import { ChevronRight } from 'lucide-react'
import { useState } from 'react'
import { Link } from 'react-router-dom'
import { IS_DEMO } from '../api/client'
import { BrandMark, ThemeButton } from '../components/Layouts'
import { SampleBadge } from '../components/ui'
import { useAuth } from '../context/AuthContext'

const DEMO_USERS = [
  { email: 'admin@nwis.demo', password: 'Admin@123', label: 'Admin', note: 'Approvals, all dashboards' },
  { email: 'engineer@nwis.demo', password: 'Engineer@123', label: 'Drilling engineer', note: 'Office + field views' },
  { email: 'driller@nwis.demo', password: 'Driller@123', label: 'Driller (approved)', note: 'Live tracking, alerts' },
  { email: 'driller3@nwis.demo', password: 'Driller@123', label: 'Driller (under review)', note: 'Registration status' },
]

// Formation stripes, a nod to a well log.
export function Strata() {
  const bands = [['#f3e6b5', 18], ['#c9a56a', 26], ['#8f6b3f', 14], ['#5a4633', 30], ['#e0c68d', 22], ['#3b332c', 16], ['#a7824f', 24]]
  let y = 0
  return (
    <svg viewBox="0 0 400 150" preserveAspectRatio="none" style={{ width: '100%', height: 150, opacity: 0.9 }} aria-hidden>
      {bands.map(([c, h], i) => { const r = <path key={i} d={`M0 ${y} C 120 ${y + 8}, 260 ${y - 8}, 400 ${y + 4} L400 ${y + h + 4} C 260 ${y + h - 8}, 120 ${y + h + 8}, 0 ${y + h} Z`} fill={c} />; y += h; return r })}
      <line x1="232" y1="0" x2="232" y2="150" stroke="#f3e6b5" strokeWidth="2" strokeDasharray="4 4" />
      <circle cx="232" cy="98" r="6" fill="#d03b3b" stroke="#f3e6b5" strokeWidth="2" />
    </svg>
  )
}

export default function Login() {
  const { login } = useAuth()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState(null)
  const [busy, setBusy] = useState(false)

  const submit = async (e, creds) => {
    e?.preventDefault()
    setBusy(true); setError(null)
    try { await login(creds?.email || email, creds?.password || password) } catch (err) { setError(err.message) }
    setBusy(false)
  }

  return (
    <div className="auth-wrap">
      <div className="auth-art">
        <div className="row"><BrandMark /><div><div className="serif" style={{ fontSize: 20 }}>eRTMAC NWIS</div><div className="tiny" style={{ opacity: 0.7 }}>Oil India Limited · Problem statement 26121</div></div></div>
        <div>
          <div className="eyebrow" style={{ color: '#c9a56a' }}>Nearby Wells Intelligence System</div>
          <h1 style={{ fontSize: 44, marginTop: 10, color: '#f6efe0' }}>Every nearby well,<br />before you drill.</h1>
          <p style={{ marginTop: 16, maxWidth: 440, color: '#d8ccb4', fontSize: 15 }}>
            See offset wells on a map, learn from their problems, and get a warning before your bit reaches the depth where they had trouble.
          </p>
        </div>
        <Strata />
      </div>
      <div className="auth-form">
        <div style={{ width: 'min(420px, 100%)' }}>
          <div className="row between"><SampleBadge text={IS_DEMO ? 'Browser demo · sample data' : 'Prototype · sample data'} /><ThemeButton /></div>
          <h1 className="mt-24">Log in</h1>
          <p className="muted mt-4">Use your account, or pick a demo user below.</p>
          <form className="col gap-16 mt-24" onSubmit={submit}>
            <div className="field"><label>Email</label><input className="input" type="email" value={email} onChange={(e) => setEmail(e.target.value)} autoComplete="username" required /></div>
            <div className="field"><label>Password</label><input className="input" type="password" value={password} onChange={(e) => setPassword(e.target.value)} autoComplete="current-password" required /></div>
            {error && <div className="error">{error}</div>}
            <button className="btn block" disabled={busy}>{busy ? 'Logging in…' : 'Log in'}<ChevronRight size={16} /></button>
          </form>
          <p className="small muted mt-16">Head of drilling and new here? <Link to="/register">Create an account</Link></p>
          <div className="card mt-24" style={{ padding: 14 }}>
            <div className="eyebrow" style={{ marginBottom: 8 }}>Demo accounts</div>
            <div className="list">
              {DEMO_USERS.map((u) => (
                <button key={u.email} className="item row between" style={{ border: 0, background: 'none', cursor: 'pointer', textAlign: 'left', padding: '10px 0', borderBottom: '1px solid var(--line)' }}
                  onClick={(e) => submit(e, u)} disabled={busy}>
                  <div><div style={{ fontWeight: 500 }}>{u.label}</div><div className="tiny muted">{u.email} · {u.password} · {u.note}</div></div>
                  <ChevronRight size={16} className="muted" />
                </button>
              ))}
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
