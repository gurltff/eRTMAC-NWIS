import { Info } from 'lucide-react'
import { Fragment, useMemo, useState } from 'react'
import { CircleMarker, Tooltip } from 'react-leaflet'
import { Link } from 'react-router-dom'
import LocationPanel from '../components/LocationPanel'
import { BaseMap, CandidatesLayer, DrillerMarker, HEAT_RAMP, Legend, UntappedLayer, WELL_STYLE, WellsLayer, ZONE_STYLE, ZonesLayer, ZoneCircle } from '../components/MapBits'
import { ErrorBox, Loading } from '../components/ui'
import { useLive } from '../context/LiveContext'
import { fmt, useApi } from '../lib/util'

const LAYERS = [
  ['wells', 'Wells'], ['candidates', 'Candidate sites'], ['untapped', 'Untapped spots'], ['heat', 'Potential heatmap'],
  ['zones', 'No-go zones'], ['blocks', 'Licence blocks'], ['drillers', 'Drillers'], ['landslides', 'Landslides'],
]

export function useMapData() {
  return useApi('/api/map/layers')
}

export function SpotExtra({ spot }) {
  if (!spot) return null
  return (
    <div className="notice" style={{ marginBottom: 16 }}>
      <b>Untapped spot {spot.id}</b>: score {spot.score}/100 with {spot.confidence_label.toLowerCase()} confidence. No well within 2.5 km.
      Risked potential about {fmt.bbl(spot.risked_recoverable_bbl)} for one well.
    </div>
  )
}

export default function MapPage() {
  const { data, error, loading } = useMapData()
  const untapped = useApi('/api/map/untapped')
  const live = useApi('/api/tracking/live')
  const { positions } = useLive()
  const [on, setOn] = useState({ wells: true, candidates: true, untapped: true, heat: true, zones: true, blocks: false, drillers: true, landslides: false })
  const [point, setPoint] = useState(null)
  const [showHelp, setShowHelp] = useState(false)

  const drillers = useMemo(() => (live.data || []).map((d) => {
    const p = positions[d.user_id]
    return p ? { ...d, lat: p.lat, lon: p.lon, tracking_status: p.status } : d
  }), [live.data, positions])

  if (loading) return <Loading />
  if (error) return <ErrorBox error={error} />
  const toggle = (k) => setOn({ ...on, [k]: !on[k] })

  return (
    <div>
      <div className="row between wrap" style={{ marginBottom: 14 }}>
        <div>
          <div className="eyebrow">Location intelligence</div>
          <h1 style={{ fontSize: 30 }}>Tap anywhere to check a spot</h1>
        </div>
        <button className="btn ghost sm" onClick={() => setShowHelp(!showHelp)}><Info size={15} />How untapped spots work</button>
      </div>
      {showHelp && untapped.data && (
        <div className="card" style={{ marginBottom: 14 }}>
          <p className="ink2">{untapped.data.explanation.prospect_model.what} {untapped.data.explanation.prospect_model.trained_on} {untapped.data.explanation.prospect_model.checked_by}</p>
          <p className="ink2 mt-8">{untapped.data.explanation.prospect_model.untapped}</p>
          <p className="ink2 mt-8">{untapped.data.explanation.prospect_model.confidence}</p>
          <p className="small muted mt-8">{untapped.data.explanation.note} <Link to="/office/data">More about the models →</Link></p>
        </div>
      )}
      <div className="map-page">
        <BaseMap onClick={(lat, lon) => setPoint({ lat, lon })}>
          {on.heat && untapped.data && <UntappedLayer grid={untapped.data.grid} step={untapped.data.grid_step} spots={[]} />}
          {on.zones && <ZonesLayer zones={data.zones.filter((z) => z.zone_type !== 'licensed_block')} onSelect={(lat, lon) => setPoint({ lat, lon })} />}
          {on.blocks && <ZonesLayer zones={data.zones.filter((z) => z.zone_type === 'licensed_block')} />}
          {on.landslides && data.landslides.map((s, i) => (
            <CircleMarker key={i} center={[s.lat, s.lon]} radius={4} pathOptions={{ color: '#8f4f07', weight: 1, fillColor: '#c06f0c', fillOpacity: 0.7 }}>
              <Tooltip>Landslide · {s.event_date} · {s.size}</Tooltip>
            </CircleMarker>
          ))}
          {on.untapped && untapped.data && <UntappedLayer grid={[]} step={0} spots={untapped.data.spots} showGrid={false}
            onSelect={(lat, lon, s) => setPoint({ lat, lon, title: `Untapped spot ${s.id}`, spot: s })} />}
          {on.candidates && <CandidatesLayer candidates={data.candidates} onSelect={(lat, lon, c) => setPoint({ lat, lon, title: c.name })} />}
          {on.wells && <WellsLayer wells={data.wells} onSelect={(w) => setPoint({ lat: w.lat, lon: w.lon, title: w.name, well: w })} />}
          {on.drillers && drillers.map((d) => (
            <Fragment key={d.user_id}>
              <ZoneCircle zone={d.zone} breach={d.tracking_status === 'OUTSIDE' || d.tracking_status === 'ILLEGAL_ZONE'} />
              <DrillerMarker lat={d.lat} lon={d.lon} name={d.name} status={d.tracking_status} />
            </Fragment>
          ))}
        </BaseMap>
        <div className="map-overlay tl">
          <div className="layer-toggles">
            {LAYERS.map(([k, label]) => <button key={k} className={`chip ${on[k] ? 'on' : ''}`} onClick={() => toggle(k)}>{label}</button>)}
          </div>
        </div>
        <div className="map-overlay bl" style={{ maxWidth: 230 }}>
          <Legend title="Map key" items={[
            ...Object.values(WELL_STYLE).map((s) => ({ label: s.label, color: s.color })),
            { label: 'Candidate site', color: 'var(--ink)', shape: 'diamond' },
            { label: 'Untapped spot (model)', color: '#eda100' },
            { label: ZONE_STYLE.protected_area.label, color: ZONE_STYLE.protected_area.color, shape: 'area' },
            { label: ZONE_STYLE.reserved_forest.label, color: ZONE_STYLE.reserved_forest.color, shape: 'area' },
            { label: ZONE_STYLE.wetland.label, color: ZONE_STYLE.wetland.color, shape: 'area' },
            { label: 'Restricted / urban', color: ZONE_STYLE.restricted.color, shape: 'area' },
          ]} />
          {on.heat && (
            <div className="card tight mt-8" style={{ padding: 10 }}>
              <div className="tiny muted">Oil potential (model score 35 → 100)</div>
              <div className="row gap-4 mt-4">{HEAT_RAMP.map((c) => <span key={c} style={{ flex: 1, height: 8, background: c, borderRadius: 2 }} />)}</div>
            </div>
          )}
        </div>
        <LocationPanel point={point} onClose={() => setPoint(null)} extra={
          <>
            <SpotExtra spot={point?.spot} />
            {point?.well && (
              <div className="notice" style={{ marginBottom: 16 }}>
                <b>{point.well.name}</b> · {point.well.operator} · spud {point.well.spud_year} · {fmt.title(point.well.status)}
                {point.well.is_active && <> · drilling at {fmt.m(point.well.current_depth_m)}</>}
                <div className="mt-4"><Link to={`/office/offset?well=${point.well.id}`}>Open offset-well analysis →</Link></div>
              </div>
            )}
          </>
        } />
      </div>
    </div>
  )
}
