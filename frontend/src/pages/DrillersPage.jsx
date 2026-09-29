import { Check, Download, X } from 'lucide-react'
import { useState } from 'react'
import { api, IS_DEMO } from '../api/client'
import { BaseMap, ZoneCircle, ZonesLayer, FitBounds } from '../components/MapBits'
import { Empty, ErrorBox, Loading, SectionTitle, StatusPill } from '../components/ui'
import { useAuth } from '../context/AuthContext'
import { fmt, useApi } from '../lib/util'

export const REG_STATUS = {
  draft: { cls: '', label: 'Not submitted' },
  submitted: { cls: 'warn', label: 'Waiting for review' },
  approved: { cls: 'good', label: 'Approved' },
  rejected: { cls: 'critical', label: 'Rejected' },
}
export const DOC_STATUS = { pending: { cls: 'warn', label: 'Pending' }, approved: { cls: 'good', label: 'Approved' }, rejected: { cls: 'critical', label: 'Rejected' } }

export function DrillerZoneMap({ profile, height = 260 }) {
  const layers = useApi('/api/map/layers')
  if (!profile.zone) return <Empty>No working area set.</Empty>
  return (
    <div style={{ height, borderRadius: 16, overflow: 'hidden', border: '1px solid var(--line)' }}>
      <BaseMap center={[profile.zone.center.lat, profile.zone.center.lon]} zoom={12}>
        {layers.data && <ZonesLayer zones={layers.data.zones} />}
        <ZoneCircle zone={profile.zone} />
        <FitBounds points={profile.zone.polygon} padding={20} />
      </BaseMap>
    </div>
  )
}

function Detail({ id, onChanged }) {
  const { user } = useAuth()
  const p = useApi(`/api/admin/drillers/${id}`)
  const [note, setNote] = useState('')
  const [err, setErr] = useState(null)
  if (p.loading) return <Loading />
  if (p.error) return <ErrorBox error={p.error} />
  const d = p.data
  const isAdmin = user.role === 'admin'
  const act = async (fn) => { setErr(null); try { await fn(); await p.reload(); onChanged() } catch (e) { setErr(e.message) } }
  const decideDoc = (doc, status) => act(() => api(`/api/admin/documents/${doc.id}/decision`, { method: 'POST', body: { status, note: status === 'rejected' ? (note || 'Please re-upload a clear, valid copy.') : null } }))
  const decide = (decision) => act(() => api(`/api/admin/drillers/${d.id}/decision`, { method: 'POST', body: { decision, note: note || (decision === 'approve' ? 'All documents checked.' : '') } }))
  const openFile = async (doc) => {
    try { const blob = await api(`/api/admin/documents/${doc.id}/file`); window.open(URL.createObjectURL(blob), '_blank') } catch (e) { setErr(e.message) }
  }
  const st = REG_STATUS[d.status]
  return (
    <div className="col gap-16">
      <div className="card">
        <div className="row between top">
          <div><div className="eyebrow">Head of drilling</div><h2 className="mt-4">{d.full_name}</h2><div className="muted">{d.email} · {d.phone || 'no phone'}</div></div>
          <StatusPill tone={st.cls} label={st.label} />
        </div>
        <div className="grid g2 mt-16 small">
          <div><div className="muted">Company</div><b>{d.company_name || '–'}</b><div className="ink2">{d.company_reg_no} · {d.company_address}</div></div>
          <div><div className="muted">Licence no.</div><b>{d.licence_number || '–'}</b><div className="ink2">{d.designation} · {d.experience_years ?? '–'} years experience</div></div>
        </div>
        {d.review_note && <div className="notice mt-12">Review note: {d.review_note}</div>}
      </div>
      <div className="card">
        <SectionTitle eyebrow="Documents" title="Check each document" />
        {d.documents.length === 0 && <Empty>No documents uploaded.</Empty>}
        <div className="list">{d.documents.map((doc) => (
          <div key={doc.id} className="item row between wrap">
            <div className="grow"><b>{doc.label}</b><div className="small muted">{doc.filename} · uploaded {fmt.ago(doc.uploaded_at)}{doc.note ? ` · ${doc.note}` : ''}</div></div>
            <div className="row gap-6">
              <StatusPill tone={DOC_STATUS[doc.status].cls} label={DOC_STATUS[doc.status].label} />
              {doc.has_file && !IS_DEMO && <button className="icon-btn plain" title="Open file" onClick={() => openFile(doc)}><Download size={15} /></button>}
              {isAdmin && <>
                <button className="btn xs ghost" onClick={() => decideDoc(doc, 'approved')}><Check size={12} />Approve</button>
                <button className="btn xs line" onClick={() => decideDoc(doc, 'rejected')}><X size={12} />Reject</button>
              </>}
            </div>
          </div>
        ))}</div>
      </div>
      <div className="card">
        <SectionTitle eyebrow="Equipment" title="Declared rigs" />
        {d.equipment.length ? (
          <table className="table"><thead><tr><th>Rig</th><th>Type</th><th>Max depth</th><th>Horizontal reach</th><th>Power</th></tr></thead>
            <tbody>{d.equipment.map((e) => <tr key={e.id}><td>{e.name}</td><td>{e.rig_type}</td><td className="num">{fmt.m(e.max_depth_m)}</td><td className="num">{fmt.m(e.max_horizontal_reach_m)}</td><td className="num">{e.power_hp ? `${e.power_hp} HP` : '–'}</td></tr>)}</tbody></table>
        ) : <Empty>No equipment declared.</Empty>}
      </div>
      <div className="card">
        <SectionTitle eyebrow="Working area" title={d.work_area_name || 'Not set'} />
        {d.zone && <p className="small ink2" style={{ marginBottom: 10 }}>Allowed radius {fmt.m(d.zone.radius_m)} = rig reach {fmt.m(d.zone.reach_m)} + margin {fmt.m(d.zone.safety_margin_m)} (limited by {d.zone.limited_by}). Site is <b>{d.zone.site_legality.verdict.replace('_', ' ').toLowerCase()}</b>.</p>}
        {d.zone?.warnings?.map((w) => <div key={w} className="small" style={{ color: 'var(--serious-ink)' }}>⚠ {w}</div>)}
        <DrillerZoneMap profile={d} />
      </div>
      {isAdmin && (
        <div className="card">
          <SectionTitle eyebrow="Decision" title="Approve or reject this registration" />
          <textarea className="input" rows={2} placeholder="Note to the driller (required when rejecting)" value={note} onChange={(e) => setNote(e.target.value)} />
          {err && <div className="error mt-8">{err}</div>}
          <div className="row mt-12">
            <button className="btn" onClick={() => decide('approve')}><Check size={15} />Approve registration</button>
            <button className="btn line" onClick={() => decide('reject')}><X size={15} />Reject</button>
          </div>
        </div>
      )}
      {!isAdmin && err && <div className="error">{err}</div>}
    </div>
  )
}

export default function DrillersPage() {
  const list = useApi('/api/admin/drillers')
  const [sel, setSel] = useState(null)
  if (list.loading) return <Loading />
  if (list.error) return <ErrorBox error={list.error} />
  const current = sel ?? list.data[0]?.id
  return (
    <div className="col gap-20">
      <SectionTitle eyebrow="Driller registrations" title="Review and approve" sub="Heads of drilling register, upload documents, declare rigs and a working area. An admin checks each document and approves." />
      <div className="grid g-side">
        <div className="card" style={{ padding: 10, alignSelf: 'start' }}>
          {list.data.map((d) => {
            const st = REG_STATUS[d.status]
            return (
              <button key={d.id} onClick={() => setSel(d.id)} className="row between"
                style={{ width: '100%', border: 0, background: current === d.id ? 'var(--card-2)' : 'none', borderRadius: 12, padding: 12, cursor: 'pointer', textAlign: 'left' }}>
                <div className="grow"><b>{d.full_name}</b><div className="small muted ellipsis">{d.company_name || 'No company yet'}</div></div>
                <StatusPill tone={st.cls} label={st.label} />
              </button>
            )
          })}
        </div>
        {current ? <Detail key={current} id={current} onChanged={list.reload} /> : <Empty>No registrations.</Empty>}
      </div>
    </div>
  )
}
