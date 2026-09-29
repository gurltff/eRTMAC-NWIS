import { ChevronRight, Lightbulb } from 'lucide-react'
import { CartesianGrid, Legend as RLegend, Line, LineChart, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { EVENT_META, fmt } from '../lib/util'
import { SeverityPill } from './ui'

/** The "book" card: an active well with bit-depth progress (mirrors the reading card in the design). */
export function ActiveWellCard({ well, analysis, depth, onOpen, compact, openLabel = 'Open offset analysis' }) {
  const current = depth ?? well.current_depth_m
  const pct = well.planned_td_m ? Math.min(100, (current / well.planned_td_m) * 100) : 0
  const tops = analysis?.well?.formation_tops || well.formation_tops || []
  const idx = tops.findIndex((t) => t.top_m <= current && current < t.bottom_m)
  const fm = tops[idx]
  const next = analysis?.next_zone
  return (
    <div className="card">
      <div className="book-card">
        <div className="book-cover">
          <div className="tiny" style={{ opacity: 0.7, letterSpacing: '.12em' }}>ACTIVE WELL</div>
          <div className="t">{well.name}</div>
          <div className="tiny" style={{ opacity: 0.8 }}>{well.field || well.operator}</div>
        </div>
        <div className="grow col" style={{ gap: 6 }}>
          <h3 style={{ fontSize: 19 }}>{fm ? fm.name : 'Drilling'}</h3>
          <div className="small muted">{well.operator}</div>
          <div className="mt-8">
            <div className="progress"><span style={{ width: `${pct}%` }} /></div>
            <div className="row between tiny muted mt-4 num"><span>{fmt.m(current)}</span><span>{Math.round(pct)}%</span></div>
          </div>
          <div className="small ink2">
            {next ? <>Next risk zone in <b>{fmt.m(Math.max(0, next.distance_ahead_m))}</b></> : 'No offset problems ahead'}
          </div>
        </div>
      </div>
      {compact && (
        <div className="row between tiny muted mt-12" style={{ borderTop: '1px solid var(--line)', paddingTop: 10 }}>
          <span className="num">{fmt.m(current)}</span>
          <span>{fm ? `Formation ${idx + 1} of ${tops.length}` : ''}</span>
          <span>{well.planned_td_m ? `${fmt.m(well.planned_td_m - current)} to TD` : ''}</span>
        </div>
      )}
      {onOpen && <button className="btn block mt-16" onClick={onOpen}>{openLabel}<ChevronRight size={16} /></button>}
    </div>
  )
}

export function AlertCard({ a }) {
  return (
    <div className="card" style={{ padding: 18, borderLeft: `4px solid ${a.severity === 'high' ? 'var(--critical)' : a.severity === 'medium' ? 'var(--serious)' : 'var(--warn)'}` }}>
      <div className="row between top">
        <div className="eyebrow">{a.state === 'IN_ZONE' ? 'In the risk zone now' : `${fmt.m(a.distance_ahead_m)} ahead`} · {a.method}</div>
        <SeverityPill severity={a.severity} />
      </div>
      <h3 className="mt-8">{a.title}</h3>
      <p className="small muted mt-4">{a.message}</p>
      <p className="mt-12" style={{ fontFamily: 'var(--serif)', fontSize: 16 }}><span className="mark">{a.recommendation}</span></p>
      {a.what_worked?.length > 0 && (
        <div className="mt-12">
          <div className="row gap-6 small" style={{ fontWeight: 500 }}><Lightbulb size={14} />What worked nearby</div>
          <ul className="small ink2" style={{ margin: '6px 0 0', paddingLeft: 18 }}>
            {a.what_worked.map((w, i) => <li key={i}><b>{w.well}</b> ({w.distance_km} km, {Math.round(w.depth_m)} m): {w.lesson || w.action}</li>)}
          </ul>
        </div>
      )}
    </div>
  )
}

const RISK_KEYS = ['MUD_LOSS', 'STUCK_PIPE', 'TORQUE_SPIKE', 'KICK', 'CEMENTING']

/** ML risk ahead of the bit: one line per problem type, depth on the x axis. */
export function RiskChart({ profile, height = 260 }) {
  if (!profile?.points?.length) return <div className="empty">No depth left to predict.</div>
  const data = profile.points.map((p) => ({ depth: p.depth_m, formation: p.formation, ...Object.fromEntries(RISK_KEYS.map((k) => [k, Math.round(p[k] * 100)])) }))
  return (
    <ResponsiveContainer width="100%" height={height}>
      <LineChart data={data} margin={{ top: 8, right: 12, bottom: 4, left: -12 }}>
        <CartesianGrid stroke="var(--grid)" vertical={false} />
        <XAxis dataKey="depth" tick={{ fontSize: 11, fill: 'var(--muted)' }} tickFormatter={(v) => `${v}`} stroke="var(--axis)" />
        <YAxis domain={[0, 100]} tick={{ fontSize: 11, fill: 'var(--muted)' }} unit="%" stroke="var(--axis)" />
        <Tooltip contentStyle={{ background: 'var(--card)', border: '1px solid var(--line-2)', borderRadius: 12, fontSize: 12 }}
          labelFormatter={(v, p) => `${v} m · ${p?.[0]?.payload?.formation || ''}`} formatter={(v, k) => [`${v}%`, EVENT_META[k]?.label || k]} />
        <RLegend formatter={(k) => <span style={{ color: 'var(--ink-2)', fontSize: 12 }}>{EVENT_META[k]?.label}</span>} iconType="plainline" />
        <ReferenceLine y={50} stroke="var(--axis)" strokeDasharray="4 4" />
        {RISK_KEYS.map((k) => <Line key={k} type="monotone" dataKey={k} stroke={EVENT_META[k].color} strokeWidth={2} dot={false} activeDot={{ r: 4 }} />)}
      </LineChart>
    </ResponsiveContainer>
  )
}
