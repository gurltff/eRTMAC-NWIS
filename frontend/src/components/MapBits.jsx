import L from 'leaflet'
import 'leaflet/dist/leaflet.css'
import { useEffect, useMemo, useRef, useState } from 'react'
import VectorBasemap from './VectorBasemap'
import { Circle, CircleMarker, MapContainer, Marker, Polygon, Polyline, Rectangle, TileLayer, Tooltip, useMap, useMapEvents } from 'react-leaflet'
import { useTheme } from '../context/ThemeContext'
import { fmt } from '../lib/util'

export const ASSAM_CENTER = [27.2, 95.05]
export const INDIA_VIEW = { center: [22.8, 82.5], zoom: 5 }
export const WORLD_VIEW = { center: [20, 40], zoom: 2 }
export const ASSAM_VIEW = { center: [27.15, 94.95], zoom: 9 }

const TILES = {
  light: 'https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png',
  dark: 'https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png',
}
const ATTR = '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> &copy; <a href="https://carto.com/attributions">CARTO</a> · Natural Earth'
const WORLD_BOUNDS = [[-82, -185], [85, 185]]

// Online tiles are the normal basemap. If they can't load (offline, or a host that
// blocks external images) the built-in Natural Earth basemap takes over.
const tileState = { loads: 0, errors: 0, failed: false }
const failListeners = new Set()
function onTileLoad() { tileState.loads++ }
function onTileError() {
  tileState.errors++
  if (!tileState.failed && tileState.loads === 0 && tileState.errors >= 3) {
    tileState.failed = true
    failListeners.forEach((fn) => fn(true))
  }
}
function useTilesFailed() {
  const [failed, setFailed] = useState(tileState.failed)
  useEffect(() => { failListeners.add(setFailed); return () => failListeners.delete(setFailed) }, [])
  return failed
}

export function BaseMap({ center = ASSAM_CENTER, zoom = 9, children, onClick, style, className }) {
  const { resolved } = useTheme()
  const failed = useTilesFailed()
  return (
    <MapContainer center={center} zoom={zoom} minZoom={2} maxBounds={WORLD_BOUNDS} maxBoundsViscosity={0.8} worldCopyJump={false}
      className={className} style={{ height: '100%', width: '100%', ...style }} zoomControl preferCanvas>
      {!failed && <TileLayer key={resolved} url={TILES[resolved]} attribution={ATTR} subdomains="abcd" maxZoom={19} noWrap
        eventHandlers={{ tileerror: onTileError, tileload: onTileLoad }} />}
      {failed && <VectorBasemap />}
      {onClick && <ClickHandler onClick={onClick} />}
      {children}
    </MapContainer>
  )
}

/** Buttons to jump between world, India and the Assam oil fields. */
export function ViewButtons({ extra }) {
  const map = useMap()
  const ref = useRef(null)
  // Stop drags and wheel zoom starting on the buttons. Clicks are filtered in ClickHandler
  // (blocking them here would also hide them from React).
  useEffect(() => {
    if (!ref.current) return
    L.DomEvent.on(ref.current, 'mousedown touchstart dblclick', L.DomEvent.stopPropagation)
    L.DomEvent.disableScrollPropagation(ref.current)
  }, [])
  const go = (v) => map.flyTo(v.center, v.zoom, { duration: 1.1 })
  return (
    <div className="view-buttons" ref={ref}>
      <button className="chip" onClick={() => go(WORLD_VIEW)}>World</button>
      <button className="chip" onClick={() => go(INDIA_VIEW)}>India</button>
      <button className="chip" onClick={() => go(ASSAM_VIEW)}>Assam oil fields</button>
      {extra}
    </div>
  )
}

/** At country scale, a callout shows where the sample data is. Click to zoom in. */
export function DataRegionCallout({ count }) {
  const map = useMap()
  const [zoom, setZoom] = useState(map.getZoom())
  useMapEvents({ zoomend: () => setZoom(map.getZoom()) })
  if (zoom >= 7) return null
  const icon = L.divIcon({
    className: '', iconSize: null,
    html: `<div class="region-callout"><span class="pulse-dot"></span><div><b>Upper Assam oil fields</b><br/><span>${count} wells · sample data · click to zoom in</span></div></div>`,
  })
  return <Marker position={[27.3, 95.1]} icon={icon} zIndexOffset={2000} eventHandlers={{ click: () => map.flyTo(ASSAM_VIEW.center, ASSAM_VIEW.zoom, { duration: 1.2 }) }} />
}

/** Fly to a selected point, zooming in if we're still at country or world scale. */
// Area with sample data (matches backend REGION, padded).
export const DATA_REGION = { min_lat: 25.7, max_lat: 28.45, min_lon: 93.1, max_lon: 96.7 }
export const inDataRegion = (lat, lon) => lat >= DATA_REGION.min_lat && lat <= DATA_REGION.max_lat && lon >= DATA_REGION.min_lon && lon <= DATA_REGION.max_lon

export function FocusPoint({ point, minZoom = 11 }) {
  const map = useMap()
  useEffect(() => {
    if (point && inDataRegion(point.lat, point.lon)) map.flyTo([point.lat, point.lon], Math.max(map.getZoom(), minZoom), { duration: 0.9 })
  }, [point?.lat, point?.lon]) // eslint-disable-line
  return null
}

function ClickHandler({ onClick }) {
  useMapEvents({
    click: (e) => {
      if (e.originalEvent?.target?.closest?.('.view-buttons, .region-callout')) return
      onClick(e.latlng.lat, e.latlng.lng)
    },
  })
  return null
}

export function FlyTo({ center, zoom }) {
  const map = useMap()
  useEffect(() => { if (center) map.flyTo(center, zoom || map.getZoom(), { duration: 0.8 }) }, [center?.[0], center?.[1], zoom]) // eslint-disable-line
  return null
}

export function FitBounds({ points, padding = 40 }) {
  const map = useMap()
  const key = JSON.stringify(points)
  useEffect(() => { if (points && points.length > 1) map.fitBounds(points, { padding: [padding, padding] }) }, [key]) // eslint-disable-line
  return null
}

// ---- wells ---------------------------------------------------------------
export const WELL_STYLE = {
  drilling: { color: 'var(--s2)', label: 'Drilling now' },
  producing: { color: 'var(--s1)', label: 'Producing' },
  dry: { color: 'var(--s7)', label: 'Dry hole' },
  other: { color: '#9b9287', label: 'Abandoned / shut-in / other' },
}
export function wellKind(w) {
  if (w.is_active) return 'drilling'
  if (w.outcome === 'dry') return 'dry'
  if (w.status === 'producing') return 'producing'
  return 'other'
}
const cssVar = (v) => (v.startsWith('var(') ? getComputedStyle(document.documentElement).getPropertyValue(v.slice(4, -1)).trim() || '#888' : v)

export function WellsLayer({ wells, onSelect, highlight }) {
  const { resolved } = useTheme()
  const map = useMap()
  const [zoom, setZoom] = useState(map.getZoom())
  useMapEvents({ zoomend: () => setZoom(map.getZoom()) })
  const small = zoom < 7 // at country scale, keep the cluster readable
  const colors = useMemo(() => Object.fromEntries(Object.entries(WELL_STYLE).map(([k, v]) => [k, cssVar(v.color)])), [resolved]) // eslint-disable-line
  return wells.map((w) => {
    const kind = wellKind(w)
    const hl = highlight && highlight.has(w.id)
    return (
      <CircleMarker key={`${w.id}-${resolved}`} center={[w.lat, w.lon]} radius={small ? (w.is_active ? 4 : 2.5) : w.is_active ? 8 : hl ? 7 : 5.5}
        pathOptions={{ color: resolved === 'dark' ? '#221f1c' : '#fbf8f2', weight: small ? 1 : 2, fillColor: colors[kind], fillOpacity: 1 }}
        eventHandlers={{ click: (e) => { L.DomEvent.stopPropagation(e); onSelect && onSelect(w) } }}>
        <Tooltip direction="top" offset={[0, -6]}>
          <b>{w.name}</b> · {WELL_STYLE[kind].label}{w.is_active && w.current_depth_m ? ` · ${fmt.m(w.current_depth_m)}` : ''}
        </Tooltip>
      </CircleMarker>
    )
  })
}

// ---- zones ---------------------------------------------------------------
export const ZONE_STYLE = {
  protected_area: { color: '#d03b3b', label: 'Protected area (no drilling)', dash: '5 5', fill: 0.14 },
  reserved_forest: { color: '#008300', label: 'Reserved forest (no drilling)', dash: '5 5', fill: 0.14 },
  wetland: { color: '#2a78d6', label: 'Wetland (no drilling)', dash: '5 5', fill: 0.16 },
  restricted: { color: '#ec835a', label: 'Restricted area', dash: '2 4', fill: 0.16 },
  urban: { color: '#8a817a', label: 'Urban area', dash: '2 4', fill: 0.12 },
  licensed_block: { color: '#9a6b2f', label: 'Licensed block (legal)', dash: null, fill: 0.03 },
}

export function ZonesLayer({ zones, showLicensed = true, onSelect }) {
  return zones.filter((z) => showLicensed || z.zone_type !== 'licensed_block').map((z) => {
    const s = ZONE_STYLE[z.zone_type] || ZONE_STYLE.restricted
    return (
      <Polygon key={z.id} positions={z.polygon} interactive={!!onSelect || z.zone_type !== 'licensed_block'}
        pathOptions={{ color: s.color, weight: z.zone_type === 'licensed_block' ? 1 : 1.5, dashArray: s.dash, fillColor: s.color, fillOpacity: s.fill }}
        eventHandlers={onSelect ? { click: (e) => { onSelect(e.latlng.lat, e.latlng.lng) } } : undefined}>
        <Tooltip sticky>{z.name}<br /><span className="muted">{s.label}</span></Tooltip>
      </Polygon>
    )
  })
}

// ---- candidates, untapped -------------------------------------------------
const diamond = (color, label) => L.divIcon({
  className: '',
  iconSize: [18, 18],
  iconAnchor: [9, 9],
  html: `<div title="${label}" style="width:14px;height:14px;transform:rotate(45deg);background:${color};border:2px solid #fff;box-shadow:0 1px 4px rgba(0,0,0,.35);margin:2px;border-radius:3px"></div>`,
})
const star = L.divIcon({
  className: '',
  iconSize: [24, 24],
  iconAnchor: [12, 12],
  html: `<svg width="24" height="24" viewBox="0 0 24 24"><path d="M12 2.5l2.9 6.2 6.6.8-4.9 4.6 1.3 6.6L12 17.4l-5.9 3.3 1.3-6.6L2.5 9.5l6.6-.8z" fill="#eda100" stroke="#fff" stroke-width="1.6" stroke-linejoin="round"/></svg>`,
})

export function CandidatesLayer({ candidates, onSelect }) {
  const icon = useMemo(() => diamond('#2b2623', 'Candidate'), [])
  return candidates.map((c) => (
    <Marker key={c.id} position={[c.lat, c.lon]} icon={icon} eventHandlers={{ click: () => onSelect && onSelect(c.lat, c.lon, c) }}>
      <Tooltip direction="top" offset={[0, -8]}><b>{c.name}</b><br />{c.target_formation} · {fmt.m(c.planned_td_m)}</Tooltip>
    </Marker>
  ))
}

// sequential single-hue ramp (amber), light → dark with probability
const RAMP = ['#fbe7b8', '#f7d27d', '#f0b440', '#e0921a', '#c06f0c', '#8f4f07']
export function rampColor(p) {
  const i = Math.min(RAMP.length - 1, Math.max(0, Math.floor((p - 0.35) / 0.65 * RAMP.length)))
  return RAMP[i]
}
export const HEAT_RAMP = RAMP

export function UntappedLayer({ grid, step, spots, showGrid = true, onSelect }) {
  return (
    <>
      {showGrid && grid.filter((c) => c.p >= 0.35).map((c, i) => (
        <Rectangle key={i} bounds={[[c.lat - step / 2, c.lon - step / 2], [c.lat + step / 2, c.lon + step / 2]]} interactive={false}
          pathOptions={{ stroke: false, fillColor: rampColor(c.p), fillOpacity: 0.18 + 0.4 * (c.p - 0.35) }} />
      ))}
      {spots.map((s) => (
        <Marker key={s.id} position={[s.lat, s.lon]} icon={star} eventHandlers={{ click: () => onSelect && onSelect(s.lat, s.lon, s) }}>
          <Tooltip direction="top" offset={[0, -10]}>
            <b>Untapped spot {s.id}</b><br />Score {s.score}/100 · {s.confidence_label} confidence<br />Risked: {fmt.bbl(s.risked_recoverable_bbl)}
          </Tooltip>
        </Marker>
      ))}
    </>
  )
}

// ---- drillers ------------------------------------------------------------
const drillerIcon = (breach) => L.divIcon({ className: '', iconSize: [26, 26], iconAnchor: [13, 13],
  html: `<div class="driller-icon ${breach ? 'breach' : ''}"><div class="ring"></div><div class="core"></div></div>` })

export function DrillerMarker({ lat, lon, name, status, onClick }) {
  const breach = status === 'OUTSIDE' || status === 'ILLEGAL_ZONE'
  const icon = useMemo(() => drillerIcon(breach), [breach])
  if (lat === null || lat === undefined) return null
  return (
    <Marker position={[lat, lon]} icon={icon} zIndexOffset={1000} eventHandlers={onClick ? { click: onClick } : undefined}>
      <Tooltip direction="top" offset={[0, -12]}><b>{name}</b><br />{status ? status.replace('_', ' ').toLowerCase() : 'no status'}</Tooltip>
    </Marker>
  )
}

export function ZoneCircle({ zone, breach }) {
  if (!zone) return null
  return (
    <>
      <Circle center={[zone.center.lat, zone.center.lon]} radius={zone.radius_m}
        pathOptions={{ color: breach ? '#d03b3b' : '#2a78d6', weight: 2, dashArray: '6 6', fillColor: breach ? '#d03b3b' : '#2a78d6', fillOpacity: 0.06 }} />
      <CircleMarker center={[zone.center.lat, zone.center.lon]} radius={4} pathOptions={{ color: '#2a78d6', fillColor: '#fff', fillOpacity: 1, weight: 2 }}>
        <Tooltip>Approved site</Tooltip>
      </CircleMarker>
      {zone.bottom_hole && (
        <>
          <Polyline positions={zone.bottom_hole.path} pathOptions={{ color: '#9a6b2f', weight: 2 }} />
          <CircleMarker center={[zone.bottom_hole.lat, zone.bottom_hole.lon]} radius={5} pathOptions={{ color: '#9a6b2f', fillColor: '#f3e6b5', fillOpacity: 1, weight: 2 }}>
            <Tooltip>Planned bottom of hole · {fmt.m(zone.bottom_hole.tvd_m)} TVD · {fmt.m(zone.bottom_hole.horizontal_displacement_m)} sideways</Tooltip>
          </CircleMarker>
        </>
      )}
    </>
  )
}

export function Legend({ items, title }) {
  return (
    <div className="card tight" style={{ padding: 12, fontSize: 12 }}>
      {title && <div className="eyebrow" style={{ marginBottom: 6 }}>{title}</div>}
      <div className="col gap-4">
        {items.map((it) => (
          <div key={it.label} className="row gap-6">
            {it.shape === 'area'
              ? <span style={{ width: 14, height: 10, borderRadius: 3, border: `1.5px dashed ${it.color}`, background: `${it.color}22` }} />
              : it.shape === 'diamond'
                ? <span style={{ width: 9, height: 9, background: it.color, transform: 'rotate(45deg)', borderRadius: 2, margin: '0 2px' }} />
                : <span className="dot" style={{ background: it.color, width: 10, height: 10 }} />}
            <span className="ink2">{it.label}</span>
          </div>
        ))}
      </div>
    </div>
  )
}
