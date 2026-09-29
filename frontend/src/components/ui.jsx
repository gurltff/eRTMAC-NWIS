import { AlertTriangle, CheckCircle2, Info, OctagonAlert, FlaskConical } from 'lucide-react'
import { EVENT_META, SEVERITY } from '../lib/util'

export function SampleBadge({ text = 'Sample data' }) {
  return <span className="sample-badge" title="This prototype runs on generated or approximate sample data"><FlaskConical size={12} />{text}</span>
}

export function Pill({ tone = '', children, icon }) {
  return <span className={`pill ${tone}`}>{icon}{children}</span>
}

export function SeverityPill({ severity }) {
  const s = SEVERITY[severity] || { label: severity, cls: '' }
  const Icon = severity === 'high' ? OctagonAlert : severity === 'medium' ? AlertTriangle : Info
  return <Pill tone={s.cls} icon={<Icon size={12} />}>{s.label}</Pill>
}

export function StatusPill({ tone, label }) {
  const Icon = tone === 'good' ? CheckCircle2 : tone === 'critical' ? OctagonAlert : tone === 'warn' || tone === 'serious' ? AlertTriangle : Info
  return <Pill tone={tone} icon={<Icon size={12} />}>{label}</Pill>
}

export function EventTag({ type }) {
  const m = EVENT_META[type] || { label: type, color: 'var(--muted)' }
  return <span className="pill" style={{ gap: 6 }}><span className="dot" style={{ background: m.color }} />{m.label}</span>
}

export function Loading({ text = 'Loading…' }) {
  return <div className="row muted" style={{ padding: 20 }}><div className="spinner" />{text}</div>
}

export function Empty({ children }) {
  return <div className="empty">{children}</div>
}

export function ErrorBox({ error }) {
  return error ? <div className="error">{error}</div> : null
}

export function Stat({ label, value, sub, tone }) {
  return (
    <div className="card tight" style={{ padding: 16 }}>
      <div className="eyebrow">{label}</div>
      <div className="serif" style={{ fontSize: 30, lineHeight: 1.15, marginTop: 6, color: tone ? `var(--${tone}-ink)` : undefined }}>{value}</div>
      {sub && <div className="small muted mt-4">{sub}</div>}
    </div>
  )
}

export function Meter({ value, tone }) {
  const color = tone || (value >= 60 ? 'var(--critical)' : value >= 35 ? 'var(--serious)' : 'var(--good)')
  return <div className="meter"><span style={{ width: `${Math.max(2, Math.min(100, value))}%`, background: color }} /></div>
}

export function SectionTitle({ eyebrow, title, right, sub }) {
  return (
    <div className="row between top" style={{ marginBottom: 14 }}>
      <div>
        {eyebrow && <div className="eyebrow" style={{ marginBottom: 4 }}>{eyebrow}</div>}
        <h2>{title}</h2>
        {sub && <p className="muted mt-4">{sub}</p>}
      </div>
      {right}
    </div>
  )
}
