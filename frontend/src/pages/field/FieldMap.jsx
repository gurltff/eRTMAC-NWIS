import { useMemo, useState } from 'react'
import { Fragment } from 'react'
import LocationPanel from '../../components/LocationPanel'
import { BaseMap, DrillerMarker, FitBounds, WellsLayer, ZoneCircle, ZonesLayer } from '../../components/MapBits'
import { Loading, StatusPill } from '../../components/ui'
import { useAuth } from '../../context/AuthContext'
import { useLive } from '../../context/LiveContext'
import { TRACK_STATUS, useApi } from '../../lib/util'

export default function FieldMap() {
  const { user } = useAuth()
  const layers = useApi('/api/map/layers')
  const live = useApi('/api/tracking/live')
  const { positions } = useLive()
  const [point, setPoint] = useState(null)
  const drillers = useMemo(() => (live.data || []).map((d) => {
    const p = positions[d.user_id]
    return p ? { ...d, lat: p.lat, lon: p.lon, tracking_status: p.status } : d
  }), [live.data, positions])
  if (layers.loading) return <Loading />
  const mine = drillers.find((d) => d.user_id === user.id)
  const st = mine && (TRACK_STATUS[mine.tracking_status] || null)
  return (
    <div className="col gap-16">
      <div className="row between"><h1 style={{ fontSize: 28 }}>Map</h1>{st && <StatusPill tone={st.cls} label={st.label} />}</div>
      <div className="field-map tall" style={{ position: 'relative' }}>
        <BaseMap onClick={(lat, lon) => setPoint({ lat, lon })} zoom={user.role === 'driller' ? 13 : 9}>
          <ZonesLayer zones={layers.data.zones.filter((z) => z.zone_type !== 'licensed_block')} onSelect={(lat, lon) => setPoint({ lat, lon })} />
          <WellsLayer wells={layers.data.wells} onSelect={(w) => setPoint({ lat: w.lat, lon: w.lon, title: w.name })} />
          {drillers.map((d) => (
            <Fragment key={d.user_id}>
              <ZoneCircle zone={d.zone} breach={d.tracking_status === 'OUTSIDE' || d.tracking_status === 'ILLEGAL_ZONE'} />
              <DrillerMarker lat={d.lat} lon={d.lon} name={d.name} status={d.tracking_status} />
            </Fragment>
          ))}
          {mine?.zone && <FitBounds points={mine.zone.polygon} padding={10} />}
        </BaseMap>
        <LocationPanel point={point} onClose={() => setPoint(null)} />
      </div>
      <p className="tiny muted">Tap anywhere to check a spot: legality, hazards, soil, ownership and oil estimate.</p>
    </div>
  )
}
