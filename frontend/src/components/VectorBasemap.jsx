import L from 'leaflet'
import { useEffect, useMemo, useState } from 'react'
import { GeoJSON, Marker, Pane, useMap, useMapEvents } from 'react-leaflet'
import { feature, mesh } from 'topojson-client'
import { useTheme } from '../context/ThemeContext'

// Built-in basemap from Natural Earth (public domain, India point-of-view borders),
// shipped with the app in public/basemap/. Used whenever the online map tiles
// can't load, so the map always shows the world, India and its states.
let dataPromise = null
function loadBasemap() {
  if (!dataPromise) {
    const get = (f) => fetch(`./basemap/${f}`).then((r) => { if (!r.ok) throw new Error(f); return r.json() })
    dataPromise = Promise.all(['world.json', 'southasia.json', 'india_states.json', 'rivers.json', 'labels.json'].map(get))
      .then(([world, sa, states, rivers, labels]) => ({
        world: feature(world, world.objects[Object.keys(world.objects)[0]]),
        southAsia: feature(sa, sa.objects[Object.keys(sa.objects)[0]]),
        states: mesh(states, states.objects[Object.keys(states.objects)[0]]),
        rivers: feature(rivers, rivers.objects[Object.keys(rivers.objects)[0]]),
        labels,
      }))
      .catch((e) => { dataPromise = null; throw e })
  }
  return dataPromise
}

const PALETTE = {
  light: { ocean: '#cfdde3', land: '#f4efe4', india: '#fbf6ea', border: '#b9ab96', indiaBorder: '#8a7456', state: '#c8b89e', river: '#8fb3c9', label: '#5d5247', halo: '#fbf8f2' },
  dark: { ocean: '#141b20', land: '#27231f', india: '#2e2924', border: '#4a4239', indiaBorder: '#8a7456', state: '#4d443a', river: '#2f5670', label: '#c9bfb2', halo: '#161412' },
}

function useView() {
  const map = useMap()
  const [view, setView] = useState(() => ({ zoom: map.getZoom(), bounds: map.getBounds().pad(0.3) }))
  useMapEvents({ moveend: () => setView({ zoom: map.getZoom(), bounds: map.getBounds().pad(0.3) }) })
  return view
}

function labelIcon(text, cls, c) {
  return L.divIcon({
    className: '',
    iconSize: null,
    html: `<div class="bm-label ${cls}" style="color:${c.label};--halo:${c.halo}">${text}</div>`,
  })
}

// Labels are placed greedily in priority order and skipped when they would overlap one
// already placed, so the map stays readable at every zoom.
function Labels({ data, c }) {
  const map = useMap()
  const { zoom, bounds } = useView()
  const items = useMemo(() => {
    const cand = []
    const inView = (lat, lon) => bounds.contains([lat, lon])
    if (zoom < 8) {
      for (const [name, lat, lon, minz] of data.labels.countries) {
        if (zoom >= Math.max(2, minz - 1) && inView(lat, lon) && (name !== 'India' || zoom < 6)) cand.push(['c', name, lat, lon, minz])
      }
    }
    for (const [name, lat, lon, minz, cap] of data.labels.cities) {
      if (cap && zoom >= minz && inView(lat, lon)) cand.push(['k', name, lat, lon, 10 + minz])
    }
    if (zoom >= 5 && zoom < 9) for (const [name, lat, lon] of data.labels.states) if (inView(lat, lon)) cand.push(['s', name, lat, lon, 20])
    for (const [name, lat, lon, minz, cap] of data.labels.cities) {
      if (!cap && zoom >= minz && inView(lat, lon)) cand.push(['t', name, lat, lon, 30 + minz])
    }
    cand.sort((a, b) => a[4] - b[4])
    const placed = []
    const out = []
    for (const it of cand) {
      const p = map.latLngToContainerPoint([it[2], it[3]])
      const w = it[1].length * (it[0] === 'c' ? 8.5 : 6.4) + 14, h = 16
      const box = it[0] === 't' || it[0] === 'k' ? [p.x - 6, p.y - h / 2, p.x + w, p.y + h / 2] : [p.x - w / 2, p.y - h / 2, p.x + w / 2, p.y + h / 2]
      if (placed.some((b) => box[0] < b[2] && box[2] > b[0] && box[1] < b[3] && box[3] > b[1])) continue
      placed.push(box)
      out.push(it)
    }
    return out
  }, [data, zoom, bounds, map])
  return items.map(([kind, name, lat, lon]) => (
    <Marker key={`${kind}-${name}-${lat}`} position={[lat, lon]} interactive={false} keyboard={false}
      icon={labelIcon(name, { c: 'bm-country', s: 'bm-state', k: 'bm-city bm-capital', t: 'bm-city' }[kind], c)} />
  ))
}

export default function VectorBasemap() {
  const map = useMap()
  const { resolved } = useTheme()
  const [data, setData] = useState(null)
  const c = PALETTE[resolved] || PALETTE.light
  useEffect(() => { loadBasemap().then(setData).catch(() => {}) }, [])
  useEffect(() => {
    const el = map.getContainer()
    el.style.background = c.ocean
    return () => { el.style.background = '' }
  }, [map, c.ocean])
  if (!data) return null
  return (
    <>
      <Pane name="bm-land" style={{ zIndex: 205 }}>
        <GeoJSON key={`w-${resolved}`} data={data.world} interactive={false}
          style={{ fillColor: c.land, fillOpacity: 1, color: c.border, weight: 0.8 }} />
        <GeoJSON key={`sa-${resolved}`} data={data.southAsia} interactive={false}
          style={(f) => (f.properties.iso === 'IND'
            ? { fillColor: c.india, fillOpacity: 1, color: c.indiaBorder, weight: 1.6 }
            : { fillColor: c.land, fillOpacity: 1, color: c.border, weight: 0.9 })} />
      </Pane>
      <Pane name="bm-lines" style={{ zIndex: 210 }}>
        <GeoJSON key={`st-${resolved}`} data={data.states} interactive={false} style={{ color: c.state, weight: 0.9, dashArray: '4 3' }} />
        <GeoJSON key={`rv-${resolved}`} data={data.rivers} interactive={false}
          style={(f) => ({ color: c.river, weight: f.properties.scalerank <= 3 ? 2.2 : f.properties.scalerank <= 5 ? 1.4 : 0.9, opacity: 0.9 })} />
      </Pane>
      <Pane name="bm-labels" style={{ zIndex: 390, pointerEvents: 'none' }}>
        <Labels data={data} c={c} />
      </Pane>
    </>
  )
}
