import { EventsTable } from './OffsetPage'
import { ErrorBox, Loading, SectionTitle } from '../components/ui'
import { useApi } from '../lib/util'

export default function KnowledgePage() {
  const ev = useApi('/api/events', { limit: 1000 })
  if (ev.loading) return <Loading />
  if (ev.error) return <ErrorBox error={ev.error} />
  const lessons = ev.data.items.filter((e) => e.lesson)
  return (
    <div className="col gap-20">
      <SectionTitle eyebrow="Knowledge base" title="Every problem, cause and fix"
        sub="Drilling events pulled from daily drilling reports, completion reports and uploaded documents. Search by words like 'Girujan', 'LCM', 'jarred' or a well name. Click a row for the full story." />
      <div className="card"><EventsTable events={ev.data.items} /></div>
      <div className="card">
        <SectionTitle eyebrow="Lessons learned" title="Most repeated advice" />
        <div className="list">
          {Object.entries(lessons.reduce((acc, e) => { (acc[e.lesson] = acc[e.lesson] || []).push(e); return acc }, {}))
            .sort((a, b) => b[1].length - a[1].length).slice(0, 12).map(([lesson, es]) => (
              <div key={lesson} className="item">
                <div style={{ fontFamily: 'var(--serif)', fontSize: 16 }}>{lesson}</div>
                <div className="small muted mt-4">From {es.length} event(s): {[...new Set(es.map((e) => e.well_name))].slice(0, 6).join(', ')}</div>
              </div>
            ))}
        </div>
      </div>
    </div>
  )
}
