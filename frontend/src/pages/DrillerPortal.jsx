import { Check, ChevronRight, LogOut, Plus, Trash2, Upload } from 'lucide-react'
import { useEffect, useState } from 'react'
import { Circle, CircleMarker } from 'react-leaflet'
import { useNavigate } from 'react-router-dom'
import { api } from '../api/client'
import { BrandMark, ThemeButton } from '../components/Layouts'
import { BaseMap, ZoneCircle, ZonesLayer } from '../components/MapBits'
import { Empty, ErrorBox, Loading, SampleBadge, StatusPill } from '../components/ui'
import { useAuth } from '../context/AuthContext'
import { fmt, useApi } from '../lib/util'
import { DOC_STATUS, REG_STATUS } from './DrillersPage'

const STEPS = [['personal', 'Personal'], ['company', 'Company'], ['documents', 'Documents'], ['equipment', 'Equipment'], ['area', 'Working area'], ['review', 'Submit']]

function Field({ label, children }) { return <div className="field"><label>{label}</label>{children}</div> }

function useForm(initial) {
  const [f, setF] = useState(initial)
  const set = (k, num) => (e) => setF({ ...f, [k]: num ? (e.target.value === '' ? null : Number(e.target.value)) : e.target.value })
  return [f, set, setF]
}

function Personal({ p, save, locked }) {
  const [f, set] = useForm({ phone: p.phone || '', designation: p.designation || '', experience_years: p.experience_years, id_number: p.id_number || '' })
  return (
    <form onSubmit={(e) => { e.preventDefault(); save('/api/driller/profile', 'PUT', f) }}>
      <div className="form-grid">
        <Field label="Full name"><input className="input" value={p.full_name} disabled /></Field>
        <Field label="Phone"><input className="input" value={f.phone} onChange={set('phone')} required disabled={locked} /></Field>
        <Field label="Designation"><input className="input" value={f.designation} onChange={set('designation')} placeholder="e.g. Head of Drilling" required disabled={locked} /></Field>
        <Field label="Years of experience"><input className="input" type="number" min={0} value={f.experience_years ?? ''} onChange={set('experience_years', true)} disabled={locked} /></Field>
        <Field label="ID number (Aadhaar / PAN)"><input className="input" value={f.id_number} onChange={set('id_number')} disabled={locked} /></Field>
      </div>
      {!locked && <button className="btn mt-16">Save and continue<ChevronRight size={15} /></button>}
    </form>
  )
}

function Company({ p, save, locked }) {
  const [f, set] = useForm({ company_name: p.company_name || '', company_reg_no: p.company_reg_no || '', company_address: p.company_address || '', licence_number: p.licence_number || '' })
  return (
    <form onSubmit={(e) => { e.preventDefault(); save('/api/driller/profile', 'PUT', f) }}>
      <div className="form-grid">
        <Field label="Company name"><input className="input" value={f.company_name} onChange={set('company_name')} required disabled={locked} /></Field>
        <Field label="Company registration no. (CIN / LLPIN)"><input className="input" value={f.company_reg_no} onChange={set('company_reg_no')} disabled={locked} /></Field>
        <Field label="Drilling contractor licence no."><input className="input" value={f.licence_number} onChange={set('licence_number')} required disabled={locked} /></Field>
        <Field label="Registered address"><input className="input" value={f.company_address} onChange={set('company_address')} disabled={locked} /></Field>
      </div>
      {!locked && <button className="btn mt-16">Save and continue<ChevronRight size={15} /></button>}
    </form>
  )
}

function Documents({ p, reload, locked }) {
  const types = useApi('/api/driller/doc-types')
  const [err, setErr] = useState(null)
  const [busy, setBusy] = useState(null)
  if (!types.data) return <Loading />
  const upload = async (docType, file) => {
    if (!file) return
    setBusy(docType); setErr(null)
    const form = new FormData(); form.append('doc_type', docType); form.append('file', file)
    try { await api('/api/driller/documents', { method: 'POST', form }); await reload() } catch (e) { setErr(e.message) }
    setBusy(null)
  }
  return (
    <div>
      <p className="muted small" style={{ marginBottom: 10 }}>PDF, PNG or JPG. Each document is checked by an admin: pending → approved or rejected.</p>
      {err && <div className="error" style={{ marginBottom: 10 }}>{err}</div>}
      <div className="list">
        {Object.entries(types.data.types).map(([t, label]) => {
          const doc = p.documents.find((d) => d.doc_type === t)
          const required = types.data.required.includes(t)
          return (
            <div key={t} className="item row between wrap">
              <div className="grow"><b>{label}</b>{required && <span className="tiny muted"> · required</span>}
                <div className="small muted">{doc ? `${doc.filename} · ${fmt.ago(doc.uploaded_at)}` : 'Not uploaded'}{doc?.note ? ` · ${doc.note}` : ''}</div></div>
              <div className="row gap-6">
                {doc && <StatusPill tone={DOC_STATUS[doc.status].cls} label={DOC_STATUS[doc.status].label} />}
                {!locked && (
                  <label className="btn xs ghost" style={{ cursor: 'pointer' }}>
                    {busy === t ? <span className="spinner" /> : <Upload size={12} />}{doc ? 'Replace' : 'Upload'}
                    <input type="file" hidden accept=".pdf,.png,.jpg,.jpeg" onChange={(e) => upload(t, e.target.files[0])} />
                  </label>
                )}
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}

function Equipment({ p, save, locked }) {
  const [f, set, setF] = useForm({ name: '', rig_type: 'Land rig', max_depth_m: 4500, max_horizontal_reach_m: 1500, hook_load_t: 300, power_hp: 1500, year_built: 2015 })
  return (
    <div>
      {p.equipment.length ? (
        <div className="table-wrap"><table className="table">
          <thead><tr><th>Rig</th><th>Type</th><th>Max depth</th><th>Horizontal reach</th><th>Hook load</th><th /></tr></thead>
          <tbody>{p.equipment.map((e) => (
            <tr key={e.id}><td>{e.name}</td><td>{e.rig_type}</td><td className="num">{fmt.m(e.max_depth_m)}</td><td className="num">{fmt.m(e.max_horizontal_reach_m)}</td>
              <td className="num">{e.hook_load_t ? `${e.hook_load_t} t` : '–'}</td>
              <td>{!locked && <button className="icon-btn plain" onClick={() => save(`/api/driller/equipment/${e.id}`, 'DELETE')} aria-label="Remove"><Trash2 size={15} /></button>}</td></tr>
          ))}</tbody>
        </table></div>
      ) : <Empty>No rigs declared yet.</Empty>}
      {!locked && (
        <form className="card flat mt-16" style={{ background: 'var(--card-2)' }} onSubmit={async (e) => { e.preventDefault(); await save('/api/driller/equipment', 'POST', f, true); setF({ ...f, name: '' }) }}>
          <div className="eyebrow" style={{ marginBottom: 10 }}>Add a rig or machine</div>
          <div className="form-grid">
            <Field label="Name / ID"><input className="input" value={f.name} onChange={set('name')} placeholder="e.g. Rig-3" required /></Field>
            <Field label="Rig type"><select className="input" value={f.rig_type} onChange={set('rig_type')}>
              {['Land rig', 'Mobile land rig', 'Workover rig', 'Coiled tubing unit', 'Truck-mounted rig'].map((x) => <option key={x}>{x}</option>)}</select></Field>
            <Field label="Maximum depth (m)"><input className="input" type="number" value={f.max_depth_m} onChange={set('max_depth_m', true)} required /></Field>
            <Field label="Maximum horizontal reach (m)"><input className="input" type="number" value={f.max_horizontal_reach_m} onChange={set('max_horizontal_reach_m', true)} required /></Field>
            <Field label="Hook load (t)"><input className="input" type="number" value={f.hook_load_t ?? ''} onChange={set('hook_load_t', true)} /></Field>
            <Field label="Power (HP)"><input className="input" type="number" value={f.power_hp ?? ''} onChange={set('power_hp', true)} /></Field>
          </div>
          <button className="btn sm mt-16"><Plus size={14} />Add rig</button>
        </form>
      )}
    </div>
  )
}

function Area({ p, save, locked }) {
  const layers = useApi('/api/map/layers')
  const [f, set, setF] = useForm({
    work_area_name: p.work_area_name || '', site_lat: p.site_lat ?? 27.35, site_lon: p.site_lon ?? 95.2, work_radius_m: p.work_radius_m || 3000,
    planned_md_m: p.planned_md_m ?? 3500, planned_kop_m: p.planned_kop_m ?? 900, planned_build_rate: p.planned_build_rate ?? 2,
    planned_hold_inc: p.planned_hold_inc ?? 30, planned_azimuth: p.planned_azimuth ?? 45,
  })
  return (
    <form onSubmit={(e) => { e.preventDefault(); save('/api/driller/work-area', 'PUT', f) }}>
      <p className="small muted" style={{ marginBottom: 10 }}>Tap the map to set your rig site. Red, green and blue dashed areas are no-go zones.</p>
      <div style={{ height: 320, borderRadius: 16, overflow: 'hidden', border: '1px solid var(--line)' }}>
        <BaseMap center={[f.site_lat, f.site_lon]} zoom={11} onClick={locked ? undefined : (lat, lon) => setF({ ...f, site_lat: +lat.toFixed(5), site_lon: +lon.toFixed(5) })}>
          {layers.data && <ZonesLayer zones={layers.data.zones} />}
          <Circle center={[f.site_lat, f.site_lon]} radius={f.work_radius_m} pathOptions={{ color: '#9a6b2f', weight: 1, dashArray: '3 5', fillOpacity: 0.03 }} />
          <CircleMarker center={[f.site_lat, f.site_lon]} radius={6} pathOptions={{ color: '#fff', weight: 2, fillColor: '#2b2623', fillOpacity: 1 }} />
          {p.zone && p.zone.center.lat === f.site_lat && p.zone.center.lon === f.site_lon && <ZoneCircle zone={p.zone} />}
        </BaseMap>
      </div>
      <div className="form-grid mt-16">
        <Field label="Area / block name"><input className="input" value={f.work_area_name} onChange={set('work_area_name')} required disabled={locked} /></Field>
        <Field label={`Declared working radius: ${fmt.m(f.work_radius_m)}`}><input type="range" min={500} max={10000} step={100} value={f.work_radius_m} onChange={set('work_radius_m', true)} disabled={locked} /></Field>
        <Field label="Site latitude"><input className="input" type="number" step="0.00001" value={f.site_lat} onChange={set('site_lat', true)} disabled={locked} /></Field>
        <Field label="Site longitude"><input className="input" type="number" step="0.00001" value={f.site_lon} onChange={set('site_lon', true)} disabled={locked} /></Field>
      </div>
      <div className="eyebrow mt-16" style={{ marginBottom: 8 }}>Planned well (for the bottom-hole location)</div>
      <div className="form-grid" style={{ gridTemplateColumns: 'repeat(auto-fit, minmax(130px, 1fr))' }}>
        <Field label="Measured depth (m)"><input className="input" type="number" value={f.planned_md_m ?? ''} onChange={set('planned_md_m', true)} disabled={locked} /></Field>
        <Field label="Kick-off point (m)"><input className="input" type="number" value={f.planned_kop_m ?? ''} onChange={set('planned_kop_m', true)} disabled={locked} /></Field>
        <Field label="Build rate (°/30 m)"><input className="input" type="number" step="0.1" value={f.planned_build_rate ?? ''} onChange={set('planned_build_rate', true)} disabled={locked} /></Field>
        <Field label="Hold angle (°)"><input className="input" type="number" value={f.planned_hold_inc ?? ''} onChange={set('planned_hold_inc', true)} disabled={locked} /></Field>
        <Field label="Azimuth (° from north)"><input className="input" type="number" value={f.planned_azimuth ?? ''} onChange={set('planned_azimuth', true)} disabled={locked} /></Field>
      </div>
      {p.zone && (
        <div className="notice mt-16">
          Allowed zone: <b>{fmt.m(p.zone.radius_m)}</b> radius = rig reach {fmt.m(p.zone.reach_m)} + safety margin {fmt.m(p.zone.safety_margin_m)} (limited by {p.zone.limited_by}).
          Site is <b>{p.zone.site_legality.verdict.replace('_', ' ').toLowerCase()}</b>.
          {p.zone.bottom_hole && <> Planned hole ends {fmt.m(p.zone.bottom_hole.horizontal_displacement_m)} sideways at {fmt.m(p.zone.bottom_hole.tvd_m)} vertical depth.</>}
          {p.zone.warnings.map((w) => <div key={w} style={{ color: 'var(--serious-ink)' }}>⚠ {w}</div>)}
        </div>
      )}
      {!locked && <button className="btn mt-16">Save working area<ChevronRight size={15} /></button>}
    </form>
  )
}

function Review({ p, save }) {
  return (
    <div>
      <div className="list">{p.checklist.map((c) => (
        <div key={c.step} className="item row between"><span>{c.label}{c.missing?.length ? <span className="small muted"> · missing: {c.missing.join(', ')}</span> : null}</span>
          <StatusPill tone={c.done ? 'good' : 'warn'} label={c.done ? 'Done' : 'To do'} /></div>
      ))}</div>
      {p.status !== 'submitted' && p.status !== 'approved' && (
        <button className="btn mt-16" disabled={!p.checklist.every((c) => c.done)} onClick={() => save('/api/driller/submit', 'POST')}>
          <Check size={15} />Submit for review
        </button>
      )}
    </div>
  )
}

export default function DrillerPortal() {
  const { logout, refresh } = useAuth()
  const nav = useNavigate()
  const me = useApi('/api/driller/me')
  const [step, setStep] = useState(null)
  const [err, setErr] = useState(null)
  const [saved, setSaved] = useState(null)

  useEffect(() => {
    if (me.data && step === null) {
      const firstTodo = me.data.checklist.find((c) => !c.done)
      setStep(firstTodo ? firstTodo.step : 'review')
    }
  }, [me.data]) // eslint-disable-line

  if (me.loading && !me.data) return <Loading />
  if (me.error) return <ErrorBox error={me.error} />
  const p = me.data
  const locked = p.status === 'submitted'
  const st = REG_STATUS[p.status]
  const idx = STEPS.findIndex(([k]) => k === step)

  const save = async (path, method, body, stay) => {
    setErr(null)
    try {
      const r = await api(path, { method, body })
      me.setData(r)
      setSaved('Saved')
      setTimeout(() => setSaved(null), 1800)
      if (path.endsWith('/submit')) refresh()
      if (!stay && method !== 'DELETE' && idx < STEPS.length - 1) setStep(STEPS[idx + 1][0])
    } catch (e) { setErr(e.message) }
  }

  const done = Object.fromEntries(p.checklist.map((c) => [c.step, c.done]))
  return (
    <div style={{ maxWidth: 920, margin: '0 auto', padding: '24px 16px 60px' }}>
      <div className="row between">
        <div className="row"><BrandMark /><div><div className="serif" style={{ fontSize: 19 }}>Driller registration</div><div className="tiny muted">{p.full_name} · {p.email}</div></div></div>
        <div className="row"><SampleBadge /><ThemeButton /><button className="icon-btn" onClick={logout} aria-label="Log out"><LogOut size={16} /></button></div>
      </div>

      <div className="card mt-24 row between wrap">
        <div>
          <div className="eyebrow">Registration status</div>
          <h2 className="mt-4">{st.label}</h2>
          <p className="muted small mt-4">
            {p.status === 'draft' && 'Complete the six steps and submit. An admin will check your documents.'}
            {p.status === 'submitted' && 'Your registration is with the admin. You will be able to edit again after the review.'}
            {p.status === 'approved' && 'You are approved. Live tracking and alerts are on in the field view.'}
            {p.status === 'rejected' && `Please fix and submit again. Note from admin: ${p.review_note || '–'}`}
          </p>
        </div>
        {p.status === 'approved' ? <button className="btn" onClick={() => nav('/field')}>Open field view<ChevronRight size={15} /></button> : <StatusPill tone={st.cls} label={st.label} />}
      </div>

      <div className="steps mt-24">
        {STEPS.map(([k, label], i) => (
          <button key={k} className={`step ${step === k ? 'on' : ''} ${done[k] ? 'done' : ''}`} onClick={() => setStep(k)}>
            <span className="n">{done[k] ? <Check size={12} /> : i + 1}</span>{label}
          </button>
        ))}
      </div>

      <div className="card mt-16">
        <div className="row between" style={{ marginBottom: 14 }}>
          <h2>{STEPS[idx]?.[1]}</h2>
          {saved && <span className="pill good">{saved}</span>}
        </div>
        {err && <div className="error" style={{ marginBottom: 12 }}>{err}</div>}
        {step === 'personal' && <Personal p={p} save={save} locked={locked} />}
        {step === 'company' && <Company p={p} save={save} locked={locked} />}
        {step === 'documents' && <Documents p={p} reload={me.reload} locked={locked} />}
        {step === 'equipment' && <Equipment p={p} save={save} locked={locked} />}
        {step === 'area' && <Area key={p.site_lat} p={p} save={save} locked={locked} />}
        {step === 'review' && <Review p={p} save={save} />}
      </div>
    </div>
  )
}
