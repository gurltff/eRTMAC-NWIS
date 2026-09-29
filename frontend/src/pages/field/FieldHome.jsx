import { LocateFixed, Pause, Play, Search } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api } from '../../api/client'
import { FORMATION_FILL } from '../../components/Correlation'
import { ThemeButton } from '../../components/Layouts'
import { ActiveWellCard, AlertCard } from '../../components/WellBits'
import { Loading, SampleBadge, StatusPill } from '../../components/ui'
import { useAuth } from '../../context/AuthContext'
import { useLive } from '../../context/LiveContext'
import { EVENT_META, fmt, TRACK_STATUS } from '../../lib/util'
import { useFieldWell } from './useFieldWell'

const DARK = new Set(['Girujan Clay', 'Barail', 'Kopili Shale'])

function greeting() {
  const h = new Date().getHours()
  return h < 12 ? 'Good morning' : h < 17 ? 'Good afternoon' : 'Good evening'
}

export function MyLocationCard({ me }) {
  const { positions, toast } = useLive()
  const [sim, setSim] = useState(false)
  const [gps, setGps] = useState(false)
  const watch = useRef(null)
  const pos = positions[me.user_id]
  const status = pos?.status || me.tracking_status
  const st = TRACK_STATUS[status] || { label: 'Waiting for position', cls: '' }

  useEffect(() => { api('/api/tracking/simulator/status').then((r) => setSim(!!r.running)).catch(() => {}) }, [])
  useEffect(() => () => { if (watch.current !== null) navigator.geolocation.clearWatch(watch.current) }, [])

  const toggleSim = async () => {
    if (gps) toggleGps()
    await api(`/api/tracking/simulator/${sim ? 'stop' : 'start'}`, { method: 'POST', body: {} })
    setSim(!sim)
  }
  const toggleGps = () => {
    if (gps) { navigator.geolocation.clearWatch(watch.current); watch.current = null; setGps(false); return }
    if (!navigator.geolocation) return toast({ tone: 'serious', title: 'GPS not available on this device' })
    watch.current = navigator.geolocation.watchPosition(
      (p) => api('/api/tracking/position', { method: 'POST', body: { lat: p.coords.latitude, lon: p.coords.longitude, accuracy_m: p.coords.accuracy } }).catch(() => {}),
      (e) => { toast({ tone: 'serious', title: 'Location permission needed', body: e.message }); setGps(false) },
      { enableHighAccuracy: true, maximumAge: 5000 })
    setGps(true)
  }

  const zone = me.zone
  const dist = pos?.check?.distance_m
  const pct = zone && dist !== undefined ? Math.min(100, (dist / zone.radius_m) * 100) : 0
  return (
    <div className="card">
      <div className="row between">
        <div className="eyebrow">My location</div>
        <StatusPill tone={st.cls} label={st.label} />
      </div>
      <h3 className="mt-8">{me.work_area_name || 'No working area yet'}</h3>
      {zone ? (
        <>
          <div className="small muted mt-4">{pos ? fmt.coord(pos.lat, pos.lon) : 'No position shared yet'}</div>
          <div className="mt-12">
            <div className="progress"><span style={{ width: `${pct}%`, background: pct > 100 || status === 'ILLEGAL_ZONE' ? 'var(--critical)' : pct > 90 ? 'var(--serious)' : 'var(--ink)' }} /></div>
            <div className="row between tiny muted mt-4 num"><span>{dist !== undefined ? `${fmt.m(dist)} from site` : '–'}</span><span>limit {fmt.m(zone.radius_m)}</span></div>
          </div>
          {status === 'ILLEGAL_ZONE' && pos?.check?.zone_name && <div className="error mt-12">You are inside {pos.check.zone_name}. Move out now.</div>}
          {status === 'OUTSIDE' && <div className="error mt-12">You are outside your allowed zone. Go back towards the site.</div>}
          <div className="row mt-16">
            <button className="btn grow" onClick={toggleGps}><LocateFixed size={15} />{gps ? 'Stop sharing GPS' : 'Share my GPS'}</button>
            <button className="btn ghost grow" onClick={toggleSim}>{sim ? <><Pause size={15} />Stop simulator</> : <><Play size={15} />Simulator</>}</button>
          </div>
          <p className="tiny muted mt-8">Simulator moves a fake driller around the site (fast-forward) so you can see alerts without real GPS.</p>
        </>
      ) : <p className="small muted mt-4">Set your working area in the registration to start tracking.</p>}
    </div>
  )
}

export default function FieldHome() {
  const { user } = useAuth()
  const nav = useNavigate()
  const f = useFieldWell()
  if (f.loading) return <Loading />
  const a = f.analysis
  const upcoming = (a?.upcoming || []).filter((u) => u.state !== 'PASSED').slice(0, 3)

  return (
    <div className="col gap-20">
      <div className="field-head">
        <div>
          <h1 style={{ fontSize: 30 }}>{greeting()}, {user.full_name.split(' ')[0]}</h1>
          <p className="muted mt-4">Pick up where you left off</p>
        </div>
        <div className="row gap-6"><ThemeButton /><button className="icon-btn" onClick={() => nav('/field/wells')} aria-label="Search wells"><Search size={17} /></button></div>
      </div>
      <div><SampleBadge /></div>

      {f.well && (
        <ActiveWellCard well={f.well} analysis={a} depth={f.depth} compact onOpen={() => nav('/field/wells')} openLabel="Continue drilling brief" />
      )}
      {f.active?.length > 1 && (
        <div className="seg" style={{ alignSelf: 'flex-start', flexWrap: 'wrap' }}>
          {f.active.map((w) => <button key={w.id} className={w.id === f.wellId ? 'on' : ''} onClick={() => f.choose(w.id)}>{w.name}</button>)}
        </div>
      )}

      {user.role === 'driller' && f.me && <MyLocationCard me={f.me} />}

      <div>
        <div className="row between" style={{ marginBottom: 12 }}><h3>Alerts</h3><span className="small muted">{a ? `${a.alerts.length} now` : ''}</span></div>
        {!a ? <Loading /> : a.alerts.length ? <div className="col gap-16">{a.alerts.map((al) => <AlertCard key={al.key} a={al} />)}</div>
          : <div className="card small ink2">All clear for the next {a.lookahead_m} m.</div>}
      </div>

      <div>
        <div className="row between" style={{ marginBottom: 12 }}><h3>Risk ahead</h3><button className="btn xs ghost" onClick={() => nav('/field/wells')}>View all</button></div>
        <div className="shelf">
          {upcoming.map((u) => (
            <button key={u.key} className="cover" onClick={() => nav('/field/wells')}
              style={{ background: FORMATION_FILL[u.formation] || 'var(--card-2)', color: DARK.has(u.formation) ? '#f6efe0' : '#2b2623' }}>
              <div className="tiny" style={{ opacity: 0.8 }}>{u.formation}</div>
              <div className="serif" style={{ fontSize: 17, lineHeight: 1.1 }}>{EVENT_META[u.event_type]?.label}</div>
              <div className="tiny num">{fmt.m(u.expected_from_m)} · {u.severity}</div>
            </button>
          ))}
        </div>
        {!upcoming.length && <div className="card small ink2">No known problem zones below the bit.</div>}
      </div>
    </div>
  )
}
