import { ChevronRight } from 'lucide-react'
import { useState } from 'react'
import { Link } from 'react-router-dom'
import { BrandMark, ThemeButton } from '../components/Layouts'
import { useAuth } from '../context/AuthContext'
import { Strata } from './Login'

export default function Register() {
  const { register } = useAuth()
  const [f, setF] = useState({ full_name: '', email: '', password: '', confirm: '' })
  const [error, setError] = useState(null)
  const [busy, setBusy] = useState(false)
  const set = (k) => (e) => setF({ ...f, [k]: e.target.value })

  const submit = async (e) => {
    e.preventDefault()
    if (f.password.length < 8) return setError('Password must be at least 8 characters.')
    if (f.password !== f.confirm) return setError('Passwords do not match.')
    setBusy(true); setError(null)
    try { await register(f.full_name, f.email, f.password) } catch (err) { setError(err.message) }
    setBusy(false)
  }

  return (
    <div className="auth-wrap">
      <div className="auth-art">
        <div className="row"><BrandMark /><div className="serif" style={{ fontSize: 20 }}>eRTMAC NWIS</div></div>
        <div>
          <div className="eyebrow" style={{ color: '#c9a56a' }}>Driller registration</div>
          <h1 style={{ fontSize: 40, marginTop: 10, color: '#f6efe0' }}>Register as head of drilling</h1>
          <ol style={{ color: '#d8ccb4', marginTop: 18, paddingLeft: 18, lineHeight: 1.9 }}>
            <li>Create your account</li><li>Add personal and company details</li><li>Upload licence, permits and ID</li>
            <li>Declare your rigs and equipment</li><li>Set your working area</li><li>An admin reviews and approves</li>
          </ol>
        </div>
        <Strata />
      </div>
      <div className="auth-form">
        <form style={{ width: 'min(420px, 100%)' }} onSubmit={submit}>
          <div className="row between"><Link to="/login" className="small muted">← Back to log in</Link><ThemeButton /></div>
          <h1 className="mt-24">Create account</h1>
          <p className="muted mt-4">Step 1 of 6. You can finish the rest after logging in.</p>
          <div className="col gap-16 mt-24">
            <div className="field"><label>Full name</label><input className="input" value={f.full_name} onChange={set('full_name')} required /></div>
            <div className="field"><label>Email</label><input className="input" type="email" value={f.email} onChange={set('email')} required /></div>
            <div className="field"><label>Password (8+ characters)</label><input className="input" type="password" value={f.password} onChange={set('password')} required /></div>
            <div className="field"><label>Confirm password</label><input className="input" type="password" value={f.confirm} onChange={set('confirm')} required /></div>
            {error && <div className="error">{error}</div>}
            <button className="btn block" disabled={busy}>{busy ? 'Creating…' : 'Create account'}<ChevronRight size={16} /></button>
          </div>
        </form>
      </div>
    </div>
  )
}
