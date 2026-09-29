import { Pause, Play } from 'lucide-react'
import { Fragment, useEffect, useMemo, useState } from 'react'
import { Polyline } from 'react-leaflet'
import { api } from '../api/client'
import { BaseMap, DrillerMarker, FitBounds, Legend, ZoneCircle, ZonesLayer } from '../components/MapBits'
import { Empty, ErrorBox, Loading, SectionTitle, StatusPill } from '../components/ui'
import { useLive } from '../context/LiveContext'
import { fmt, TRACK_STATUS, useApi } from '../lib/util'

export default function TrackingPage() {
  const live = useApi('/api/tracking/live')
  const layers = useApi('/api/map/layers')
  const breaches = useApi('/api/tracking/breaches', { limit: 100 })
  const { positions, breaches: liveBreaches } = useLive()
  const [trails, setTrails] = useState({})
  const [focus, setFocus] = useState(null)
  const [busy, setBusy] = useState(null)

  // Build a short trail from live positions.
  useEffect(() => {
    setTrails((t) => {
      const next = { ...t }
      Object.values(positions).forEach((p) => {
        const arr = next[p.user_id] || (live.data?.find((d) => d.user_id === p.user_id)?.trail || [])
        const last = arr[arr.length - 1]
        if (!last || last[0] !== p.lat || last[1] !== p.lon) next[p.user_id] = [...arr, [p.lat, p.lon]].slice(-80)
      })
      return next
    })
  }, [positions]) // eslint-disable-line

  const drillers = useMemo(() => (live.data || []).map((d) => {
    const p = positions[d.user_id]
    return p ? { ...d, lat: p.lat, lon: p.lon, tracking_status: p.status, check: p.check, last_seen_at: p.at } : d
  }), [live.data, positions])

  if (live.loading || layers.loading) return <Loading />
  if (live.error) return <ErrorBox error={live.error} />

  const sim = async (d, start) => {
    setBusy(d.user_id)
    if (start) setFocus(d.user_id)
    try {
      await api(`/api/tracking/simulator/${start ? 'start' : 'stop'}`, { method: 'POST', body: { user_id: d.user_id } })
      live.setData((rows) => rows.map((r) => (r.user_id === d.user_id ? { ...r, simulator_running: start } : r)))
    } finally { setBusy(null) }
  }
  const ack = async (b) => { await api(`/api/tracking/breaches/${b.id}/ack`, { method: 'POST' }); breaches.reload() }
  const allBreaches = [...liveBreaches, ...(breaches.data || [])].filter((a, i, arr) => arr.findIndex((b) => b.id === a.id) === i)
  const focusD = drillers.find((d) => d.user_id === focus)
  const points = focusD?.zone ? focusD.zone.polygon : drillers.filter((d) => d.lat).map((d) => [d.lat, d.lon])

  return (
    <div className="col gap-20">
      <SectionTitle eyebrow="Live geotag tracking" title="Where the drilling crews are"
        sub="Positions update live over a websocket. The dashed circle is the allowed zone: rig reach plus a safety margin around the approved site. Use the simulator to move a demo driller." />
      <div className="grid g-map">
        <div className="map-page" style={{ height: 560 }}>
          <BaseMap>
            {layers.data && <ZonesLayer zones={layers.data.zones.filter((z) => z.zone_type !== 'licensed_block')} />}
            {drillers.map((d) => (
              <Fragment key={d.user_id}>
                <ZoneCircle zone={d.zone} breach={d.tracking_status === 'OUTSIDE' || d.tracking_status === 'ILLEGAL_ZONE'} />
                {(trails[d.user_id] || d.trail)?.length > 1 && <Polyline positions={trails[d.user_id] || d.trail} pathOptions={{ color: '#2a78d6', weight: 2, opacity: 0.6 }} />}
                <DrillerMarker lat={d.lat} lon={d.lon} name={d.name} status={d.tracking_status} onClick={() => setFocus(d.user_id)} />
              </Fragment>
            ))}
            <FitBounds points={points} />
          </BaseMap>
          <div className="map-overlay bl">
            <Legend items={[{ label: 'Driller (live)', color: '#2a78d6' }, { label: 'Driller in breach', color: '#d03b3b' },
              { label: 'Allowed zone', color: '#2a78d6', shape: 'area' }, { label: 'Planned bottom of hole', color: '#9a6b2f' },
              { label: 'No-go zone', color: '#d03b3b', shape: 'area' }]} />
          </div>
        </div>
        <div className="col gap-16">
          {drillers.length === 0 && <Empty>No drillers with a working area yet.</Empty>}
          {drillers.map((d) => {
            const st = TRACK_STATUS[d.tracking_status] || { label: 'Not reported yet', cls: '' }
            return (
              <div key={d.user_id} className="card" style={{ padding: 16, outline: focus === d.user_id ? '2px solid var(--accent)' : 'none' }} onClick={() => setFocus(d.user_id)}>
                <div className="row between top">
                  <div><b>{d.name}</b><div className="small muted">{d.company}</div></div>
                  <StatusPill tone={st.cls} label={st.label} />
                </div>
                {d.zone && (
                  <div className="small ink2 mt-8">
                    Allowed radius <b>{fmt.m(d.zone.radius_m)}</b> ({fmt.m(d.zone.reach_m)} rig reach + {fmt.m(d.zone.safety_margin_m)} margin, limited by {d.zone.limited_by})
                    {d.check && <> · now <b>{fmt.m(d.check.distance_m)}</b> from site</>}
                  </div>
                )}
                {d.zone?.warnings?.map((w) => <div key={w} className="small" style={{ color: 'var(--serious-ink)' }}>⚠ {w}</div>)}
                <div className="row between mt-12">
                  <span className="tiny muted">{d.last_seen_at ? `Last update ${fmt.ago(d.last_seen_at)}` : 'No position yet'} · registration {d.status}</span>
                  <button className="btn xs" disabled={busy === d.user_id} onClick={(e) => { e.stopPropagation(); sim(d, !d.simulator_running) }}>
                    {d.simulator_running ? <><Pause size={12} />Stop simulator</> : <><Play size={12} />Start simulator</>}
                  </button>
                </div>
              </div>
            )
          })}
        </div>
      </div>
      <div className="card">
        <SectionTitle eyebrow="History" title="Zone event log" sub="Every time a driller leaves the allowed zone, enters a no-go zone or comes back, it is logged with time and coordinates." />
        <div className="table-wrap"><table className="table">
          <thead><tr><th>When</th><th>Driller</th><th>Event</th><th>Where</th><th>Distance / limit</th><th></th></tr></thead>
          <tbody>{allBreaches.map((b) => (
            <tr key={b.id}>
              <td className="small">{fmt.time(b.created_at)}</td><td>{b.name}</td>
              <td><StatusPill tone={b.is_breach ? 'critical' : b.event_type === 'RETURNED_TO_ZONE' ? 'good' : 'warn'} label={b.text} />{b.zone_name && <div className="tiny muted mt-4">{b.zone_name}</div>}</td>
              <td className="small num">{fmt.coord(b.lat, b.lon)}{b.simulated && <div className="tiny muted">simulated</div>}</td>
              <td className="small num">{fmt.m(b.distance_m)} / {fmt.m(b.radius_m)}</td>
              <td>{b.is_breach && !b.acknowledged && <button className="btn xs ghost" onClick={() => ack(b)}>Acknowledge</button>}{b.acknowledged && <span className="tiny muted">acknowledged</span>}</td>
            </tr>
          ))}</tbody>
        </table></div>
      </div>
    </div>
  )
}
