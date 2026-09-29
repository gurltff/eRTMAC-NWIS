import { FileUp, Sparkles } from 'lucide-react'
import { useRef, useState } from 'react'
import { api, IS_DEMO } from '../api/client'
import { Empty, EventTag, Loading, SectionTitle, StatusPill } from '../components/ui'
import { fmt, useApi } from '../lib/util'

function Result({ doc }) {
  const x = doc.extracted
  return (
    <div className="col gap-16">
      <div className="row wrap gap-6">
        <StatusPill tone="good" label={`${doc.events_created} events saved`} />
        <StatusPill tone="info" label={doc.extract_method === 'llm' ? 'Read by Claude (LLM)' : 'Rule-based extraction'} />
        <StatusPill tone="" label={doc.text_method === 'ocr' ? 'OCR' : doc.text_method === 'pdf-text' ? 'PDF text layer' : doc.text_method} />
        {doc.well_name && <StatusPill tone="good" label={`Linked to well ${doc.well_name}`} />}
      </div>
      {doc.warnings?.map((w) => <div key={w} className="notice">{w}</div>)}
      <div className="grid g3 small">
        {[['Well', x.well_name], ['Field', x.field], ['Operator', x.operator], ['Report date', x.report_date], ['Rig', x.rig],
          ['Location', x.lat ? fmt.coord(x.lat, x.lon) : null], ['Total depth', x.total_depth_m ? fmt.m(x.total_depth_m) : null]].map(([k, v]) => (
          <div key={k}><div className="muted">{k}</div><b>{v || '–'}</b></div>
        ))}
      </div>
      {x.summary && <p style={{ fontFamily: 'var(--serif)', fontSize: 16 }}><span className="mark">{x.summary}</span></p>}
      {x.formations?.length > 0 && (
        <div><div className="eyebrow" style={{ marginBottom: 6 }}>Formation tops</div>
          <div className="row wrap gap-6">{x.formations.map((f) => <span key={f.name} className="pill">{f.name} · {fmt.m(f.top_m)}</span>)}</div></div>
      )}
      <div className="table-wrap"><table className="table">
        <thead><tr><th>Problem</th><th>Depth</th><th>Formation</th><th>What happened</th><th>What was done</th><th>Lesson</th></tr></thead>
        <tbody>{(x.events || []).map((e, i) => (
          <tr key={i}><td><EventTag type={e.event_type} /></td><td className="num">{fmt.m(e.depth_m)}</td><td>{e.formation || '–'}</td>
            <td className="small">{e.description}</td><td className="small ink2">{e.action_taken || '–'}</td><td className="small">{e.lesson || '–'}</td></tr>
        ))}</tbody>
      </table></div>
      {x.lessons?.length > 0 && <div><div className="eyebrow">Lessons</div><ul className="ink2" style={{ margin: '6px 0 0', paddingLeft: 18 }}>{x.lessons.map((l) => <li key={l}>{l}</li>)}</ul></div>}
      <details><summary className="small muted" style={{ cursor: 'pointer' }}>Show extracted text</summary>
        <pre className="small" style={{ whiteSpace: 'pre-wrap', background: 'var(--card-2)', padding: 12, borderRadius: 12, maxHeight: 300, overflow: 'auto' }}>{doc.text_excerpt}</pre></details>
    </div>
  )
}

export default function DocumentsPage() {
  const mode = useApi('/api/documents/mode')
  const history = useApi('/api/documents')
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState(null)
  const [doc, setDoc] = useState(null)
  const input = useRef()

  const upload = async (file) => {
    if (!file) return
    setBusy(true); setErr(null); setDoc(null)
    const form = new FormData()
    form.append('file', file)
    try { setDoc(await api('/api/documents/extract', { method: 'POST', form })); history.reload() } catch (e) { setErr(e.message) }
    setBusy(false)
  }
  const useSample = async () => {
    const res = await fetch('./samples/drilling_report_sample.pdf')
    upload(new File([await res.blob()], 'drilling_report_sample.pdf', { type: 'application/pdf' }))
  }

  return (
    <div className="col gap-20">
      <SectionTitle eyebrow="AI document extraction" title="Turn a drilling report into data"
        sub="Upload a daily drilling report or well completion report (PDF). The text is read (OCR for scans), then the well, depths, formations, problems and lessons are pulled out and saved, so they show up in search and on the map." />
      <div className="card" onDragOver={(e) => e.preventDefault()} onDrop={(e) => { e.preventDefault(); upload(e.dataTransfer.files[0]) }}
        style={{ borderStyle: 'dashed', borderWidth: 2, textAlign: 'center', padding: 36 }}>
        <FileUp size={30} className="muted" />
        <h3 className="mt-8">Drop a PDF here</h3>
        <p className="small muted mt-4">{mode.data?.text}{mode.data && !mode.data.llm_enabled && !IS_DEMO && ' – set ANTHROPIC_API_KEY on the server to use Claude.'}</p>
        <div className="row mt-16" style={{ justifyContent: 'center' }}>
          <button className="btn" onClick={() => input.current.click()} disabled={busy}><FileUp size={15} />Choose file</button>
          <button className="btn ghost" onClick={useSample} disabled={busy}><Sparkles size={15} />Try the sample report</button>
          <a className="btn line" href="./samples/drilling_report_sample.pdf" target="_blank" rel="noreferrer">View sample PDF</a>
        </div>
        <input ref={input} type="file" accept=".pdf,.txt,.png,.jpg,.jpeg" hidden onChange={(e) => upload(e.target.files[0])} />
      </div>
      {busy && <Loading text="Reading the document…" />}
      {err && <div className="error">{err}</div>}
      {doc && <div className="card"><SectionTitle eyebrow="Result" title={doc.filename} /><Result doc={doc} /></div>}
      <div className="card">
        <SectionTitle eyebrow="History" title="Processed documents" />
        {history.data?.length ? (
          <table className="table"><thead><tr><th>File</th><th>Well</th><th>Events</th><th>Method</th><th>When</th></tr></thead>
            <tbody>{history.data.map((d) => (
              <tr key={d.id} style={{ cursor: 'pointer' }} onClick={() => setDoc(d)}><td>{d.filename}</td><td>{d.well_name || '–'}</td><td className="num">{d.events_created}</td>
                <td>{d.extract_method === 'llm' ? 'LLM' : 'Rules'}</td><td className="small">{fmt.ago(d.created_at)}</td></tr>
            ))}</tbody></table>
        ) : <Empty>No documents yet. Try the sample report.</Empty>}
      </div>
    </div>
  )
}
