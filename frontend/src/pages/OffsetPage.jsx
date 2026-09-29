import { Search } from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import { Circle } from 'react-leaflet'
import { useSearchParams } from 'react-router-dom'
import { api } from '../api/client'
import Correlation, { FORMATION_FILL } from '../components/Correlation'
import { BaseMap, FitBounds, WellsLayer } from '../components/MapBits'
import { ActiveWellCard, AlertCard, RiskChart } from '../components/WellBits'
import { Empty, ErrorBox, EventTag, Loading, SectionTitle, SeverityPill } from '../components/ui'
import { useAuth } from '../context/AuthContext'
import { useLive } from '../context/LiveContext'
import { EVENT_META, EVENT_TYPES, fmt, useApi } from '../lib/util'

export function EventsTable({ events, compact }) {
  const [q, setQ] = useState('')
  const [types, setTypes] = useState(new Set())
  const [open, setOpen] = useState(null)
  const rows = useMemo(() => events.filter((e) => (!types.size || types.has(e.event_type)) &&
    (!q || `${e.description} ${e.cause} ${e.action_taken} ${e.lesson} ${e.formation} ${e.well_name}`.toLowerCase().includes(q.toLowerCase()))), [events, q, types])
  const toggle = (t) => { const s = new Set(types); s.has(t) ? s.delete(t) : s.add(t); setTypes(s) }
  return (
    <div>
      <div className="row wrap gap-6" style={{ marginBottom: 12 }}>
        <div className="row grow" style={{ minWidth: 200, position: 'relative' }}>
          <Search size={15} style={{ position: 'absolute', left: 12 }} className="muted" />
          <input className="input" style={{ paddingLeft: 34 }} placeholder="Search problems, causes, fixes…" value={q} onChange={(e) => setQ(e.target.value)} />
        </div>
        {EVENT_TYPES.map((t) => (
          <button key={t} className={`chip ${types.has(t) ? 'on' : ''}`} onClick={() => toggle(t)} style={{ boxShadow: 'none' }}>
            <span className="dot" style={{ background: EVENT_META[t].color }} />{EVENT_META[t].label}
          </button>
        ))}
      </div>
      <div className="small muted" style={{ marginBottom: 6 }}>{rows.length} of {events.length} events</div>
      <div className="table-wrap">
        <table className="table">
          <thead><tr><th>Well</th><th>Problem</th><th>Depth</th><th>Formation</th>{!compact && <th>Cause</th>}<th>Severity</th></tr></thead>
          <tbody>
            {rows.slice(0, 300).map((e) => (
              <FragmentRow key={e.id} e={e} compact={compact} open={open === e.id} onToggle={() => setOpen(open === e.id ? null : e.id)} />
            ))}
          </tbody>
        </table>
        {!rows.length && <Empty>No events match.</Empty>}
      </div>
    </div>
  )
}

function FragmentRow({ e, compact, open, onToggle }) {
  return (
    <>
      <tr onClick={onToggle} style={{ cursor: 'pointer' }}>
        <td className="nowrap"><b>{e.well_name}</b>{e.distance_km !== null && e.distance_km !== undefined && <div className="tiny muted">{e.distance_km === 0 ? 'this well' : `${e.distance_km} km`}</div>}</td>
        <td><EventTag type={e.event_type} /></td>
        <td className="num">{fmt.m(e.depth_m)}</td>
        <td>{e.formation}</td>
        {!compact && <td className="small ink2">{e.cause}</td>}
        <td><SeverityPill severity={e.severity} /></td>
      </tr>
      {open && (
        <tr><td colSpan={compact ? 5 : 6} style={{ background: 'var(--card-2)' }}>
          <div className="col gap-6 small">
            <div>{e.description}</div>
            {e.cause && <div><b>Cause:</b> {e.cause}</div>}
            {e.action_taken && <div><b>What was done:</b> {e.action_taken}</div>}
            {e.lesson && <div><b>Lesson:</b> <span className="mark">{e.lesson}</span></div>}
            <div className="muted">{e.event_date} · {e.npt_hours ? `${e.npt_hours} h lost · ` : ''}{e.source}</div>
          </div>
        </td></tr>
      )}
    </>
  )
}

export default function OffsetPage() {
  const { user } = useAuth()
  const { depths, subscribe } = useLive()
  const [params, setParams] = useSearchParams()
  const wells = useApi('/api/wells')
  const [radius, setRadius] = useState(10)
  const wellId = Number(params.get('well')) || wells.data?.find((w) => w.is_active)?.id
  const analysis = useApi(wellId ? `/api/wells/${wellId}/offsets` : null, { radius_km: radius })
  const corr = useApi(wellId ? `/api/wells/${wellId}/correlation` : null, { radius_km: radius })
  const risk = useApi(wellId ? `/api/wells/${wellId}/risk-profile` : null)
  const events = useApi(wellId && analysis.data ? '/api/events' : null, analysis.data ? { lat: analysis.data.well.lat, lon: analysis.data.well.lon, radius_km: radius, limit: 1000 } : null)
  const [depthDraft, setDepthDraft] = useState(null)

  // Re-run the analysis when the live depth of this well changes (every ~25 m).
  const liveDepth = depths[wellId]
  const bucket = liveDepth ? Math.floor(liveDepth / 25) : null
  useEffect(() => { if (bucket !== null) { analysis.reload(); corr.reload() } }, [bucket]) // eslint-disable-line
  useEffect(() => subscribe((m) => { if (m.type === 'well_alert' && m.well_id === wellId) analysis.reload() }), [wellId]) // eslint-disable-line

  if (wells.loading) return <Loading />
  if (wells.error) return <ErrorBox error={wells.error} />
  const well = wells.data.find((w) => w.id === wellId)
  const a = analysis.data
  const currentDepth = liveDepth ?? a?.current_depth_m ?? well?.current_depth_m ?? 0
  const offsetIds = new Set((a?.offset_wells || []).map((w) => w.id))

  const setDepth = async (d) => {
    await api(`/api/wells/${wellId}/depth`, { method: 'POST', body: { depth_m: d } })
    setDepthDraft(null); analysis.reload(); corr.reload(); risk.reload()
  }

  return (
    <div className="col gap-20">
      <SectionTitle eyebrow="Offset well intelligence" title="Learn from the wells around you"
        sub="Pick a well and a radius. Problems from nearby wells are matched to your well by formation and shown before you reach them." />
      <div className="card row wrap gap-16">
        <div className="field" style={{ minWidth: 220 }}>
          <label>Well</label>
          <select className="input" value={wellId || ''} onChange={(e) => setParams({ well: e.target.value })}>
            <optgroup label="Drilling now">{wells.data.filter((w) => w.is_active).map((w) => <option key={w.id} value={w.id}>{w.name} · {w.field}</option>)}</optgroup>
            <optgroup label="Other wells">{wells.data.filter((w) => !w.is_active).map((w) => <option key={w.id} value={w.id}>{w.name}</option>)}</optgroup>
          </select>
        </div>
        <div className="field grow" style={{ minWidth: 220 }}>
          <label>Radius: {radius} km {a && <span>· {a.offset_wells.length} offset wells</span>}</label>
          <input type="range" min={2} max={30} value={radius} onChange={(e) => setRadius(Number(e.target.value))} />
        </div>
        {well?.is_active && user.role !== 'driller' && (
          <div className="field" style={{ minWidth: 240 }}>
            <label>Demo: move the bit to {fmt.m(depthDraft ?? currentDepth)}</label>
            <div className="row">
              <input type="range" min={0} max={well.planned_td_m || 4000} step={10} value={depthDraft ?? currentDepth} onChange={(e) => setDepthDraft(Number(e.target.value))} />
              <button className="btn sm" disabled={depthDraft === null} onClick={() => setDepth(depthDraft)}>Set</button>
            </div>
          </div>
        )}
      </div>

      {analysis.error && <ErrorBox error={analysis.error} />}
      {!a ? <Loading /> : (
        <>
          <div className="grid g2">
            <div className="col gap-16">
              {well?.is_active ? <ActiveWellCard well={well} analysis={a} depth={currentDepth} compact /> : (
                <div className="card"><div className="eyebrow">Finished well</div><h2 className="mt-4">{well?.name}</h2>
                  <p className="muted mt-4">This well is not being drilled, so there is no live depth. The offset list and correlation still work.</p></div>
              )}
              {well?.is_active && (a.alerts.length ? a.alerts.map((al) => <AlertCard key={al.key} a={al} />) : (
                <div className="card"><div className="eyebrow">Alerts</div><p className="mt-8 ink2">Nothing in the next {a.lookahead_m} m. {a.next_zone && <>Next: <b>{a.next_zone.title}</b> ({fmt.m(a.next_zone.distance_ahead_m)} ahead).</>}</p></div>
              ))}
            </div>
            <div className="card" style={{ padding: 0, overflow: 'hidden', minHeight: 380 }}>
              <BaseMap center={[a.well.lat, a.well.lon]} zoom={11}>
                <Circle center={[a.well.lat, a.well.lon]} radius={radius * 1000} pathOptions={{ color: '#9a6b2f', weight: 1.5, dashArray: '6 6', fillOpacity: 0.04 }} />
                <WellsLayer wells={wells.data.filter((w) => offsetIds.has(w.id) || w.id === wellId)} highlight={offsetIds}
                  onSelect={(w) => setParams({ well: w.id })} />
                <FitBounds points={[[a.well.lat, a.well.lon], ...wells.data.filter((w) => offsetIds.has(w.id)).map((w) => [w.lat, w.lon])]} />
              </BaseMap>
            </div>
          </div>

          {well?.is_active && a.upcoming.length > 0 && (
            <div className="card">
              <SectionTitle eyebrow="Ahead of the bit" title="Risk zones on the way down" />
              <div className="table-wrap"><table className="table">
                <thead><tr><th>From</th><th>Problem</th><th>Formation</th><th>Wells</th><th>Severity</th><th>Status</th></tr></thead>
                <tbody>{a.upcoming.map((u) => (
                  <tr key={u.key}><td className="num">{fmt.m(u.expected_from_m)}</td><td><EventTag type={u.event_type} /></td><td>{u.formation}</td>
                    <td className="small">{u.wells.join(', ')}</td><td><SeverityPill severity={u.severity} /></td>
                    <td className="small">{u.state === 'IN_ZONE' ? 'In zone now' : u.state === 'APPROACHING' ? 'Approaching' : `${fmt.m(u.distance_ahead_m)} ahead`}</td></tr>
                ))}</tbody>
              </table></div>
            </div>
          )}

          <div className="card">
            <SectionTitle eyebrow="Depth vs formation" title="Offset wells side by side"
              sub="Same formation, different depth: the coloured ribbons join each formation across wells. Dots are recorded problems; hover for details." />
            <div className="row wrap gap-6" style={{ marginBottom: 10 }}>
              {Object.entries(EVENT_META).map(([k, m]) => <span key={k} className="row gap-4 small ink2"><span className="dot" style={{ background: m.color }} />{m.label}</span>)}
            </div>
            {corr.data ? <Correlation columns={corr.data.columns} currentDepth={currentDepth} upcoming={well?.is_active ? a.upcoming : []} /> : <Loading />}
            <div className="row wrap gap-6 mt-8">{Object.entries(FORMATION_FILL).map(([k, c]) => <span key={k} className="row gap-4 tiny ink2"><span style={{ width: 12, height: 10, background: c, borderRadius: 2 }} />{k}</span>)}</div>
          </div>

          {well?.is_active && (
            <div className="card">
              <SectionTitle eyebrow="Predictive model" title="Chance of each problem ahead" sub={risk.data?.explanation} />
              {risk.data ? <RiskChart profile={risk.data} /> : <Loading text="Model is loading…" />}
            </div>
          )}

          <div className="card">
            <SectionTitle eyebrow="Knowledge base" title={`Problems within ${radius} km`} />
            {events.data ? <EventsTable events={events.data.items} /> : <Loading />}
          </div>
        </>
      )}
    </div>
  )
}
