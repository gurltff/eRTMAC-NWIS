// JavaScript port of backend/app/services/geo.py (same formulas, same constants).
export const R = 6371000
const rad = (d) => (d * Math.PI) / 180
const deg = (r) => (r * 180) / Math.PI

export function haversine(lat1, lon1, lat2, lon2) {
  const p1 = rad(lat1), p2 = rad(lat2), dp = rad(lat2 - lat1), dl = rad(lon2 - lon1)
  const a = Math.sin(dp / 2) ** 2 + Math.cos(p1) * Math.cos(p2) * Math.sin(dl / 2) ** 2
  return 2 * R * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a))
}

export function bearing(lat1, lon1, lat2, lon2) {
  const p1 = rad(lat1), p2 = rad(lat2), dl = rad(lon2 - lon1)
  const x = Math.sin(dl) * Math.cos(p2)
  const y = Math.cos(p1) * Math.sin(p2) - Math.sin(p1) * Math.cos(p2) * Math.cos(dl)
  return (deg(Math.atan2(x, y)) + 360) % 360
}

export function destination(lat, lon, brg, dist) {
  const d = dist / R, t = rad(brg), p1 = rad(lat), l1 = rad(lon)
  const p2 = Math.asin(Math.sin(p1) * Math.cos(d) + Math.cos(p1) * Math.sin(d) * Math.cos(t))
  const l2 = l1 + Math.atan2(Math.sin(t) * Math.sin(d) * Math.cos(p1), Math.cos(d) - Math.sin(p1) * Math.sin(p2))
  return [deg(p2), ((deg(l2) + 540) % 360) - 180]
}

export function offsetNE(lat, lon, north, east) {
  return [lat + deg(north / R), lon + deg(east / (R * Math.cos(rad(lat))))]
}

export function circlePolygon(lat, lon, radius, n = 64) {
  const pts = []
  for (let i = 0; i < n; i++) pts.push(destination(lat, lon, (360 * i) / n, radius))
  pts.push(pts[0])
  return pts
}

export function pointInPolygon(lat, lon, ring) {
  let inside = false
  for (let i = 0, j = ring.length - 1; i < ring.length; j = i++) {
    const [yi, xi] = ring[i], [yj, xj] = ring[j]
    if ((yi > lat) !== (yj > lat)) {
      const x = ((xj - xi) * (lat - yi)) / (yj - yi) + xi
      if (lon < x) inside = !inside
    }
  }
  return inside
}

export function distToPolyline(lat, lon, line) {
  const kx = Math.cos(rad(lat)) * Math.PI * R / 180, ky = Math.PI * R / 180
  let best = Infinity
  for (let i = 0; i < line.length - 1; i++) {
    const ax = (line[i][1] - lon) * kx, ay = (line[i][0] - lat) * ky
    const bx = (line[i + 1][1] - lon) * kx, by = (line[i + 1][0] - lat) * ky
    const dx = bx - ax, dy = by - ay, l2 = dx * dx + dy * dy
    const t = l2 === 0 ? 0 : Math.max(0, Math.min(1, -(ax * dx + ay * dy) / l2))
    best = Math.min(best, Math.hypot(ax + t * dx, ay + t * dy))
  }
  return best
}
export const distToPolygonEdge = (lat, lon, ring) => distToPolyline(lat, lon, [...ring, ring[0]])

// Minimum curvature method (see geo.py for the formulas).
export function minimumCurvature(st) {
  const pts = [{ md: st[0].md, tvd: st[0].md, n: 0, e: 0 }]
  for (let k = 1; k < st.length; k++) {
    const s1 = st[k - 1], s2 = st[k]
    const i1 = rad(s1.inc), i2 = rad(s2.inc), a1 = rad(s1.azi), a2 = rad(s2.azi), dmd = s2.md - s1.md
    const cb = Math.cos(i2 - i1) - Math.sin(i1) * Math.sin(i2) * (1 - Math.cos(a2 - a1))
    const b = Math.acos(Math.max(-1, Math.min(1, cb)))
    const rf = b < 1e-9 ? 1 : (2 / b) * Math.tan(b / 2)
    const p = pts[pts.length - 1]
    pts.push({
      md: s2.md,
      tvd: p.tvd + (dmd / 2) * (Math.cos(i1) + Math.cos(i2)) * rf,
      n: p.n + (dmd / 2) * (Math.sin(i1) * Math.cos(a1) + Math.sin(i2) * Math.cos(a2)) * rf,
      e: p.e + (dmd / 2) * (Math.sin(i1) * Math.sin(a1) + Math.sin(i2) * Math.sin(a2)) * rf,
    })
  }
  return pts
}

export function buildAndHold(kop, build, hold, md, azi, step = 30) {
  const st = []
  for (let x = 0; x <= md + 1e-6; x += step) st.push({ md: x, inc: x <= kop ? 0 : Math.min(hold, ((x - kop) / 30) * build), azi })
  if (st[st.length - 1].md < md) st.push({ md, inc: st[st.length - 1].inc, azi })
  return st
}

export function bottomHole(lat, lon, st) {
  const path = minimumCurvature(st)
  const end = path[path.length - 1]
  const [blat, blon] = offsetNE(lat, lon, end.n, end.e)
  const every = Math.max(1, Math.floor(path.length / 40))
  return {
    lat: blat, lon: blon, tvd_m: +end.tvd.toFixed(1), md_m: +end.md.toFixed(1),
    horizontal_displacement_m: +Math.hypot(end.n, end.e).toFixed(1),
    path: path.filter((_, i) => i % every === 0).map((p) => offsetNE(lat, lon, p.n, p.e)),
  }
}

export function operatingRadius(reach, declared) {
  const margin = Math.max(0.1 * reach, 250)
  const cap = reach + margin
  const radius = declared ? Math.min(cap, declared) : cap
  return { reach_m: reach, safety_margin_m: +margin.toFixed(1), capability_radius_m: +cap.toFixed(1), declared_radius_m: declared,
    radius_m: +radius.toFixed(1), limited_by: declared && declared < cap ? 'declared area' : 'rig reach' }
}

export function checkPosition(lat, lon, clat, clon, radius, zones) {
  const d = haversine(lat, lon, clat, clon)
  for (const z of zones) if (pointInPolygon(lat, lon, z.polygon)) return { status: 'ILLEGAL_ZONE', distance_m: d, radius_m: radius, zone_name: z.name, zone_type: z.zone_type }
  const status = d > radius ? 'OUTSIDE' : d > 0.9 * radius ? 'NEAR_EDGE' : 'INSIDE'
  return { status, distance_m: d, radius_m: radius, zone_name: null, zone_type: null }
}

export function breachTransition(prev, cur) {
  if (prev === cur.status) return null
  if (cur.status === 'ILLEGAL_ZONE') return 'ENTERED_ILLEGAL_ZONE'
  if (cur.status === 'OUTSIDE') return 'LEFT_ALLOWED_ZONE'
  if (cur.status === 'NEAR_EDGE' && (prev === null || prev === undefined || prev === 'INSIDE')) return 'NEAR_BOUNDARY'
  if ((prev === 'OUTSIDE' || prev === 'ILLEGAL_ZONE') && (cur.status === 'INSIDE' || cur.status === 'NEAR_EDGE')) return 'RETURNED_TO_ZONE'
  return null
}
