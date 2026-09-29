// JavaScript port of backend/app/services/alerts.py
const WEIGHT = { low: 1, medium: 2, high: 3 }
const REC = {
  MUD_LOSS: 'Mix and hold 100 bbl of LCM pill before {d} m, add 15-20 ppb LCM to the active system 50 m above, keep ECD low (reduce flow rate, slow trips).',
  KICK: 'Raise mud weight by 0.3-0.5 ppg before {d} m, run flow checks on every drilling break, keep the trip tank lined up and watch pit volume, gas and d-exponent closely.',
  STUCK_PIPE: 'Keep the string moving, back-ream each stand, pump hi-vis sweeps and check hole-cleaning before {d} m. Have jars in the BHA.',
  TORQUE_SPIKE: 'Lower RPM and WOB when torque rises near {d} m, add lubricant, and consider an anti-balling PDC bit.',
  CEMENTING: 'Plan a lightweight lead slurry and extra centralisers across the zone near {d} m; run a CBL after the job.',
  FISHING: 'Inspect drill-string and BHA before drilling past {d} m; keep a fishing tool kit on site.',
  NPT: 'Check spares and logistics before reaching {d} m.',
}
export const LABELS = { MUD_LOSS: 'Mud loss', KICK: 'Kick / overpressure', STUCK_PIPE: 'Stuck pipe', TORQUE_SPIKE: 'Torque spike',
  CEMENTING: 'Cementing problem', FISHING: 'Fishing job', NPT: 'Non-productive time' }

export function correlateDepth(depth, fm, offTops, actTops) {
  const off = fm && offTops.find((t) => t.name === fm)
  const act = fm && actTops.find((t) => t.name === fm)
  if (off && act && off.bottom_m > off.top_m) {
    const f = Math.min(1, Math.max(0, (depth - off.top_m) / (off.bottom_m - off.top_m)))
    return [act.top_m + f * (act.bottom_m - act.top_m), 'formation match']
  }
  return [depth, 'depth match']
}

function severity(g, nOffsets) {
  let score = 0
  for (const [e] of g.events) score += (WEIGHT[e.severity] || 2) / (1 + e.distance_m / 2000)
  const wells = new Set(g.events.map(([e]) => e.well_name))
  const share = wells.size / Math.max(1, nOffsets)
  if (g.type === 'KICK' && wells.size >= 2) return 'high'
  if (score >= 4 || share >= 0.5) return 'high'
  if (score >= 1.8 || wells.size >= 2) return 'medium'
  return 'low'
}

export function evaluate(active, events, nOffsets, lookahead = 150) {
  const depth = active.current_depth_m
  const groups = new Map()
  for (const e of events) {
    if (e.event_type === 'NPT') continue
    const [d, method] = correlateDepth(e.depth_m, e.formation, e.offset_tops, active.formation_tops)
    const key = `${e.event_type}:${e.formation}`
    if (!groups.has(key)) groups.set(key, { type: e.event_type, formation: e.formation, min: d, max: d, events: [], method })
    const g = groups.get(key)
    g.min = Math.min(g.min, d); g.max = Math.max(g.max, d); g.events.push([e, d])
  }
  const alerts = [], upcoming = []
  for (const [key, g] of groups) {
    const sev = severity(g, nOffsets)
    const ahead = g.min - depth
    const state = depth > g.max + 25 ? 'PASSED' : (g.min - 25 <= depth && depth <= g.max + 25) ? 'IN_ZONE' : ahead <= lookahead ? 'APPROACHING' : 'AHEAD'
    const ev = [...g.events].sort((a, b) => a[0].distance_m - b[0].distance_m)
    const wells = [...new Set(g.events.map(([e]) => e.well_name))].sort()
    const lessons = ev.map(([e]) => e.lesson).filter(Boolean)
    const range = Math.round(g.min) === Math.round(g.max) ? `${Math.round(g.min)} m` : `${Math.round(g.min)}–${Math.round(g.max)} m`
    const item = {
      key, event_type: g.type, label: LABELS[g.type], formation: g.formation, severity: sev, state,
      expected_from_m: Math.round(g.min), expected_to_m: Math.round(g.max), distance_ahead_m: Math.round(ahead), wells,
      event_count: g.events.length, method: g.method,
      title: `${LABELS[g.type]} expected in ${g.formation || 'this interval'} at ${range}`,
      message: `${g.events.length} ${LABELS[g.type].toLowerCase()} event(s) in ${wells.length} offset well(s): ${wells.slice(0, 4).join(', ')}.`,
      recommendation: (REC[g.type] || '').replace('{d}', Math.round(g.min)),
      what_worked: ev.slice(0, 3).map(([e]) => ({ well: e.well_name, distance_km: +(e.distance_m / 1000).toFixed(1), depth_m: e.depth_m, action: e.action_taken, lesson: e.lesson })),
      top_lesson: lessons[0] || null,
    }
    if (state === 'APPROACHING' || state === 'IN_ZONE') alerts.push(item)
    if (state !== 'PASSED') upcoming.push(item)
  }
  const order = { high: 0, medium: 1, low: 2 }
  alerts.sort((a, b) => order[a.severity] - order[b.severity] || a.distance_ahead_m - b.distance_ahead_m)
  upcoming.sort((a, b) => a.expected_from_m - b.expected_from_m)
  return { current_depth_m: depth, lookahead_m: lookahead, alerts, upcoming, next_zone: upcoming.find((u) => u.state === 'APPROACHING' || u.state === 'AHEAD') || null }
}
