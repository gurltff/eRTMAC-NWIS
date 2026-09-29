// In-browser demo backend for the static hosted build (npm run build:demo).
// Answers the same /api routes as FastAPI from a snapshot of the sample database
// (public/demo/snapshot.json) plus JavaScript ports of the geometry, alert and
// extraction logic. Changes (registrations, approvals, breaches, alerts, imported
// documents) live in memory and in this browser's localStorage only.
import * as geo from './geo'
import { evaluate } from './alerts'
import { fileText, ruleExtract, severityFrom } from './extract'

const STORE_KEY = 'nwis-demo-state-v1'
let snap = null
let S = null // mutable state
const subscribers = new Set()
const timers = { sims: {}, drill: null }

class HttpError extends Error { constructor(status, message) { super(message); this.status = status } }
const fail = (status, msg) => { throw new HttpError(status, msg) }
const now = () => new Date().toISOString()
const clone = (x) => JSON.parse(JSON.stringify(x))

// --------------------------------------------------------------------------- state
async function load() {
  if (snap) return
  const res = await fetch('./demo/snapshot.json')
  snap = await res.json()
  let saved = null
  try { saved = JSON.parse(localStorage.getItem(STORE_KEY) || 'null') } catch { saved = null }
  S = saved || {
    users: snap.users, drillers: snap.drillers, breaches: snap.breaches, alerts: [], depths: {},
    documents: [], extraWells: [], extraEvents: [], trails: {}, nextId: 100000,
  }
  for (const w of snap.wells) if (w.is_active && S.depths[w.id] === undefined) S.depths[w.id] = w.current_depth_m
  startDrillingSim()
}
let saveT = null
function save() {
  clearTimeout(saveT)
  saveT = setTimeout(() => { try { localStorage.setItem(STORE_KEY, JSON.stringify(S)) } catch { /* quota */ } }, 300)
}
const nextId = () => ++S.nextId
const emit = (msg) => subscribers.forEach((fn) => { try { fn(msg) } catch { /* ignore */ } })

const allWells = () => [...snap.wells, ...S.extraWells].map((w) => (w.is_active ? { ...w, current_depth_m: S.depths[w.id] ?? w.current_depth_m } : w))
const allEvents = () => [...snap.events, ...S.extraEvents]
const zones = () => snap.layers.zones
const illegalZones = () => zones().filter((z) => !z.legal_to_drill)

// --------------------------------------------------------------------------- auth
function tokenFor(u) { return btoa(JSON.stringify({ sub: u.id, role: u.role, demo: true })) }
function userFrom(token) {
  if (!token) return null
  try { const { sub } = JSON.parse(atob(token)); return S.users.find((u) => u.id === sub) || null } catch { return null }
}
function need(user, ...roles) {
  if (!user) fail(401, 'Please log in again.')
  if (roles.length && !roles.includes(user.role)) fail(403, `This needs one of these roles: ${roles.join(', ')}.`)
  return user
}
function userDict(u) {
  const d = { id: u.id, email: u.email, full_name: u.full_name, role: u.role }
  const p = S.drillers.find((x) => x.user_id === u.id)
  if (p) d.driller_status = p.status
  return d
}

// --------------------------------------------------------------------------- spatial helpers
function legality(lat, lon) {
  const inside = zones().filter((z) => geo.pointInPolygon(lat, lon, z.polygon))
  const illegal = inside.filter((z) => !z.legal_to_drill)
  const blocks = inside.filter((z) => z.zone_type === 'licensed_block')
  let nearest = null, nd = Infinity
  for (const z of illegalZones()) {
    const d = geo.pointInPolygon(lat, lon, z.polygon) ? 0 : geo.distToPolygonEdge(lat, lon, z.polygon)
    if (d < nd) { nd = d; nearest = z }
  }
  let verdict, summary
  if (illegal.length) { verdict = 'ILLEGAL'; summary = `Inside ${illegal[0].name} (${illegal[0].zone_type.replace('_', ' ')}). Drilling is not allowed here.` }
  else if (blocks.length) { verdict = 'LEGAL'; summary = `Inside licensed block ${blocks[0].name} (licensee: ${blocks[0].licensee}).` }
  else { verdict = 'NEEDS_LICENCE'; summary = 'Not in any protected or restricted area, but no licence block covers this spot yet.' }
  return { verdict, summary, zones: inside.map(({ polygon, ...z }) => z),
    nearest_restricted: nearest ? { name: nearest.name, zone_type: nearest.zone_type, distance_m: Math.round(nd) } : null }
}
function geologyAt(lat, lon) {
  const g = snap.layers.geology.find((u) => geo.pointInPolygon(lat, lon, u.polygon))
  return g ? { ...snap.geology_full.find((x) => x.id === g.id) } : null
}
let cellIndex = null
function cellAt(lat, lon) {
  if (!cellIndex) { cellIndex = new Map(); for (const c of snap.cells) cellIndex.set(`${Math.round(c[0] * 1000)},${Math.round(c[1] * 1000)}`, c) }
  const st = snap.grid_step, r = snap.region
  const i = Math.max(0, Math.round((lat - r.min_lat - st / 2) / st)), j = Math.max(0, Math.round((lon - r.min_lon - st / 2) / st))
  const clat = r.min_lat + st / 2 + i * st, clon = r.min_lon + st / 2 + j * st
  return cellIndex.get(`${Math.round(clat * 1000)},${Math.round(clon * 1000)}`) || snap.cells.reduce((b, c) => (Math.abs(c[0] - lat) + Math.abs(c[1] - lon) < Math.abs(b[0] - lat) + Math.abs(b[1] - lon) ? c : b))
}
const wellsWithin = (lat, lon, radius, excludeId) => allWells().filter((w) => w.id !== excludeId)
  .map((w) => [w, geo.haversine(lat, lon, w.lat, w.lon)]).filter(([, d]) => d <= radius).sort((a, b) => a[1] - b[1])

// --------------------------------------------------------------------------- drillers
function allowedZone(p) {
  if (p.site_lat === null || p.site_lat === undefined) return null
  const reach = p.equipment.length ? Math.max(...p.equipment.map((e) => e.max_horizontal_reach_m)) : 500
  const maxDepth = p.equipment.length ? Math.max(...p.equipment.map((e) => e.max_depth_m)) : null
  const radius = geo.operatingRadius(reach, p.work_radius_m)
  const z = { center: { lat: p.site_lat, lon: p.site_lon }, ...radius, polygon: geo.circlePolygon(p.site_lat, p.site_lon, radius.radius_m),
    site_legality: legality(p.site_lat, p.site_lon), warnings: [], bottom_hole: null }
  if (p.planned_md_m) {
    const b = geo.bottomHole(p.site_lat, p.site_lon, geo.buildAndHold(p.planned_kop_m || 0, p.planned_build_rate || 0, p.planned_hold_inc || 0, p.planned_md_m, p.planned_azimuth || 0))
    const bl = legality(b.lat, b.lon)
    z.bottom_hole = { ...b, legality: bl.verdict }
    if (b.horizontal_displacement_m > reach) z.warnings.push(`Planned well reaches ${Math.round(b.horizontal_displacement_m)} m sideways, more than the rig's ${Math.round(reach)} m reach.`)
    if (bl.verdict === 'ILLEGAL') z.warnings.push('The planned bottom of the hole ends up under a protected or restricted area.')
    if (maxDepth && p.planned_md_m > maxDepth) z.warnings.push(`Planned depth ${Math.round(p.planned_md_m)} m is deeper than the rig's ${Math.round(maxDepth)} m rating.`)
  }
  if (z.site_legality.verdict === 'ILLEGAL') z.warnings.push('The approved site itself is inside an illegal zone.')
  return z
}
function checklist(p) {
  const have = new Set(p.documents.map((d) => d.doc_type))
  const req = snap.doc_types.required
  return [
    { step: 'personal', label: 'Personal details', done: !!(p.phone && p.designation) },
    { step: 'company', label: 'Company details', done: !!(p.company_name && p.licence_number) },
    { step: 'documents', label: 'Required documents uploaded', done: req.every((t) => have.has(t)), missing: req.filter((t) => !have.has(t)).map((t) => snap.doc_types.types[t]) },
    { step: 'equipment', label: 'At least one rig declared', done: p.equipment.length > 0 },
    { step: 'area', label: 'Working area set', done: p.site_lat !== null && p.site_lat !== undefined && !!p.work_radius_m },
  ]
}
function profile(p) {
  const u = S.users.find((x) => x.id === p.user_id)
  return { ...p, full_name: u.full_name, email: u.email, checklist: checklist(p), zone: allowedZone(p) }
}
const myProfile = (user) => S.drillers.find((d) => d.user_id === user.id) || fail(404, 'No driller profile.')
const editable = (p) => { if (p.status === 'submitted') fail(400, 'Your registration is under review. You can edit it after the admin replies.') }

const BREACH_TEXT = { ENTERED_ILLEGAL_ZONE: 'Entered an illegal zone', LEFT_ALLOWED_ZONE: 'Left the allowed working zone',
  NEAR_BOUNDARY: 'Close to the edge of the allowed zone', RETURNED_TO_ZONE: 'Back inside the allowed zone' }

function processPosition(user, lat, lon, simulated) {
  const p = S.drillers.find((d) => d.user_id === user.id)
  const zone = p && allowedZone(p)
  const check = zone ? geo.checkPosition(lat, lon, zone.center.lat, zone.center.lon, zone.radius_m, illegalZones()) : null
  const status = check ? check.status : 'NO_ZONE'
  let breach = null
  if (p) {
    const ev = check ? geo.breachTransition(p.tracking_status, check) : null
    Object.assign(p, { tracking_status: status, last_lat: lat, last_lon: lon, last_seen_at: now() })
    const trail = (S.trails[user.id] = [...(S.trails[user.id] || []), [lat, lon]].slice(-60))
    void trail
    if (ev) {
      breach = { id: nextId(), user_id: user.id, name: user.full_name, event_type: ev, text: BREACH_TEXT[ev],
        is_breach: ev === 'ENTERED_ILLEGAL_ZONE' || ev === 'LEFT_ALLOWED_ZONE', status, lat, lon,
        distance_m: Math.round(check.distance_m), radius_m: Math.round(check.radius_m), zone_name: check.zone_name,
        simulated, acknowledged: false, created_at: now() }
      S.breaches.push(breach)
    }
  }
  save()
  const round = check ? { ...check, distance_m: +check.distance_m.toFixed(1), radius_m: +check.radius_m.toFixed(1),
    is_breach: status === 'OUTSIDE' || status === 'ILLEGAL_ZONE' } : null
  const pos = { type: 'position', user_id: user.id, driller_id: p?.id, name: user.full_name, company: p?.company_name, lat, lon, status, check: round, simulated, at: now() }
  emit(pos)
  if (breach) emit({ type: 'breach', ...breach })
  return { position: pos, breach: breach ? { type: 'breach', ...breach } : null }
}

function simWaypoints(zone) {
  const c = zone.center, r = zone.radius_m
  const pts = [[c.lat, c.lon], geo.destination(c.lat, c.lon, 210, 0.45 * r), geo.destination(c.lat, c.lon, 300, 0.6 * r)]
  let best = null
  for (const z of illegalZones()) {
    const clat = z.polygon.reduce((s, p) => s + p[0], 0) / z.polygon.length, clon = z.polygon.reduce((s, p) => s + p[1], 0) / z.polygon.length
    const b = geo.bearing(c.lat, c.lon, clat, clon)
    for (let st = 50; st < 1.6 * r; st += 50) {
      const p = geo.destination(c.lat, c.lon, b, st)
      if (geo.pointInPolygon(p[0], p[1], z.polygon)) { if (!best || st < best[0]) best = [st, geo.destination(c.lat, c.lon, b, st + 150)]; break }
    }
  }
  if (best) pts.push(best[1], [c.lat, c.lon])
  const ob = best ? (geo.bearing(c.lat, c.lon, ...best[1]) + 150) % 360 : 90
  pts.push(geo.destination(c.lat, c.lon, ob, 0.8 * r), geo.destination(c.lat, c.lon, ob, 1.3 * r), geo.destination(c.lat, c.lon, ob + 40, 0.5 * r), [c.lat, c.lon])
  const path = []
  for (let i = 0; i < pts.length - 1; i++) {
    const d = geo.haversine(...pts[i], ...pts[i + 1]), n = Math.max(1, Math.floor(d / 67.5)), b = geo.bearing(...pts[i], ...pts[i + 1])
    for (let k = 0; k < n; k++) path.push(geo.destination(...pts[i], b, (d * k) / n))
  }
  path.push(pts[pts.length - 1])
  return path
}
function startSim(userId) {
  if (timers.sims[userId]) return
  const user = S.users.find((u) => u.id === userId)
  const p = S.drillers.find((d) => d.user_id === userId)
  const zone = p && allowedZone(p)
  if (!zone) fail(400, 'This driller has no working area yet, so there is nothing to simulate.')
  const path = simWaypoints(zone)
  let i = 0
  timers.sims[userId] = setInterval(() => {
    const [lat, lon] = path[i % path.length]
    processPosition(user, ...geo.offsetNE(lat, lon, 3 * Math.sin(i * 1.7), 3 * Math.cos(i * 1.3)), true)
    i++
  }, 1500)
}
function stopSim(userId) { clearInterval(timers.sims[userId]); delete timers.sims[userId] }

// --------------------------------------------------------------------------- wells & alerts
function offsetEvents(well, radius) {
  const wells = allWells(), events = allEvents()
  const offsets = wells.filter((w) => w.id !== well.id).map((w) => [w, geo.haversine(well.lat, well.lon, w.lat, w.lon)]).filter(([, d]) => d <= radius)
  const out = []
  for (const [w, d] of offsets) for (const e of events) if (e.well_id === w.id) out.push({ ...e, well_name: w.name, distance_m: d, offset_tops: w.formation_tops || [] })
  return [out, offsets]
}
function analyse(well, radius = 10000, lookahead = 150) {
  const [evs, offsets] = offsetEvents(well, radius)
  const res = evaluate({ current_depth_m: well.current_depth_m || 0, formation_tops: well.formation_tops || [] }, evs, offsets.length, lookahead)
  res.offset_wells = offsets.sort((a, b) => a[1] - b[1]).map(([w, d]) => ({ id: w.id, name: w.name, distance_km: +(d / 1000).toFixed(2), status: w.status }))
  res.radius_m = radius
  return res
}
function persistAlerts(well, analysis) {
  const out = []
  for (const a of analysis.alerts) {
    const key = `${well.id}:${a.key}`
    if (S.alerts.some((x) => x.alert_key === key)) continue
    const row = { id: nextId(), alert_key: key, well_id: well.id, well_name: well.name, alert_type: a.event_type, severity: a.severity, title: a.title,
      message: a.message, recommendation: a.recommendation, formation: a.formation, expected_depth_m: a.expected_from_m,
      depth_at_alert_m: well.current_depth_m, evidence: a.what_worked, acknowledged: false, created_at: now() }
    S.alerts.push(row); out.push(row)
  }
  if (out.length) save()
  return out
}
function startDrillingSim() {
  if (timers.drill) return
  timers.drill = setInterval(() => {
    for (const w of allWells()) {
      if (!w.is_active || (w.planned_td_m && w.current_depth_m >= w.planned_td_m)) continue
      S.depths[w.id] = +(w.current_depth_m + 3).toFixed(1)
      const cur = { ...w, current_depth_m: S.depths[w.id] }
      emit({ type: 'depth', well_id: w.id, name: w.name, depth_m: cur.current_depth_m })
      for (const a of persistAlerts(cur, analyse(cur))) emit({ type: 'well_alert', ...a })
    }
    save()
  }, 4000)
}
const wellOr404 = (id) => allWells().find((w) => w.id === Number(id)) || fail(404, 'Well not found.')
const summary = (w) => ({ id: w.id, name: w.name, field: w.field, operator: w.operator, lat: w.lat, lon: w.lon, status: w.status, well_type: w.well_type,
  spud_year: w.spud_year, td_md_m: w.td_md_m, is_active: w.is_active, current_depth_m: w.current_depth_m, planned_td_m: w.planned_td_m,
  outcome: w.outcome, cum_oil_bbl: w.cum_oil_bbl, source: w.source })

// --------------------------------------------------------------------------- location detail
function rng(seed) { return () => { seed |= 0; seed = (seed + 0x6D2B79F5) | 0; let t = Math.imul(seed ^ (seed >>> 15), 1 | seed); t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t; return ((t ^ (t >>> 14)) >>> 0) / 4294967296 } }
function oilEstimate(lat, lon, pos, closure) {
  const near = snap.fields_full.map((f) => [f, geo.haversine(lat, lon, f.lat, f.lon)]).sort((a, b) => a[1] - b[1]).slice(0, 3)
  const blend = (k) => { let n = 0, d = 0; for (const [f, dist] of near) { const w = 1 / Math.max(dist, 500) ** 2; n += f[k] * w; d += w } return n / d }
  const phi = blend('porosity'), sw = blend('water_saturation'), bo = blend('formation_volume_factor'), pay = blend('net_pay_m'), rf = blend('recovery_factor')
  const cf = Math.min(1.25, Math.max(0.25, closure / 200))
  const r = rng(7), normal = (m, s) => m + s * Math.sqrt(-2 * Math.log(r() || 1e-9)) * Math.cos(2 * Math.PI * r())
  const tri = (a, c, b) => { const u = r(), f = (c - a) / (b - a); return u < f ? a + Math.sqrt(u * (b - a) * (c - a)) : b - Math.sqrt((1 - u) * (b - a) * (b - c)) }
  const rec = [], stoiip = []
  for (let i = 0; i < 2000; i++) {
    const A = tri(40, 80, 160), h = Math.max(1, normal(pay * cf, 0.25 * pay * cf)) * 3.28084
    const p = Math.min(0.35, Math.max(0.05, normal(phi, 0.02))), s = Math.min(0.9, Math.max(0.1, normal(sw, 0.05)))
    const b = Math.min(1.6, Math.max(1, normal(bo, 0.03))), f = Math.min(0.5, Math.max(0.05, normal(rf, 0.04)))
    const st = (7758 * A * h * p * (1 - s)) / b
    stoiip.push(st); rec.push(st * f)
  }
  rec.sort((a, b) => a - b); stoiip.sort((a, b) => a - b)
  const pct = (arr, q) => arr[Math.floor(q * (arr.length - 1))]
  const mean = rec.reduce((a, b) => a + b, 0) / rec.length
  return { method: 'Volumetric (STOIIP = 7758·A·h·φ·(1−Sw)/Bo) × recovery factor, 2,000 Monte Carlo runs',
    stoiip_p50_bbl: Math.round(pct(stoiip, 0.5)), recoverable_p90_bbl: Math.round(pct(rec, 0.1)), recoverable_p50_bbl: Math.round(pct(rec, 0.5)),
    recoverable_p10_bbl: Math.round(pct(rec, 0.9)), risked_recoverable_bbl: Math.round(mean * pos), chance_of_success: pos,
    inputs: { drainage_area_acres: '40–160 (most likely 80)', net_pay_m: +(pay * cf).toFixed(1), porosity: +phi.toFixed(3), water_saturation: +sw.toFixed(3),
      formation_volume_factor: +bo.toFixed(3), recovery_factor: +rf.toFixed(3), structural_closure_m: Math.round(closure), borrowed_from_fields: near.map(([f]) => f.name) },
    note: "Sample estimate for one well's drainage area. Real numbers need logs, core and a reservoir model." }
}

function texture(sand, silt, clay) {
  if (clay >= 40) return 'Clay'
  if (clay >= 27 && sand <= 45) return silt < 40 ? 'Clay loam' : 'Silty clay loam'
  if (clay >= 20 && sand > 45) return 'Sandy clay loam'
  if (silt >= 50) return 'Silt loam'
  if (sand >= 70) return sand < 85 ? 'Loamy sand' : 'Sand'
  if (sand >= 52) return 'Sandy loam'
  return 'Loam'
}
const soilCache = new Map()
let soilDownUntil = 0
async function soilAt(lat, lon, rockClass) {
  const key = `${lat.toFixed(2)},${lon.toFixed(2)}`
  if (soilCache.has(key)) return { ...soilCache.get(key), cached: true }
  let layers = null
  if (Date.now() > soilDownUntil) {
    try {
      const q = new URLSearchParams([['lon', lon], ['lat', lat], ['value', 'mean'], ...['clay', 'sand', 'silt', 'phh2o', 'bdod', 'soc'].map((p) => ['property', p]), ...['0-5cm', '30-60cm', '100-200cm'].map((d) => ['depth', d])])
      const ctl = new AbortController(); const t = setTimeout(() => ctl.abort(), 5000)
      const r = await fetch(`https://rest.isric.org/soilgrids/v2.0/properties/query?${q}`, { signal: ctl.signal })
      clearTimeout(t)
      const j = await r.json()
      layers = {}
      for (const l of j.properties.layers) for (const d of l.depths) if (d.values.mean !== null) (layers[d.label] = layers[d.label] || {})[l.name] = +(d.values.mean / (l.unit_measure.d_factor || 1)).toFixed(2)
      if (!Object.keys(layers).length) layers = null
    } catch { soilDownUntil = Date.now() + 300000 }
  }
  const live = !!layers
  if (!layers) {
    const w = Math.sin(lat * 57) * Math.cos(lon * 43)
    let [clay, sand, ph, bd] = rockClass === 'alluvium' ? [22 + 6 * w, 30 - 8 * w, 5.3, 1.38] : ['metamorphic', 'igneous'].includes(rockClass) ? [28 + 4 * w, 45 + 5 * w, 5.0, 1.3] : [32 + 5 * w, 36 + 6 * w, 4.9, 1.28]
    const top = { clay: +clay.toFixed(1), sand: +sand.toFixed(1), silt: +Math.max(5, 100 - clay - sand).toFixed(1), phh2o: ph, bdod: bd, soc: +(12 + 5 * w).toFixed(1) }
    layers = { '0-5cm': top, '30-60cm': { ...top, clay: +(top.clay * 1.1).toFixed(1) }, '100-200cm': { ...top, clay: +(top.clay * 1.1).toFixed(1) } }
  }
  const top = layers['0-5cm'] || Object.values(layers)[0]
  const notes = []
  if (top.clay >= 35) notes.push('High clay: ground turns soft and sticky when wet; build a compacted rig pad with crane mats.')
  if (top.sand >= 60) notes.push('Sandy soil drains fast but can wash out; line the cellar and waste pits.')
  if (top.bdod && top.bdod < 1.2) notes.push('Low bulk density: loose soil, check bearing capacity before moving the rig in.')
  if (!notes.length) notes.push('Normal soil for a rig pad with standard compaction.')
  const out = { source: live ? 'ISRIC SoilGrids v2.0 (live)' : 'Estimate from surface geology (SoilGrids not reachable)', is_live: live, layers,
    texture: texture(top.sand, top.silt, top.clay), ph: top.phh2o, notes,
    scope_note: 'Soil data covers only the top 2 m. It is used for surface safety (rig pad, roads, flooding), not for oil potential, which comes from geology and formation data.' }
  if (live) soilCache.set(key, out)
  return { ...out, cached: false }
}

const clamp = (x, a = 0, b = 1) => Math.max(a, Math.min(b, x))
const level = (s) => (s >= 60 ? 'High' : s >= 35 ? 'Medium' : 'Low')
function hazards(lat, lon, terrain, g, soil, near10, evCounts) {
  const slides = snap.layers.landslides.filter((s) => geo.haversine(lat, lon, s.lat, s.lon) <= 10000)
  const out = []
  const offset = (key, label, type, extra) => {
    if (!near10.length) return out.push({ key, label, score: 40, level: 'Medium', why: ['No offset wells within 10 km – unknown, treat with care', extra] })
    const n = evCounts[type] || 0, per = n / near10.length, s = 100 * clamp(0.15 + 0.45 * per)
    out.push({ key, label, score: Math.round(s), level: level(s), why: [`${n} such events in ${near10.length} offset wells within 10 km (${per.toFixed(1)} per well)`, extra] })
  }
  offset('gas_kick', 'Gas kick / overpressure', 'KICK', 'Kopili Shale is overpressured across Upper Assam')
  offset('mud_loss', 'Mud losses', 'MUD_LOSS', 'Depleted Tipam sands and fractured Sylhet limestone take losses')
  offset('stuck_pipe', 'Stuck pipe', 'STUCK_PIPE', 'Girujan Clay swells and Barail coal seams cave in')
  const weak = 1 - (g ? g.strength : 0.5)
  const ls = 100 * (0.35 * clamp(terrain.slope_deg / 30) + 0.15 * clamp(terrain.local_relief_m / 300) + 0.2 * weak + 0.1 * 0.8 + 0.2 * clamp(slides.length / 3))
  out.push({ key: 'landslide', label: 'Landslide', score: Math.round(ls), level: level(ls), why: [`Ground slope ${terrain.slope_deg.toFixed(1)}° and ${Math.round(terrain.local_relief_m)} m height change within 1 km`,
    `Rock/soil strength: ${weak > 0.6 ? 'weak' : weak > 0.35 ? 'moderate' : 'strong'} (${g ? g.name : 'unknown'})`, 'Heavy monsoon rain (June–September)',
    slides.length ? `${slides.length} recorded landslides within 10 km` : 'No recorded landslides within 10 km'] })
  const top = soil.layers['0-5cm'] || {}
  const producers = near10.filter(([w, d]) => d <= 3000 && ['producing', 'shut-in'].includes(w.status)).length
  const alluvial = g && g.rock_class === 'alluvium' ? 1 : 0.3
  const sub = 100 * (0.35 * clamp((top.clay || 25) / 45) + 0.35 * alluvial + 0.3 * clamp(producers / 3))
  out.push({ key: 'subsidence', label: 'Ground subsidence', score: Math.round(sub), level: level(sub), why: [`Surface clay about ${top.clay}%`, alluvial === 1 ? 'Soft alluvial ground' : 'Firm rock at surface', `${producers} producing wells within 3 km (fluid withdrawal)`] })
  let river = ['', Infinity]
  for (const rv of snap.layers.rivers) { const d = geo.distToPolyline(lat, lon, rv.line); if (d < river[1]) river = [rv.name, d] }
  const height = Math.max(0, terrain.elevation_m - (95 + 55 * (lon - 93.6) / 2.6))
  const fl = 100 * (0.55 * Math.exp(-(river[1] / 1000) / 8) + 0.45 * clamp(1 - height / 40))
  out.push({ key: 'flooding', label: 'Flooding', score: Math.round(fl), level: level(fl), why: [`${(river[1] / 1000).toFixed(1)} km from the ${river[0]}`, `About ${Math.round(height)} m above the valley floor`, 'Assam valley floods most monsoons (pad should be raised above the 100-year flood level)'] })
  out.push({ key: 'earthquake', label: 'Earthquake', score: 75, level: 'High', why: ['All of Assam is in Seismic Zone V (IS 1893), the highest in India', 'Design rig foundations and tanks for strong shaking'] })
  const lg = legality(lat, lon), nr = lg.nearest_restricted
  const eco = nr ? (nr.distance_m === 0 ? 100 : 100 * clamp(1 - nr.distance_m / 5000)) : 0
  out.push({ key: 'ecology', label: 'Wildlife / eco-sensitive area', score: Math.round(eco), level: level(eco), why: [nr ? `Nearest protected or restricted area: ${nr.name} (${(nr.distance_m / 1000).toFixed(1)} km)` : 'None nearby', 'Blowouts near wetlands cause lasting damage (e.g. Baghjan 2020)'] })
  return out
}

const FIELD_NOTES = {
  Digboi: "Asia's oldest producing oil field (oil struck in 1889); Digboi refinery commissioned 1901.",
  Naharkatiya: 'Discovered 1953; its success led to the formation of Oil India Limited in 1959.',
  Baghjan: 'May–June 2020: blowout and fire at well Baghjan-5, next to Dibru-Saikhowa NP and Maguri-Motapung wetland.',
  Lakwa: "One of ONGC's main onshore fields in Assam, producing since the late 1960s.",
}

async function locationDetail(lat, lon) {
  const r = snap.region
  if (lat < r.min_lat - 0.5 || lat > r.max_lat + 0.5 || lon < r.min_lon - 0.5 || lon > r.max_lon + 0.5) fail(400, 'This prototype only has data for Upper Assam and nearby areas.')
  const c = cellAt(lat, lon)
  const [, , prob, conf, closure, tipam, ratio, n10, kmProd, elev, slope, relief] = c
  const terrain = { elevation_m: elev, slope_deg: slope, local_relief_m: relief, source: 'Modelled terrain (browser demo: precomputed 2.7 km grid)' }
  const g = geologyAt(lat, lon)
  const soil = await soilAt(lat, lon, g?.rock_class)
  const legal = legality(lat, lon)
  const near = wellsWithin(lat, lon, 10000)
  const ids = new Set(near.map(([w]) => w.id))
  const events = allEvents().filter((e) => ids.has(e.well_id))
  const evCounts = events.reduce((a, e) => ({ ...a, [e.event_type]: (a[e.event_type] || 0) + 1 }), {})
  const success = {
    probability: prob, score: Math.round(prob * 100), label: prob >= 0.6 ? 'Good' : prob >= 0.4 ? 'Fair' : 'Poor', confidence: conf,
    confidence_label: conf >= 0.66 ? 'High' : conf >= 0.45 ? 'Medium' : 'Low',
    features: { structural_closure_m: closure, depth_to_tipam_m: tipam, success_ratio_10km: ratio, wells_within_10km: n10, km_to_nearest_producer: kmProd },
    reasons: [closure > 60 ? `Structural high of about ${Math.round(closure)} m on the sample seismic map` : 'No clear structural high here (oil has nowhere to collect)',
      `Tipam reservoir expected at about ${Math.round(tipam)} m`, `${Math.round(ratio * 100)}% of nearby wells found oil (${n10} wells within 10 km)`,
      `Nearest producing well is ${kmProd} km away`, ...(n10 === 0 ? ['Few wells nearby, so the model is less sure here'] : [])],
  }
  const oil = oilEstimate(lat, lon, prob, closure)
  const st = snap.parcel_step
  const code = `AS-${String(Math.floor((lat - r.min_lat) / st)).padStart(2, '0')}${String(Math.floor((lon - r.min_lon) / st)).padStart(3, '0')}`
  const pr = snap.parcels[code]
  const hist = pr ? pr[3].map(([from, to, holder, type]) => ({ from, to, holder, type })) : []
  const illegalName = legal.zones.find((z) => !z.legal_to_drill)?.name
  let own = { status: 'unknown', statement: 'No land record found for this point.' }
  if (pr) {
    const [village, status, holder] = pr
    const since = [...hist].reverse().find((h) => h.to === null)?.from
    own = { parcel: code, village, status, holder, history: hist, source: 'Sample data (no open land-record dataset)' }
    if (status === 'unclaimed') {
      const past = hist.filter((h) => h.to)
      const pt = past.length ? ` It was held by ${past[past.length - 1].holder} (${past[past.length - 1].from}–${past[past.length - 1].to}), but that has lapsed.` : ' No past owner or lease on record.'
      own.statement = legal.verdict === 'LEGAL' ? `Unclaimed land.${pt} The zone is legal, so work can go ahead (after the usual permits).`
        : legal.verdict === 'NEEDS_LICENCE' ? `Unclaimed land.${pt} The area is not restricted, but a petroleum licence is needed before work can start.`
          : `No private owner, but this point is inside ${illegalName}. Work cannot go ahead.`
      own.can_proceed = legal.verdict === 'LEGAL'
    } else if (status === 'owned') { own.statement = `Owned by ${holder}${since ? ` since ${since}` : ''}. You need the owner's consent or land acquisition (RFCTLARR Act, 2013) before work.`; own.can_proceed = false }
    else if (status === 'leased') { own.statement = `Leased to ${holder}${since ? ` since ${since}` : ''}. Work needs the leaseholder's agreement.`; own.can_proceed = false }
    else if (legal.verdict === 'ILLEGAL') { own.statement = `Government land held by ${holder}, inside ${illegalName}. Work cannot go ahead.`; own.can_proceed = false }
    else { own.statement = `Government land held by ${holder}. Needs government allotment before work.`; own.can_proceed = false }
  }
  const fields = snap.fields_full.map((f) => [f, geo.haversine(lat, lon, f.lat, f.lon)]).sort((a, b) => a[1] - b[1]).slice(0, 2)
  const near5 = near.filter(([, d]) => d <= 5000)
  const sum = []
  sum.push(near5.length ? `${near5.length} well${near5.length > 1 ? 's' : ''} drilled within 5 km since ${Math.min(...near5.map(([w]) => w.spud_year || 9999))}.` : 'No wells drilled within 5 km – this is untested ground.')
  const topTypes = Object.entries(evCounts).sort((a, b) => b[1] - a[1]).slice(0, 2)
  if (topTypes.length) sum.push(`Most common problems nearby: ${topTypes.map(([t, n]) => `${t.replace('_', ' ').toLowerCase()} (${n})`).join(', ')}.`)
  if (fields[0][1] < 15000) sum.push(`Closest field: ${fields[0][0].name} (${fields[0][0].operator}), discovered ${fields[0][0].discovery_year}.`)
  const strat = snap.stratigraphy
  const withTops = near.filter(([w]) => w.formation_tops?.length && strat.some((s) => s.name === w.formation_tops[0].name)).slice(0, 4)
  let column, method
  if (withTops.length) {
    column = strat.map((s) => {
      const vals = withTops.map(([w, d]) => [w.formation_tops.find((t) => t.name === s.name), 1 / Math.max(d, 300) ** 2]).filter(([t]) => t)
      if (!vals.length) return null
      const ws = vals.reduce((a, [, w]) => a + w, 0)
      return { name: s.name, top_m: Math.round(vals.reduce((a, [t, w]) => a + t.top_m * w, 0) / ws), bottom_m: Math.round(vals.reduce((a, [t, w]) => a + t.bottom_m * w, 0) / ws), lithology: s.lithology }
    }).filter(Boolean)
    method = `Weighted average of ${withTops.length} nearby wells (${withTops.map(([w]) => w.name).join(', ')})`
  } else {
    const idx = strat.findIndex((s) => s.name === 'Tipam Sandstone')
    const scale = tipam / strat.slice(0, idx).reduce((a, s) => a + s.mean_thickness, 0)
    let d = 0
    column = strat.map((s, i) => { const t = s.mean_thickness * (i < idx ? scale : 1); const row = { name: s.name, top_m: Math.round(d), bottom_m: Math.round(d + t), lithology: s.lithology }; d += t; return row })
    method = 'Hung from the sample seismic structure map (no wells within 5 km)'
  }
  return {
    lat, lon, sample_data: true,
    history: {
      wells: near.slice(0, 8).map(([w, d]) => ({ id: w.id, name: w.name, distance_km: +(d / 1000).toFixed(2), spud_year: w.spud_year, operator: w.operator, status: w.status, outcome: w.outcome })),
      event_counts: evCounts,
      fields: fields.map(([f, d]) => ({ name: f.name, distance_km: +(d / 1000).toFixed(1), operator: f.operator, discovered: f.discovery_year, past_operators: f.past_operators, note: FIELD_NOTES[f.name] })),
      landslides: snap.layers.landslides.map((s) => [s, geo.haversine(lat, lon, s.lat, s.lon)]).filter(([, d]) => d <= 10000).sort((a, b) => a[1] - b[1]).slice(0, 5)
        .map(([s, d]) => ({ date: s.event_date, place: s.place, size: s.size, distance_km: +(d / 1000).toFixed(1) })),
      land_use: hist.map((h) => `${h.from}${h.to ? '–' + h.to : '–now'}: ${h.holder} (${h.type})`),
      summary: sum.join(' '),
    },
    terrain, geology: { surface: g, subsurface: { column, method, main_targets: ['Tipam Sandstone', 'Barail'] } }, soil, success,
    hazards: hazards(lat, lon, terrain, g, soil, near, evCounts), legality: legal, oil_estimate: oil, ownership: own,
    sources: [terrain.source, soil.source, g?.source, fields[0][0].source, 'Land records: sample data (no open dataset)'].filter(Boolean).sort(),
  }
}

// --------------------------------------------------------------------------- analytics
function overview() {
  const wells = allWells(), events = allEvents()
  const count = (arr, f) => arr.reduce((a, x) => { const k = f(x); a[k] = (a[k] || 0) + 1; return a }, {})
  const perPeriod = {}
  for (const e of events) if (e.event_date) { const y = Math.floor(+e.event_date.slice(0, 4) / 5) * 5; (perPeriod[y] = perPeriod[y] || {})[e.event_type] = (perPeriod[y]?.[e.event_type] || 0) + 1 }
  const npt = {}
  for (const e of events) npt[e.formation || 'Unknown'] = (npt[e.formation || 'Unknown'] || 0) + (e.npt_hours || 0)
  const fr = {}
  const wById = Object.fromEntries(wells.map((w) => [w.id, w]))
  for (const w of wells) { const k = w.field || 'Exploration / other'; (fr[k] = fr[k] || { wells: 0, events: 0, high: 0 }).wells++ }
  for (const e of events) { const w = wById[e.well_id]; const k = w?.field || 'Exploration / other'; fr[k] = fr[k] || { wells: 0, events: 0, high: 0 }; fr[k].events++; fr[k].high += e.severity === 'high' ? 1 : 0 }
  const week = Date.now() - 7 * 86400000
  return {
    kpis: { wells: wells.length, active_wells: wells.filter((w) => w.is_active).length, events: events.length, npt_hours: Math.round(events.reduce((a, e) => a + (e.npt_hours || 0), 0)),
      drillers: S.drillers.length, pending_approvals: S.drillers.filter((p) => p.status === 'submitted').length, open_alerts: S.alerts.filter((a) => !a.acknowledged).length,
      breaches_7d: S.breaches.filter((b) => new Date(b.created_at).getTime() >= week && b.is_breach).length },
    wells_by_status: count(wells, (w) => w.status), wells_by_outcome: count(wells, (w) => w.outcome), events_by_type: count(events, (e) => e.event_type),
    events_by_period: Object.keys(perPeriod).sort().map((y) => ({ period: `${y}–${+y + 4}`, ...perPeriod[y] })),
    npt_by_formation: Object.entries(npt).sort((a, b) => b[1] - a[1]).map(([formation, h]) => ({ formation, npt_hours: Math.round(h) })),
    field_risk: Object.entries(fr).map(([field, v]) => ({ field, ...v, events_per_well: +(v.events / Math.max(1, v.wells)).toFixed(1) })).sort((a, b) => b.events_per_well - a.events_per_well),
    drillers_by_status: count(S.drillers, (p) => p.status),
  }
}

// --------------------------------------------------------------------------- router
const routes = []
const on = (method, pattern, fn) => routes.push([method, new RegExp(`^${pattern.replace(/:(\w+)/g, '(?<$1>[^/]+)')}$`), fn])

on('POST', '/api/auth/login', ({ body }) => {
  const u = S.users.find((x) => x.email === (body.email || '').trim().toLowerCase())
  if (!u || u.password !== body.password) fail(401, 'Wrong email or password.')
  return { token: tokenFor(u), user: userDict(u) }
})
on('POST', '/api/auth/register', ({ body }) => {
  const email = (body.email || '').trim().toLowerCase()
  if (!/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(email)) fail(422, 'Enter a valid email.')
  if ((body.password || '').length < 8) fail(422, 'Password must be at least 8 characters.')
  if (S.users.some((u) => u.email === email)) fail(409, 'An account with this email already exists.')
  const u = { id: nextId(), email, full_name: body.full_name.trim(), role: 'driller', password: body.password }
  S.users.push(u)
  S.drillers.push({ id: nextId(), user_id: u.id, status: 'draft', documents: [], equipment: [], site_lat: null, site_lon: null })
  save()
  return { token: tokenFor(u), user: userDict(u) }
})
on('GET', '/api/auth/me', ({ user }) => userDict(need(user)))

on('GET', '/api/driller/me', ({ user }) => profile(myProfile(need(user, 'driller'))))
on('GET', '/api/driller/doc-types', () => snap.doc_types)
on('PUT', '/api/driller/profile', ({ user, body }) => { const p = myProfile(need(user, 'driller')); editable(p); Object.assign(p, body); save(); return profile(p) })
on('PUT', '/api/driller/work-area', ({ user, body }) => {
  const p = myProfile(need(user, 'driller')); editable(p)
  if (!(body.work_radius_m > 0)) fail(422, 'Working radius must be positive.')
  Object.assign(p, body); if (p.last_lat === null || p.last_lat === undefined) { p.last_lat = p.site_lat; p.last_lon = p.site_lon }
  save(); return profile(p)
})
on('POST', '/api/driller/equipment', ({ user, body }) => {
  const p = myProfile(need(user, 'driller')); editable(p)
  if (!(body.max_horizontal_reach_m > 0) || !(body.max_depth_m > 0)) fail(422, 'Depth and reach must be positive.')
  p.equipment.push({ id: nextId(), ...body }); save(); return profile(p)
})
on('DELETE', '/api/driller/equipment/:id', ({ user, params }) => {
  const p = myProfile(need(user, 'driller')); editable(p)
  p.equipment = p.equipment.filter((e) => e.id !== Number(params.id)); save(); return profile(p)
})
on('POST', '/api/driller/documents', ({ user, body }) => {
  const p = myProfile(need(user, 'driller')); editable(p)
  const type = body.get('doc_type'), file = body.get('file')
  if (!snap.doc_types.types[type]) fail(400, 'Unknown document type.')
  if (!/\.(pdf|png|jpe?g)$/i.test(file?.name || '')) fail(400, 'Upload a PDF, PNG or JPG file.')
  p.documents = p.documents.filter((d) => d.doc_type !== type)
  p.documents.push({ id: nextId(), doc_type: type, label: snap.doc_types.types[type], filename: file.name, status: 'pending', note: null, uploaded_at: now(), reviewed_at: null, has_file: false })
  if (p.status === 'approved') { p.status = 'submitted'; p.submitted_at = now() }
  save(); return profile(p)
})
on('POST', '/api/driller/submit', ({ user }) => {
  const p = myProfile(need(user, 'driller'))
  const missing = checklist(p).filter((c) => !c.done).map((c) => c.label)
  if (missing.length) fail(400, `Please complete: ${missing.join(', ')}`)
  Object.assign(p, { status: 'submitted', submitted_at: now(), review_note: null }); save(); return profile(p)
})
on('GET', '/api/driller/breaches', ({ user }) => S.breaches.filter((b) => b.user_id === need(user, 'driller').id).sort((a, b) => b.created_at.localeCompare(a.created_at)))

on('GET', '/api/admin/drillers', ({ user }) => {
  need(user, 'admin', 'engineer')
  const order = { submitted: 0, draft: 1, rejected: 2, approved: 3 }
  return S.drillers.map(profile).sort((a, b) => order[a.status] - order[b.status] || a.full_name.localeCompare(b.full_name))
})
on('GET', '/api/admin/drillers/:id', ({ user, params }) => { need(user, 'admin', 'engineer'); return profile(S.drillers.find((d) => d.id === Number(params.id)) || fail(404, 'Not found.')) })
on('POST', '/api/admin/drillers/:id/decision', ({ user, params, body }) => {
  need(user, 'admin')
  const p = S.drillers.find((d) => d.id === Number(params.id)) || fail(404, 'Not found.')
  if (body.decision === 'approve') {
    const pending = p.documents.filter((d) => d.status !== 'approved').map((d) => d.doc_type)
    if (pending.length) fail(400, `Approve or reject every document first. Not approved yet: ${pending.join(', ')}`)
    if (!p.equipment.length || p.site_lat === null || p.site_lat === undefined) fail(400, 'The driller has not declared equipment and a working area.')
  } else if (!body.note) fail(400, 'Please add a note saying why the registration is rejected.')
  Object.assign(p, { status: body.decision === 'approve' ? 'approved' : 'rejected', review_note: body.note, reviewed_at: now() }); save(); return profile(p)
})
on('POST', '/api/admin/documents/:id/decision', ({ user, params, body }) => {
  need(user, 'admin')
  for (const p of S.drillers) {
    const d = p.documents.find((x) => x.id === Number(params.id))
    if (d) { if (body.status === 'rejected' && !body.note) fail(400, 'Please add a note saying why the document is rejected.'); Object.assign(d, { status: body.status, note: body.note, reviewed_at: now() }); save(); return d }
  }
  fail(404, 'Not found.')
})
on('GET', '/api/admin/documents/:id/file', () => fail(404, 'The browser demo does not store uploaded files.'))

on('POST', '/api/tracking/position', ({ user, body }) => processPosition(need(user, 'driller'), body.lat, body.lon, false))
const simTarget = (user, body) => (user.role === 'driller' ? user.id : body.user_id || fail(400, 'Pick a driller.'))
on('POST', '/api/tracking/simulator/start', ({ user, body }) => { const id = simTarget(need(user), body || {}); startSim(id); return { running: true, user_id: id } })
on('POST', '/api/tracking/simulator/stop', ({ user, body }) => { const id = simTarget(need(user), body || {}); stopSim(id); return { running: false, user_id: id } })
on('GET', '/api/tracking/simulator/status', ({ user }) => (need(user).role === 'driller' ? { running: !!timers.sims[user.id] } : { running: Object.fromEntries(S.drillers.map((p) => [p.user_id, !!timers.sims[p.user_id]])) }))
on('GET', '/api/tracking/live', ({ user }) => {
  need(user)
  return S.drillers.filter((p) => p.site_lat !== null && p.site_lat !== undefined && (user.role !== 'driller' || p.user_id === user.id)).map((p) => {
    const u = S.users.find((x) => x.id === p.user_id)
    return { user_id: p.user_id, driller_id: p.id, name: u.full_name, company: p.company_name, status: p.status, tracking_status: p.tracking_status,
      lat: p.last_lat, lon: p.last_lon, last_seen_at: p.last_seen_at, simulator_running: !!timers.sims[p.user_id], zone: allowedZone(p), trail: S.trails[p.user_id] || [] }
  })
})
on('GET', '/api/tracking/breaches', ({ user, query }) => { need(user, 'admin', 'engineer'); return [...S.breaches].sort((a, b) => b.created_at.localeCompare(a.created_at)).slice(0, Number(query.limit) || 100) })
on('POST', '/api/tracking/breaches/:id/ack', ({ user, params }) => { need(user, 'admin', 'engineer'); const b = S.breaches.find((x) => x.id === Number(params.id)); if (b) b.acknowledged = true; save(); return { ok: true } })

on('GET', '/api/wells', ({ user, query }) => {
  need(user)
  const counts = allEvents().reduce((a, e) => ({ ...a, [e.well_id]: (a[e.well_id] || 0) + 1 }), {})
  return allWells().filter((w) => query.active === undefined || String(w.is_active) === query.active).sort((a, b) => a.name.localeCompare(b.name)).map((w) => ({ ...summary(w), event_count: counts[w.id] || 0 }))
})
on('GET', '/api/wells/:id', ({ user, params }) => {
  need(user); const w = wellOr404(params.id)
  return { ...w, events: allEvents().filter((e) => e.well_id === w.id).sort((a, b) => a.depth_m - b.depth_m), depth_logs: [] }
})
on('GET', '/api/wells/:id/offsets', ({ user, params, query }) => {
  need(user); const w = wellOr404(params.id)
  return { ...analyse(w, (Number(query.radius_km) || 10) * 1000, Number(query.lookahead_m) || 150), well: { ...summary(w), formation_tops: w.formation_tops } }
})
on('GET', '/api/wells/:id/correlation', ({ user, params, query }) => {
  need(user); const w = wellOr404(params.id)
  const others = wellsWithin(w.lat, w.lon, (Number(query.radius_km) || 10) * 1000, w.id).slice(0, Number(query.max_wells) || 6)
  const events = allEvents()
  return { well_id: w.id, columns: [[w, 0], ...others].map(([o, d]) => ({ id: o.id, name: o.name, distance_km: +(d / 1000).toFixed(2), is_active: o.is_active,
    current_depth_m: o.current_depth_m, td_m: o.td_md_m || o.planned_td_m, formation_tops: o.formation_tops,
    events: events.filter((e) => e.well_id === o.id).map((e) => ({ id: e.id, type: e.event_type, depth_m: e.depth_m, severity: e.severity, formation: e.formation, description: e.description })), logs: [] })) }
})
on('GET', '/api/wells/:id/risk-profile', ({ user, params }) => {
  need(user); const w = wellOr404(params.id)
  const prof = snap.risk_profiles[w.id]
  if (!prof) return { well_id: w.id, points: [], explanation: 'Risk curves are only precomputed for the active wells in the browser demo.' }
  const start = Math.floor((w.current_depth_m || 0) / 50) * 50
  return { ...prof, from_m: w.current_depth_m, points: prof.points.filter((p) => p.depth_m >= start) }
})
on('POST', '/api/wells/:id/depth', ({ user, params, body }) => {
  need(user, 'admin', 'engineer'); const w = wellOr404(params.id)
  if (!w.is_active) fail(400, 'Only active wells have a live depth.')
  S.depths[w.id] = Number(body.depth_m); save()
  const cur = { ...w, current_depth_m: S.depths[w.id] }
  emit({ type: 'depth', well_id: w.id, name: w.name, depth_m: cur.current_depth_m })
  const a = analyse(cur)
  for (const x of persistAlerts(cur, a)) emit({ type: 'well_alert', ...x })
  return { depth_m: cur.current_depth_m, alerts: a.alerts }
})
on('GET', '/api/events', ({ user, query }) => {
  need(user)
  const wells = Object.fromEntries(allWells().map((w) => [w.id, w]))
  const q = (query.q || '').toLowerCase().trim(), types = query.event_type ? query.event_type.split(',') : null
  const lat = query.lat !== undefined ? Number(query.lat) : null, lon = query.lon !== undefined ? Number(query.lon) : null
  const out = []
  for (const e of allEvents()) {
    const w = wells[e.well_id]
    if (!w) continue
    if (q && !`${e.description} ${e.cause} ${e.action_taken} ${e.lesson} ${e.formation} ${w.name}`.toLowerCase().includes(q)) continue
    if (types && !types.includes(e.event_type)) continue
    if (query.formation && e.formation !== query.formation) continue
    if (query.well_id && e.well_id !== Number(query.well_id)) continue
    if (query.severity && e.severity !== query.severity) continue
    const d = lat !== null ? geo.haversine(lat, lon, w.lat, w.lon) : null
    if (query.radius_km && d !== null && d > Number(query.radius_km) * 1000) continue
    out.push({ ...e, well_name: w.name, distance_km: d !== null ? +(d / 1000).toFixed(2) : null })
  }
  out.sort((a, b) => (a.distance_km ?? 0) - (b.distance_km ?? 0) || a.well_name.localeCompare(b.well_name) || a.depth_m - b.depth_m)
  return { total: out.length, items: out.slice(0, Number(query.limit) || 200), facets: {} }
})
on('GET', '/api/alerts', ({ user, query }) => {
  need(user)
  return S.alerts.filter((a) => (!query.well_id || a.well_id === Number(query.well_id)) && (query.open_only !== 'true' || !a.acknowledged)).sort((a, b) => b.created_at.localeCompare(a.created_at)).slice(0, 200)
})
on('POST', '/api/alerts/:id/ack', ({ user, params }) => { need(user); const a = S.alerts.find((x) => x.id === Number(params.id)); if (a) a.acknowledged = true; save(); return { ok: true } })

on('GET', '/api/map/layers', ({ user }) => {
  need(user)
  return { ...snap.layers, wells: allWells().map((w) => ({ ...summary(w), bhl: w.trajectory?.bhl_lat ? [w.trajectory.bhl_lat, w.trajectory.bhl_lon] : null })) }
})
on('GET', '/api/map/location', ({ user, query }) => { need(user); return locationDetail(Number(query.lat), Number(query.lon)) })
on('GET', '/api/map/untapped', ({ user }) => { need(user); return snap.untapped })
on('GET', '/api/ml/explain', ({ user }) => { need(user); return snap.explain })
on('GET', '/api/analytics/overview', ({ user }) => { need(user, 'admin', 'engineer'); return overview() })
on('GET', '/api/meta/sources', () => snap.sources)
on('GET', '/api/documents/mode', ({ user }) => { need(user); return { llm_enabled: false, text: 'Rule-based extraction in your browser (hosted demo). The full backend can use Claude with an API key.' } })
on('GET', '/api/documents', ({ user }) => { need(user); return [...S.documents].reverse() })
on('POST', '/api/documents/extract', async ({ user, body }) => {
  need(user, 'admin', 'engineer')
  const file = body.get('file')
  const [text, method] = await fileText(file)
  if (!text.trim()) fail(400, 'No text could be read from this file (scanned PDFs need OCR on the full backend).')
  const x = ruleExtract(text)
  const warnings = []
  const doc = { id: nextId(), filename: file.name, status: 'processed', text_method: method, extract_method: 'rules', text_excerpt: text.slice(0, 3000), extracted: x, well_id: null, well_name: null, events_created: 0, warnings, created_at: now() }
  if (!x.well_name) warnings.push('No well name found, so events were not linked to a well.')
  else {
    let w = allWells().find((v) => v.name.toLowerCase() === x.well_name.toLowerCase())
    const tops = [...x.formations].sort((a, b) => a.top_m - b.top_m)
    const topsFull = tops.map((t, i) => ({ name: t.name, top_m: t.top_m, bottom_m: tops[i + 1]?.top_m ?? (x.total_depth_m || t.top_m + 200) }))
    if (!w) {
      let lat = x.lat, lon = x.lon
      const field = x.field && snap.fields_full.find((f) => f.name.toLowerCase() === x.field.toLowerCase())
      if ((!lat || !lon) && field) { [lat, lon] = geo.destination(field.lat, field.lon, 45, 1500); warnings.push(`No coordinates in the report; the well was placed next to the ${field.name} field centre.`) }
      if (lat && lon) {
        w = { id: nextId(), name: x.well_name, field: field?.name || x.field, operator: x.operator || field?.operator, lat, lon, status: 'unknown', well_type: 'vertical',
          spud_year: +(x.report_date || '').slice(0, 4) || null, td_md_m: x.total_depth_m, is_active: false, outcome: null, formation_tops: topsFull, source: `Extracted from ${file.name}` }
        S.extraWells.push(w)
      } else warnings.push('No coordinates or known field in the report; the well was not added to the map.')
    }
    if (w) {
      for (const e of x.events) {
        if (e.depth_m === null) { warnings.push(`Skipped a ${e.event_type} event without a depth.`); continue }
        S.extraEvents.push({ id: nextId(), well_id: w.id, event_type: e.event_type, label: e.event_type, depth_m: e.depth_m, formation: e.formation, event_date: x.report_date,
          severity: severityFrom(e.event_type, e.npt_hours), npt_hours: e.npt_hours, description: e.description, cause: e.cause, action_taken: e.action_taken,
          lesson: e.lesson || x.lessons[0] || null, source: `Extracted from ${file.name}`, document_id: doc.id })
        doc.events_created++
      }
      doc.well_id = w.id; doc.well_name = w.name
    }
  }
  S.documents.push(doc); save()
  return doc
})

// --------------------------------------------------------------------------- entry points
export default {
  async handle(method, url, body, token) {
    await load()
    const [path, qs] = url.split('?')
    const query = Object.fromEntries(new URLSearchParams(qs || ''))
    for (const [m, rx, fn] of routes) {
      const match = m === method && rx.exec(path)
      if (match) return clone(await fn({ user: userFrom(token), body, query, params: match.groups || {} }))
    }
    fail(404, `No demo route for ${method} ${path}`)
  },
  subscribe(fn) {
    subscribers.add(fn)
    load()
    const close = () => subscribers.delete(fn)
    close.send = () => {}
    return close
  },
  reset() { try { localStorage.removeItem(STORE_KEY) } catch { /* ignore */ } },
}
