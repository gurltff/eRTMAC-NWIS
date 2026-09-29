import { useNavigate } from 'react-router-dom'
import { Bar, BarChart, CartesianGrid, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { ActiveWellCard } from '../components/WellBits'
import { Empty, ErrorBox, Loading, SectionTitle, SeverityPill, Stat, StatusPill } from '../components/ui'
import { useLive } from '../context/LiveContext'
import { EVENT_META, EVENT_TYPES, fmt, useApi } from '../lib/util'

const tip = { background: 'var(--card)', border: '1px solid var(--line-2)', borderRadius: 12, fontSize: 12, color: 'var(--ink)' }
const axis = { fontSize: 11, fill: 'var(--muted)' }

function ActiveWell({ well }) {
  const nav = useNavigate()
  const { depths } = useLive()
  const a = useApi(`/api/wells/${well.id}/offsets`, { radius_km: 10 })
  return <ActiveWellCard well={well} analysis={a.data} depth={depths[well.id]} onOpen={() => nav(`/office/offset?well=${well.id}`)} />
}

export default function Overview() {
  const o = useApi('/api/analytics/overview')
  const active = useApi('/api/wells', { active: true })
  const alerts = useApi('/api/alerts', { open_only: true })
  const breaches = useApi('/api/tracking/breaches', { limit: 8 })
  const live = useLive()
  if (o.loading) return <Loading />
  if (o.error) return <ErrorBox error={o.error} />
  const d = o.data
  const k = d.kpis
  const allAlerts = [...live.wellAlerts, ...(alerts.data || [])].filter((a, i, arr) => arr.findIndex((b) => b.id === a.id) === i)
  const allBreaches = [...live.breaches, ...(breaches.data || [])].filter((a, i, arr) => arr.findIndex((b) => b.id === a.id) === i).slice(0, 8)
  const byType = EVENT_TYPES.map((t) => ({ type: t, label: EVENT_META[t].label, count: d.events_by_type[t] || 0 }))

  return (
    <div className="col gap-20">
      <SectionTitle eyebrow="Office view" title="Operations overview" sub="All wells, drillers, alerts and trends in one place." />
      <div className="grid g4">
        <Stat label="Wells in database" value={k.wells} sub={`${k.active_wells} drilling now`} />
        <Stat label="Recorded problems" value={k.events} sub={`${fmt.n(k.npt_hours)} hours of lost time`} />
        <Stat label="Open well alerts" value={Math.max(k.open_alerts, allAlerts.filter((a) => !a.acknowledged).length)} tone={k.open_alerts ? 'serious' : undefined} sub="from the offset alert engine" />
        <Stat label="Zone breaches (7 days)" value={k.breaches_7d + live.breaches.filter((b) => b.is_breach).length} tone={k.breaches_7d ? 'critical' : undefined}
          sub={`${k.pending_approvals} registration(s) waiting`} />
      </div>

      <div>
        <div className="row between" style={{ marginBottom: 12 }}><h2>Drilling now</h2></div>
        {active.data ? <div className="grid g3">{active.data.map((w) => <ActiveWell key={w.id} well={w} />)}</div> : <Loading />}
      </div>

      <div className="grid g2">
        <div className="card">
          <SectionTitle eyebrow="Alerts" title="Latest well alerts" />
          {allAlerts.length ? (
            <div className="list">{allAlerts.slice(0, 6).map((a) => (
              <div key={a.id} className="item">
                <div className="row between"><b>{a.well_name}</b><SeverityPill severity={a.severity} /></div>
                <div className="small ink2 mt-4">{a.title}</div>
                <div className="tiny muted mt-4">Raised at {fmt.m(a.depth_at_alert_m)} · {fmt.ago(a.created_at)}</div>
              </div>
            ))}</div>
          ) : <Empty>No alerts yet. They appear as the active wells get close to known problem zones.</Empty>}
        </div>
        <div className="card">
          <SectionTitle eyebrow="Live tracking" title="Latest zone events" />
          {allBreaches.length ? (
            <div className="list">{allBreaches.map((b) => (
              <div key={b.id} className="item row between top">
                <div><b>{b.name}</b><div className="small ink2">{b.text}{b.zone_name ? ` · ${b.zone_name}` : ''}</div>
                  <div className="tiny muted">{fmt.time(b.created_at)} · {fmt.coord(b.lat, b.lon)}{b.simulated ? ' · simulated' : ''}</div></div>
                <StatusPill tone={b.is_breach ? 'critical' : b.event_type === 'RETURNED_TO_ZONE' ? 'good' : 'warn'} label={b.is_breach ? 'Breach' : b.event_type === 'RETURNED_TO_ZONE' ? 'Back' : 'Warning'} />
              </div>
            ))}</div>
          ) : <Empty>No zone events.</Empty>}
        </div>
      </div>

      <div className="grid g2">
        <div className="card">
          <SectionTitle eyebrow="Event trends" title="Problems by period" sub="Events from daily drilling and completion reports, grouped in 5-year periods." />
          <ResponsiveContainer width="100%" height={280}>
            <BarChart data={d.events_by_period} margin={{ left: -18, right: 8 }}>
              <CartesianGrid stroke="var(--grid)" vertical={false} />
              <XAxis dataKey="period" tick={axis} stroke="var(--axis)" interval={0} angle={-30} textAnchor="end" height={50} />
              <YAxis tick={axis} stroke="var(--axis)" allowDecimals={false} />
              <Tooltip contentStyle={tip} cursor={{ fill: 'var(--card-2)' }} formatter={(v, key) => [v, EVENT_META[key]?.label]} />
              <Legend formatter={(key) => <span style={{ color: 'var(--ink-2)', fontSize: 12 }}>{EVENT_META[key]?.label}</span>} />
              {EVENT_TYPES.map((t, i) => <Bar key={t} dataKey={t} stackId="a" fill={EVENT_META[t].color} stroke="var(--card)" strokeWidth={1}
                radius={i === EVENT_TYPES.length - 1 ? [4, 4, 0, 0] : 0} />)}
            </BarChart>
          </ResponsiveContainer>
        </div>
        <div className="card">
          <SectionTitle eyebrow="Risk by formation" title="Lost time by formation" sub="Hours of non-productive time recorded in each formation." />
          <ResponsiveContainer width="100%" height={280}>
            <BarChart data={d.npt_by_formation} layout="vertical" margin={{ left: 40, right: 16 }}>
              <CartesianGrid stroke="var(--grid)" horizontal={false} />
              <XAxis type="number" tick={axis} stroke="var(--axis)" />
              <YAxis type="category" dataKey="formation" tick={axis} stroke="var(--axis)" width={110} />
              <Tooltip contentStyle={tip} cursor={{ fill: 'var(--card-2)' }} formatter={(v) => [`${v} h`, 'Lost time']} />
              <Bar dataKey="npt_hours" fill="var(--s1)" radius={[0, 4, 4, 0]} barSize={14} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      </div>

      <div className="grid g2">
        <div className="card">
          <SectionTitle eyebrow="All problems" title="Problems by type" />
          <ResponsiveContainer width="100%" height={240}>
            <BarChart data={byType} margin={{ left: -18, right: 8 }}>
              <CartesianGrid stroke="var(--grid)" vertical={false} />
              <XAxis dataKey="label" tick={axis} stroke="var(--axis)" interval={0} angle={-20} textAnchor="end" height={50} />
              <YAxis tick={axis} stroke="var(--axis)" />
              <Tooltip contentStyle={tip} cursor={{ fill: 'var(--card-2)' }} />
              <Bar dataKey="count" name="Events" radius={[4, 4, 0, 0]} barSize={26} fill="var(--s1)" />
            </BarChart>
          </ResponsiveContainer>
        </div>
        <div className="card">
          <SectionTitle eyebrow="Field risk" title="Problems per well, by field" />
          <div className="table-wrap" style={{ maxHeight: 260, overflowY: 'auto' }}>
            <table className="table">
              <thead><tr><th>Field</th><th>Wells</th><th>Problems</th><th>Per well</th><th>High severity</th></tr></thead>
              <tbody>{d.field_risk.map((f) => (
                <tr key={f.field}><td>{f.field}</td><td className="num">{f.wells}</td><td className="num">{f.events}</td>
                  <td className="num"><b>{f.events_per_well}</b></td><td className="num">{f.high}</td></tr>
              ))}</tbody>
            </table>
          </div>
        </div>
      </div>
    </div>
  )
}
