import { ChevronLeft, ChevronRight, List, Sparkles } from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { EventsTable } from '../OffsetPage'
import { Loading } from '../../components/ui'
import { EVENT_META, fmt, useApi } from '../../lib/util'
import { useFieldWell } from './useFieldWell'

const HAZARD_TEXT = {
  'Girujan Clay': 'Sticky, swelling clay. Expect tight hole, bit balling and stuck pipe on connections.',
  'Tipam Sandstone': 'Main reservoir sand. Partly depleted, so losses are common; gas-charged sands can kick.',
  Barail: 'Sand, shale and coal. Coal seams cave in; watch for pack-off, losses and gas.',
  'Kopili Shale': 'Overpressured shale across Upper Assam. The kick zone: weight up before entering.',
  'Sylhet Limestone': 'Fractured limestone. Severe and total losses are likely; cement jobs suffer.',
  Namsang: 'Loose sands with lignite. Seepage losses and erratic torque.',
  Dhekiajuli: 'Soft sands and clays. Mostly smooth drilling; watch for seepage losses.',
  Alluvium: 'Unconsolidated surface sands and gravels. Shallow losses and washouts.',
  Langpar: 'Sandstone and shale above basement. Occasional gas and cement problems.',
  Basement: 'Hard granite gneiss. Slow drilling and torque spikes.',
}

/** A "reader" for the formation column: one formation per page, like a chapter. */
export default function FieldWells() {
  const nav = useNavigate()
  const f = useFieldWell()
  const well = useApi(f.wellId ? `/api/wells/${f.wellId}` : null)
  const events = useApi(f.analysis ? '/api/events' : null, f.analysis ? { lat: f.analysis.well.lat, lon: f.analysis.well.lon, radius_km: 10, limit: 1000 } : null)
  const tops = well.data?.formation_tops || []
  const currentIdx = Math.max(0, tops.findIndex((t) => t.top_m <= (f.depth || 0) && (f.depth || 0) < t.bottom_m))
  const [page, setPage] = useState(null)
  const [showList, setShowList] = useState(false)
  useEffect(() => { if (page === null && tops.length) setPage(currentIdx) }, [tops.length]) // eslint-disable-line

  const fmEvents = useMemo(() => (events.data?.items || []).filter((e) => e.formation === tops[page]?.name && e.well_id !== f.wellId), [events.data, page, tops, f.wellId])
  if (f.loading || !well.data || page === null) return <Loading />
  const t = tops[page]
  const lessons = [...new Set(fmEvents.map((e) => e.lesson).filter(Boolean))]
  const counts = fmEvents.reduce((acc, e) => ({ ...acc, [e.event_type]: (acc[e.event_type] || 0) + 1 }), {})
  const pct = well.data.planned_td_m ? Math.round(((f.depth || 0) / well.data.planned_td_m) * 100) : 0
  const next = f.analysis?.next_zone

  return (
    <div className="col gap-16">
      <div className="row between">
        <button className="icon-btn" onClick={() => nav('/field')} aria-label="Back"><ChevronLeft size={18} /></button>
        <div className="row gap-6">
          <span className="serif" style={{ fontSize: 17 }}>{well.data.name}</span>
          <button className="icon-btn plain" onClick={() => setShowList(!showList)} aria-label="All events"><List size={18} /></button>
        </div>
      </div>

      {showList ? (
        <div className="card" style={{ padding: 14 }}>
          <h3 style={{ marginBottom: 10 }}>All problems within 10 km</h3>
          {events.data ? <EventsTable events={events.data.items} compact /> : <Loading />}
        </div>
      ) : (
        <div className="card" style={{ padding: '28px 22px', minHeight: 460 }}>
          <div className="eyebrow" style={{ textAlign: 'center' }}>Formation {page + 1} of {tops.length}{page === currentIdx ? ' · bit is here' : page < currentIdx ? ' · drilled' : ''}</div>
          <h1 style={{ textAlign: 'center', marginTop: 12, fontSize: 34 }}>{t.name}</h1>
          <div className="small muted" style={{ textAlign: 'center', marginTop: 6 }}>{fmt.m(t.top_m)} – {fmt.m(t.bottom_m)}</div>
          <hr className="rule" />
          {lessons[0] && <p style={{ fontFamily: 'var(--serif)', fontSize: 18, lineHeight: 1.6 }}><span className="mark">{lessons[0]}</span></p>}
          <p style={{ fontFamily: 'var(--serif)', fontSize: 17, lineHeight: 1.65, marginTop: 14 }}>{HAZARD_TEXT[t.name] || ''}</p>
          <p style={{ fontFamily: 'var(--serif)', fontSize: 17, lineHeight: 1.65, marginTop: 14 }}>
            {fmEvents.length
              ? <>Nearby wells had {Object.entries(counts).map(([k, n]) => `${n} ${EVENT_META[k]?.label.toLowerCase()}`).join(', ')} in this formation.</>
              : 'No problems were recorded in this formation in nearby wells.'}
          </p>
          {lessons.slice(1, 3).map((l) => <p key={l} style={{ fontFamily: 'var(--serif)', fontSize: 17, lineHeight: 1.65, marginTop: 14 }}>{l}</p>)}
          {fmEvents.length > 0 && (
            <div className="row" style={{ justifyContent: 'flex-end', marginTop: 16 }}>
              <button className="pill" style={{ border: 0, cursor: 'pointer' }} onClick={() => setShowList(true)}><Sparkles size={12} />{fmEvents.length} events</button>
            </div>
          )}
        </div>
      )}

      <div>
        <div className="progress"><span style={{ width: `${pct}%` }} /></div>
        <div className="row between tiny muted mt-8 num">
          <span>{pct}%</span><span>Formation {currentIdx + 1} of {tops.length}</span><span>{next ? `${fmt.m(Math.max(0, next.distance_ahead_m))} to next risk` : 'clear ahead'}</span>
        </div>
      </div>
      <div className="row" style={{ justifyContent: 'center' }}>
        <div className="seg">
          <button onClick={() => setPage(Math.max(0, page - 1))} aria-label="Previous formation"><ChevronLeft size={16} /></button>
          <button className={page === currentIdx ? 'on' : ''} onClick={() => setPage(currentIdx)}>Bit</button>
          <button onClick={() => setPage(Math.min(tops.length - 1, page + 1))} aria-label="Next formation"><ChevronRight size={16} /></button>
        </div>
      </div>
    </div>
  )
}
