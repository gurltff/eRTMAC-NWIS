import { useState } from 'react'
import { EVENT_META } from '../lib/util'

// Lithology-style fills (geological convention), always labelled in the band.
export const FORMATION_FILL = {
  Alluvium: '#eadfbf', Dhekiajuli: '#dcc590', Namsang: '#cfb074', 'Girujan Clay': '#a88a6c', 'Tipam Sandstone': '#f1d97e',
  Barail: '#86725f', 'Kopili Shale': '#5f544b', 'Sylhet Limestone': '#aec4cb', Langpar: '#c9b28d', Basement: '#d8a9a4',
}
const DARK_TEXT = new Set(['Alluvium', 'Dhekiajuli', 'Namsang', 'Tipam Sandstone', 'Sylhet Limestone', 'Langpar', 'Basement'])

/**
 * Offset wells side by side, depth down the page. Formation bands are joined
 * between neighbouring columns so the correlation is visible; problems are
 * dots at their depth, coloured by type. The active well shows the bit depth
 * and the upcoming risk windows from the alert engine.
 */
export default function Correlation({ columns, currentDepth, upcoming = [], onEvent }) {
  const [hover, setHover] = useState(null)
  const colW = 92, gap = 58, top = 44, height = 560
  const maxDepth = Math.max(...columns.map((c) => Math.max(c.td_m || 0, ...(c.formation_tops || []).map((t) => t.bottom_m))), 1000)
  const y = (d) => top + (d / maxDepth) * height
  const width = columns.length * (colW + gap)
  const ticks = []
  for (let d = 0; d <= maxDepth; d += 500) ticks.push(d)

  return (
    <div style={{ position: 'relative', overflowX: 'auto' }}>
      <svg width={Math.max(width + 40, 400)} height={top + height + 20} role="img" aria-label="Formation correlation of offset wells">
        {ticks.map((d) => (
          <g key={d}>
            <line x1={34} x2={width + 30} y1={y(d)} y2={y(d)} stroke="var(--grid)" strokeWidth="1" />
            <text x={30} y={y(d) + 4} textAnchor="end" fontSize="10" fill="var(--muted)" className="num">{d}</text>
          </g>
        ))}
        <text x={30} y={top - 26} textAnchor="end" fontSize="10" fill="var(--muted)">m</text>
        {columns.map((c, i) => {
          const x = 40 + i * (colW + gap)
          const next = columns[i + 1]
          const nx = 40 + (i + 1) * (colW + gap)
          const tdY = y(c.td_m || c.current_depth_m || 0)
          return (
            <g key={c.id}>
              {/* correlation ribbons to the next well */}
              {next && (c.formation_tops || []).map((t) => {
                const n = (next.formation_tops || []).find((u) => u.name === t.name)
                if (!n) return null
                return <path key={t.name} d={`M${x + colW} ${y(t.top_m)} L${nx} ${y(n.top_m)} L${nx} ${y(n.bottom_m)} L${x + colW} ${y(t.bottom_m)} Z`}
                  fill={FORMATION_FILL[t.name] || '#ccc'} opacity="0.28" />
              })}
              <text x={x + colW / 2} y={top - 24} textAnchor="middle" fontSize="12" fontWeight="600" fill="var(--ink)">{c.name}</text>
              <text x={x + colW / 2} y={top - 10} textAnchor="middle" fontSize="10" fill="var(--muted)">{c.is_active ? 'active well' : `${c.distance_km} km`}</text>
              {(c.formation_tops || []).map((t) => {
                const h = y(t.bottom_m) - y(t.top_m)
                const drilledTo = c.is_active ? c.current_depth_m : c.td_m
                return (
                  <g key={t.name}>
                    <rect x={x} y={y(t.top_m)} width={colW} height={Math.max(0, h - 1)} rx="3" fill={FORMATION_FILL[t.name] || '#ccc'}
                      opacity={drilledTo && t.top_m > drilledTo ? 0.45 : 1} />
                    {h > 16 && <text x={x + 6} y={y(t.top_m) + 13} fontSize="10" fill={DARK_TEXT.has(t.name) ? '#2b2623' : '#f6efe0'}>{t.name}</text>}
                  </g>
                )
              })}
              {!c.is_active && c.td_m && <line x1={x - 4} x2={x + colW + 4} y1={tdY} y2={tdY} stroke="var(--ink-2)" strokeWidth="1.5" />}
              {c.is_active && (
                <>
                  {upcoming.map((u) => (
                    <rect key={u.key} x={x - 6} y={y(u.expected_from_m - 10)} width={4} height={Math.max(4, y(u.expected_to_m + 10) - y(u.expected_from_m - 10))}
                      rx="2" fill={u.severity === 'high' ? 'var(--critical)' : u.severity === 'medium' ? 'var(--serious)' : 'var(--warn)'}>
                      <title>{u.title}</title>
                    </rect>
                  ))}
                  <line x1={x - 10} x2={x + colW + 10} y1={y(currentDepth)} y2={y(currentDepth)} stroke="var(--critical)" strokeWidth="2" />
                  <text x={x + colW + 12} y={y(currentDepth) + 4} fontSize="11" fontWeight="600" fill="var(--critical-ink)">bit {Math.round(currentDepth)} m</text>
                </>
              )}
              {(c.events || []).map((e) => (
                <circle key={e.id} cx={x + colW - 14 - (['MUD_LOSS', 'KICK', 'STUCK_PIPE', 'TORQUE_SPIKE', 'CEMENTING', 'FISHING', 'NPT'].indexOf(e.type) % 4) * 11}
                  cy={y(e.depth_m)} r={hover?.id === e.id ? 7 : 5} fill={EVENT_META[e.type]?.color || 'var(--muted)'} stroke="var(--card)" strokeWidth="2"
                  style={{ cursor: 'pointer' }} onMouseEnter={() => setHover({ ...e, well: c.name })} onMouseLeave={() => setHover(null)}
                  onClick={() => onEvent && onEvent(e)} />
              ))}
            </g>
          )
        })}
      </svg>
      {hover && (
        <div className="card tight" style={{ position: 'sticky', left: 0, bottom: 0, maxWidth: 420, padding: 12, marginTop: -8 }}>
          <b>{hover.well}</b> · {EVENT_META[hover.type]?.label} at {Math.round(hover.depth_m)} m ({hover.formation})
          <div className="small ink2 mt-4">{hover.description}</div>
        </div>
      )}
    </div>
  )
}
