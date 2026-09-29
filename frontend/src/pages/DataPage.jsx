import { ErrorBox, Loading, SectionTitle } from '../components/ui'
import { useApi } from '../lib/util'
import { IS_DEMO } from '../api/client'

const REAL_VS_MOCK = [
  ['Real', 'Full-stack app: FastAPI + SQLite database + React/Leaflet frontend, JWT login with roles'],
  ['Real', 'Distance (haversine), point-in-polygon, allowed-zone and breach detection maths'],
  ['Real', 'Directional well geometry: minimum curvature method for the bottom-hole location'],
  ['Real', 'Live tracking over websockets, breach logging with time and coordinates'],
  ['Real', 'Offset alert engine: formation-based depth correlation and recommendations'],
  ['Real', 'scikit-learn models are really trained and cross-validated (on sample data)'],
  ['Real', 'PDF text extraction, rule-based NLP, optional Claude extraction with API key'],
  ['Real', 'ISRIC SoilGrids live lookups (cached) when the server has internet'],
  ['Real names', 'Oil fields, operators, formations and protected areas use real names'],
  ['Sample', 'Well locations, events, depth logs, production, reserves, drillers'],
  ['Sample', 'Zone outlines (simplified), geology polygons, landslide list, land ownership'],
  ['Sample', 'Terrain is modelled unless SRTM tiles are added; the seismic structure map is invented'],
  ['Simulated', 'Driller GPS movement (simulator) and live drilling depth of the active wells'],
]

export default function DataPage() {
  const src = useApi('/api/meta/sources')
  const ml = useApi('/api/ml/explain')
  if (src.loading || ml.loading) return <Loading />
  if (src.error) return <ErrorBox error={src.error} />
  const p = ml.data?.prospect_model
  return (
    <div className="col gap-20">
      <SectionTitle eyebrow="Honesty panel" title="What is real and what is sample data" sub={src.data.notice} />
      {IS_DEMO && <div className="notice">You are using the hosted browser demo: the backend logic runs inside your browser on a snapshot of the sample database. Run the project locally for the full FastAPI backend.</div>}
      <div className="card"><div className="table-wrap"><table className="table">
        <thead><tr><th>Dataset</th><th>Used in this demo</th><th>Real source it stands in for</th></tr></thead>
        <tbody>{src.data.datasets.map((d) => <tr key={d.name}><td><b>{d.name}</b></td><td className="small ink2">{d.used}</td><td className="small">{d.real_source}</td></tr>)}</tbody>
      </table></div></div>
      <div className="card">
        <SectionTitle eyebrow="At a glance" title="Real vs sample vs simulated" />
        <table className="table"><tbody>{REAL_VS_MOCK.map(([k, v]) => <tr key={v}><td style={{ width: 110 }}><span className={`pill ${k === 'Real' ? 'good' : k === 'Sample' ? 'warn' : k === 'Simulated' ? 'info' : ''}`}>{k}</span></td><td>{v}</td></tr>)}</tbody></table>
      </div>
      {p && (
        <div className="grid g2">
          <div className="card">
            <SectionTitle eyebrow="Model 1" title="Success score and untapped spots" />
            <p className="ink2">{p.what}</p>
            <p className="ink2 mt-8">{p.trained_on} {p.checked_by}</p>
            <div className="eyebrow mt-16" style={{ marginBottom: 6 }}>What it looks at (importance)</div>
            {p.inputs.map((f) => (
              <div key={f.feature} className="mt-8"><div className="row between small"><span>{f.label}</span><span className="num muted">{Math.round(f.importance * 100)}%</span></div>
                <div className="meter mt-4"><span style={{ width: `${f.importance * 100}%`, background: 'var(--s1)' }} /></div></div>
            ))}
            <p className="small muted mt-16">{p.confidence}</p>
            <p className="small muted mt-8">{p.untapped}</p>
          </div>
          <div className="card">
            <SectionTitle eyebrow="Model 2" title="Drilling risk ahead of the bit" />
            <p className="ink2">{ml.data.risk_model.what}</p>
            <p className="ink2 mt-8">{ml.data.risk_model.trained_on}</p>
            <ul className="ink2">{ml.data.risk_model.inputs.map((i) => <li key={i}>{i}</li>)}</ul>
            <p className="small muted mt-8">{ml.data.note}</p>
            <div className="eyebrow mt-16">Physics and geometry used</div>
            <ul className="small ink2">
              <li>Haversine distance between GPS points</li>
              <li>Allowed radius = rig horizontal reach + max(10 % of reach, 250 m), capped by the declared area</li>
              <li>Minimum curvature method (MD, inclination, azimuth) for the planned bottom-hole location</li>
              <li>Ray-casting point-in-polygon for protected, forest and restricted zones</li>
              <li>Volumetric oil in place: 7758 · A · h · φ · (1 − Sw) / Bo, with Monte Carlo P90/P50/P10</li>
              <li>Slope from elevation by central differences on a 30 m grid</li>
            </ul>
          </div>
        </div>
      )}
      <div className="card">
        <SectionTitle eyebrow="Production integration" title="Where real data would come from" />
        <p className="ink2">In production the loaders in <code>backend/loaders/</code> read the real datasets (GEM tracker, Volve DDR XML, Bhukosh shapefiles, NASA GLC, SRTM, WDPA, OSM). The national source of record would be the DGH National Data Repository (ndr.dghindia.gov.in), and land ownership would come from state land-record portals.</p>
      </div>
    </div>
  )
}
