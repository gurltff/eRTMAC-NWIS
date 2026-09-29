import { Ban, CheckCircle2, ChevronDown, CircleHelp, Landmark, Layers, Mountain, ShieldAlert, Sprout, X } from 'lucide-react'
import { useState } from 'react'
import { fmt, LEVEL_CLS, useApi } from '../lib/util'
import { EventTag, ErrorBox, Loading, Meter, Pill, SampleBadge, StatusPill } from './ui'

const VERDICT = {
  LEGAL: { tone: 'good', label: 'Legal zone', Icon: CheckCircle2 },
  ILLEGAL: { tone: 'critical', label: 'Illegal zone', Icon: Ban },
  NEEDS_LICENCE: { tone: 'warn', label: 'Needs a licence', Icon: CircleHelp },
}
const OWNER = { owned: 'Privately owned', leased: 'Leased', government: 'Government land', unclaimed: 'Unclaimed' }

function Section({ title, icon, children, open: startOpen = true }) {
  const [open, setOpen] = useState(startOpen)
  return (
    <div style={{ borderTop: '1px solid var(--line)', padding: '16px 0' }}>
      <button onClick={() => setOpen(!open)} className="row between" style={{ width: '100%', border: 0, background: 'none', padding: 0, cursor: 'pointer' }}>
        <span className="row gap-6">{icon}<h3>{title}</h3></span>
        <ChevronDown size={16} style={{ transform: open ? 'rotate(180deg)' : 'none', transition: 'transform .15s' }} />
      </button>
      {open && <div className="mt-12">{children}</div>}
    </div>
  )
}

function ScoreRing({ score, label }) {
  const r = 30, c = 2 * Math.PI * r
  const color = score >= 60 ? 'var(--good)' : score >= 40 ? 'var(--warn)' : 'var(--critical)'
  return (
    <div style={{ position: 'relative', width: 76, height: 76 }}>
      <svg width="76" height="76" viewBox="0 0 76 76" role="img" aria-label={`Success score ${score} of 100`}>
        <circle cx="38" cy="38" r={r} fill="none" stroke="var(--track)" strokeWidth="6" />
        <circle cx="38" cy="38" r={r} fill="none" stroke={color} strokeWidth="6" strokeLinecap="round"
          strokeDasharray={`${(score / 100) * c} ${c}`} transform="rotate(-90 38 38)" />
      </svg>
      <div style={{ position: 'absolute', inset: 0, display: 'grid', placeItems: 'center', textAlign: 'center' }}>
        <div><div className="serif" style={{ fontSize: 22, lineHeight: 1 }}>{score}</div><div className="tiny muted">{label}</div></div>
      </div>
    </div>
  )
}

export function LocationDetail({ lat, lon, extra }) {
  const { data: d, error, loading } = useApi('/api/map/location', { lat: lat.toFixed(5), lon: lon.toFixed(5) })
  if (loading) return <Loading text="Checking this spot…" />
  if (error) return <ErrorBox error={error} />
  if (!d) return null
  const v = VERDICT[d.legality.verdict]
  const own = d.ownership
  const soilTop = d.soil.layers['0-5cm'] || {}
  return (
    <div>
      {extra}
      {/* Headline: score, legal, ownership, oil */}
      <div className="row gap-16" style={{ alignItems: 'center' }}>
        <ScoreRing score={d.success.score} label={d.success.label} />
        <div className="grow">
          <div className="eyebrow">Chance of a good result</div>
          <p className="ink2 small mt-4">Model confidence: <b>{d.success.confidence_label}</b></p>
          <div className="row wrap mt-8 gap-6">
            <StatusPill tone={v.tone} label={v.label} />
            <Pill tone={own.status === 'unclaimed' ? 'info' : ''} icon={<Landmark size={12} />}>{OWNER[own.status] || own.status}</Pill>
          </div>
        </div>
      </div>

      <p className="mt-16" style={{ fontFamily: 'var(--serif)', fontSize: 17, lineHeight: 1.55 }}>
        <span className="mark">{d.history.summary}</span>
      </p>
      <p className="mt-8 ink2">{d.legality.summary}</p>
      <p className="mt-8 ink2">{own.statement}</p>

      <div className="grid g2 mt-16" style={{ gap: 10 }}>
        <div className="card flat tight" style={{ background: 'var(--card-2)' }}>
          <div className="eyebrow">Estimated oil (P50)</div>
          <div className="serif" style={{ fontSize: 22 }}>{fmt.bbl(d.oil_estimate.recoverable_p50_bbl)}</div>
          <div className="tiny muted">Range {fmt.bbl(d.oil_estimate.recoverable_p90_bbl)} – {fmt.bbl(d.oil_estimate.recoverable_p10_bbl)}</div>
        </div>
        <div className="card flat tight" style={{ background: 'var(--card-2)' }}>
          <div className="eyebrow">After risk</div>
          <div className="serif" style={{ fontSize: 22 }}>{fmt.bbl(d.oil_estimate.risked_recoverable_bbl)}</div>
          <div className="tiny muted">× {Math.round(d.oil_estimate.chance_of_success * 100)}% chance of success</div>
        </div>
      </div>

      <Section title="Hazards" icon={<ShieldAlert size={16} />}>
        <div className="col gap-16">
          {d.hazards.map((h) => (
            <div key={h.key}>
              <div className="row between"><span style={{ fontWeight: 500 }}>{h.label}</span><StatusPill tone={LEVEL_CLS[h.level]} label={`${h.level} · ${h.score}`} /></div>
              <div className="mt-4"><Meter value={h.score} /></div>
              <ul className="small muted" style={{ margin: '6px 0 0', paddingLeft: 18 }}>{h.why.map((w) => <li key={w}>{w}</li>)}</ul>
            </div>
          ))}
        </div>
      </Section>

      <Section title="Why this score" icon={<Sprout size={16} />} open={false}>
        <ul className="ink2" style={{ margin: 0, paddingLeft: 18 }}>{d.success.reasons.map((r) => <li key={r}>{r}</li>)}</ul>
        <p className="small muted mt-8">The score comes from a small random-forest model trained on the sample wells. Confidence is lower far from drilled wells.</p>
        <div className="small muted mt-8">
          Oil estimate: {d.oil_estimate.method}. Inputs borrowed from {d.oil_estimate.inputs.borrowed_from_fields.join(', ')}:
          net pay {d.oil_estimate.inputs.net_pay_m} m, porosity {Math.round(d.oil_estimate.inputs.porosity * 100)}%,
          water saturation {Math.round(d.oil_estimate.inputs.water_saturation * 100)}%, recovery factor {Math.round(d.oil_estimate.inputs.recovery_factor * 100)}%.
        </div>
      </Section>

      <Section title="History of this place" icon={<Landmark size={16} />}>
        {d.history.fields.map((f) => (
          <div key={f.name} className="small mt-4">
            <b>{f.name}</b> field · {f.distance_km} km · {f.operator}, discovered {f.discovered}
            {f.past_operators?.length ? <span className="muted"> · earlier: {f.past_operators.join('; ')}</span> : null}
            {f.note && <div className="muted">{f.note}</div>}
          </div>
        ))}
        {d.history.wells.length > 0 && (
          <div className="table-wrap mt-12">
            <table className="table">
              <thead><tr><th>Well</th><th>Distance</th><th>Spud</th><th>Result</th></tr></thead>
              <tbody>{d.history.wells.map((w) => (
                <tr key={w.id}><td>{w.name}</td><td className="num">{w.distance_km} km</td><td>{w.spud_year}</td><td>{fmt.title(w.outcome || w.status)}</td></tr>
              ))}</tbody>
            </table>
          </div>
        )}
        {Object.keys(d.history.event_counts).length > 0 && (
          <div className="row wrap gap-6 mt-12">{Object.entries(d.history.event_counts).map(([t, n]) => <span key={t} className="row gap-4"><EventTag type={t} /><span className="small muted">{n}</span></span>)}</div>
        )}
        {d.history.land_use.length > 0 && (
          <div className="mt-12"><div className="eyebrow">Land record · parcel {own.parcel} ({own.village})</div>
            <ul className="small ink2" style={{ margin: '6px 0 0', paddingLeft: 18 }}>{d.history.land_use.map((x) => <li key={x}>{x}</li>)}</ul></div>
        )}
        {d.history.landslides.length > 0 && (
          <div className="mt-12"><div className="eyebrow">Landslides within 10 km</div>
            <ul className="small ink2" style={{ margin: '6px 0 0', paddingLeft: 18 }}>{d.history.landslides.map((s, i) => <li key={i}>{s.date} · {s.place} · {s.size} · {s.distance_km} km</li>)}</ul></div>
        )}
      </Section>

      <Section title="Ground: rock and soil" icon={<Mountain size={16} />}>
        {d.geology.surface && (
          <div>
            <div style={{ fontWeight: 500 }}>{d.geology.surface.name}</div>
            <div className="small ink2">{d.geology.surface.lithology} · {d.geology.surface.age}</div>
          </div>
        )}
        <div className="grid g3 mt-12" style={{ gap: 8 }}>
          <div><div className="tiny muted">Elevation</div><div className="num">{fmt.m(d.terrain.elevation_m)}</div></div>
          <div><div className="tiny muted">Slope</div><div className="num">{d.terrain.slope_deg}°</div></div>
          <div><div className="tiny muted">Relief (1 km)</div><div className="num">{fmt.m(d.terrain.local_relief_m)}</div></div>
        </div>
        <div className="mt-12">
          <div className="row between"><b>Soil: {d.soil.texture}</b><span className="tiny muted">{d.soil.is_live ? 'SoilGrids live' : 'estimate'}</span></div>
          <div className="small ink2 mt-4">Clay {soilTop.clay}% · Sand {soilTop.sand}% · Silt {soilTop.silt}% · pH {soilTop.phh2o}</div>
          <ul className="small ink2" style={{ margin: '6px 0 0', paddingLeft: 18 }}>{d.soil.notes.map((n) => <li key={n}>{n}</li>)}</ul>
          <p className="tiny muted mt-8">{d.soil.scope_note}</p>
        </div>
      </Section>

      <Section title="Expected rock column" icon={<Layers size={16} />} open={false}>
        <p className="small muted" style={{ marginBottom: 8 }}>{d.geology.subsurface.method}</p>
        <table className="table">
          <thead><tr><th>Formation</th><th>Top</th><th>Rock</th></tr></thead>
          <tbody>{d.geology.subsurface.column.map((t) => (
            <tr key={t.name} style={d.geology.subsurface.main_targets.includes(t.name) ? { background: 'var(--highlight)' } : undefined}>
              <td>{t.name}</td><td className="num">{fmt.m(t.top_m)}</td><td className="small ink2">{t.lithology}</td>
            </tr>
          ))}</tbody>
        </table>
      </Section>

      <div className="tiny muted" style={{ borderTop: '1px solid var(--line)', paddingTop: 12 }}>Sources: {d.sources.join(' · ')}</div>
    </div>
  )
}

export default function LocationPanel({ point, onClose, extra }) {
  if (!point) return null
  return (
    <aside className="loc-panel card">
      <div className="row between" style={{ marginBottom: 12 }}>
        <div>
          <div className="eyebrow">{point.title ? 'Selected' : 'Tapped location'}</div>
          <h2 style={{ fontSize: 22 }}>{point.title || fmt.coord(point.lat, point.lon)}</h2>
          {point.title && <div className="small muted">{fmt.coord(point.lat, point.lon)}</div>}
        </div>
        <div className="row gap-6"><SampleBadge /><button className="icon-btn plain" onClick={onClose} aria-label="Close"><X size={18} /></button></div>
      </div>
      <LocationDetail key={`${point.lat},${point.lon}`} lat={point.lat} lon={point.lon} extra={extra} />
    </aside>
  )
}

