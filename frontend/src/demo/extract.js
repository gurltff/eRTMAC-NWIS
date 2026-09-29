// JavaScript port of the rule-based extractor (backend/app/services/extraction.py
// + event_classifier.py), used by the browser demo. PDF text comes from pdf.js.

const RULES = [
  ['KICK', /\bkick\b|influx|pit gain|well control|flow check positive|shut[- ]in (the )?well|gas cut mud/i],
  ['STUCK_PIPE', /stuck|pack(ed)?[- ]off|differential(ly)? stick|overpull|tight hole|jarr(ed|ing)/i],
  ['CEMENTING', /cement(ing)? (job|problem|failure)|top of cement|squeeze|channel(l)?ing|micro[- ]?annul|poor bond/i],
  ['MUD_LOSS', /\blosses\b|\bloss(es)? of (mud|returns|circulation)|lost circulation|lost returns|mud loss|partial loss|total loss/i],
  ['TORQUE_SPIKE', /torque spike|erratic torque|high torque|torque (increased|fluctuat)|stick[- ]slip/i],
  ['FISHING', /\bfish(ing)?\b|twist[- ]?off|junk in hole|parted string/i],
  ['NPT', /\bNPT\b|waiting on|rig repair|breakdown|downtime|non[- ]productive/i],
]
export const classify = (t) => (RULES.find(([, rx]) => rx.test(t || '')) || [null])[0]

export function findDepth(t) {
  const m = /(\d{3,5}(?:\.\d+)?)\s*(m|mtr|meters|metres|ft|feet)\b/i.exec(t || '')
  if (!m) return null
  const v = parseFloat(m[1])
  return /^f/i.test(m[2]) ? +(v * 0.3048).toFixed(1) : v
}
const findHours = (t) => { const m = /(\d+(?:\.\d+)?)\s*(hrs|hours|hr|h)\b/i.exec(t || ''); return m ? parseFloat(m[1]) : null }
const ACTION = /\b(pumped|spotted|reduced|raised|increased|jarred|circulated|pulled|reamed|backreamed|shut in|killed|squeezed|set|ran|added|switched|worked|washed|freed|cured)\b/i
const actionSentences = (t) => (t || '').split(/(?<=[.;])\s+/).map((s) => s.trim()).filter((s) => s && ACTION.test(s) && !/^(lesson|cause)/i.test(s)).join(' ') || null
export function severityFrom(type, hours) {
  if (type === 'KICK' || (hours || 0) >= 12) return 'high'
  if ((hours || 0) >= 4 || type === 'STUCK_PIPE' || type === 'FISHING') return 'medium'
  return 'low'
}

const FORMATIONS = ['Alluvium', 'Dhekiajuli', 'Namsang', 'Girujan Clay', 'Tipam Sandstone', 'Barail', 'Kopili Shale', 'Sylhet Limestone', 'Langpar', 'Basement',
  'Girujan', 'Tipam', 'Kopili', 'Sylhet', 'Lakadong', 'Nordland Gp', 'Hordaland Gp', 'Shetland Gp', 'Draupne Fm', 'Heather Fm', 'Hugin Fm', 'Sleipner Fm', 'Skagerrak Fm']
const ALIAS = { Girujan: 'Girujan Clay', Tipam: 'Tipam Sandstone', Kopili: 'Kopili Shale', Sylhet: 'Sylhet Limestone', Lakadong: 'Sylhet Limestone' }
const esc = (s) => s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
function formationIn(s) {
  for (const f of [...FORMATIONS].sort((a, b) => b.length - a.length)) if (new RegExp(`\\b${esc(f)}\\b`, 'i').test(s)) return ALIAS[f] || f
  return null
}
const first = (rx, t) => { const m = rx.exec(t); return m ? m[1].trim() : null }

export function ruleExtract(text) {
  const flat = text.replace(/[ \t]+/g, ' ')
  const well = first(/Well(?:\s*name)?\s*[:-]\s*([A-Za-z0-9][A-Za-z0-9\-/#. ]{1,30}?)(?:\s{2,}|\n|,|;|$)/im, flat) || first(/\b([A-Z]{2,4}-[A-Z]?\d{1,4}[A-Z]?)\b/, flat)
  const lat = parseFloat(first(/Lat(?:itude)?\s*[:-]?\s*([0-9]{1,2}\.[0-9]+)/i, flat)) || null
  const lon = parseFloat(first(/Lon(?:gitude)?\s*[:-]?\s*([0-9]{2,3}\.[0-9]+)/i, flat)) || null
  const td = first(/(?:Total depth|TD|Final depth)\s*(?:reached)?\s*[:-]?\s*([0-9][0-9,.]*\s*(?:m|ft))/i, flat)
  const formations = {}
  for (const line of text.split('\n')) {
    const fm = formationIn(line)
    if (!fm) continue
    const m = /(?:top|tops?\s*at|at|:)?\s*([0-9]{3,5}(?:\.[0-9]+)?)\s*(m|ft)\b/i.exec(line)
    if (m && (/top/i.test(line) || /^\s*[A-Za-z ]+\s*[:-]?\s*[0-9]/.test(line))) { const d = findDepth(m[0]); if (d && !(fm in formations)) formations[fm] = d }
  }
  const tops = Object.entries(formations).sort((a, b) => a[1] - b[1])
  const fmAt = (d) => { let n = null; for (const [f, t] of tops) if (d !== null && d >= t) n = f; return n }
  const header = /^\s*(well( name)?|field|operator|rig|report date|date|latitude|longitude|lat|lon|total depth|td|[A-Za-z ]{3,30}\btop)\s*:/i
  // Short lines without end punctuation are headings: close them so they don't glue onto the next sentence.
  const body = text.split('\n').map((l) => l.trim()).filter((l) => l && !header.test(l))
    .map((l) => (l.length < 60 && !/[.!?:;,]$/.test(l) ? `${l}.` : l)).join(' ')
  const sentences = body.split(/(?<=[.!?])\s+/).map((s) => s.trim()).filter(Boolean)
  const events = [], lessons = []
  sentences.forEach((s, i) => {
    const low = s.toLowerCase()
    if (/^(lesson|recommendation)/.test(low) || low.includes('in future')) {
      const clean = s.replace(/^((lessons?( learnt| learned)?|recommendations?)\s*[:-]?\s*)+/i, '').trim()
      lessons.push(clean)
      if (events.length && !events[events.length - 1].lesson && !low.startsWith('lessons learnt')) events[events.length - 1].lesson = clean
      return
    }
    const type = classify(s)
    if (!type) return
    const depth = findDepth(s)
    if (depth === null && events.length && events[events.length - 1].event_type === type) return
    const ctx = [s, ...sentences.slice(i + 1, i + 3).filter((t) => findDepth(t) === null && (!classify(t) || classify(t) === type))]
    const context = ctx.join(' ')
    const fm = formationIn(s)
    events.push({
      event_type: type, depth_m: depth ?? formations[fm] ?? null, formation: fm || fmAt(depth), description: s.slice(0, 400),
      cause: first(/(?:cause[d]?\s*(?:by)?|due to|because of)\s*[:-]?\s*([^.;]+)/i, context),
      action_taken: actionSentences(ctx.slice(1).join(' ')) || actionSentences(s),
      lesson: first(/lesson\s*[:-]\s*(.+?)(?:\.\s|\.$|$)/i, context), npt_hours: findHours(context),
    })
  })
  return {
    well_name: well, field: first(/Field\s*[:-]\s*([A-Za-z][A-Za-z ]{2,30}?)(?:\s{2,}|\n|,|;|$)/im, flat),
    operator: first(/Operator\s*[:-]\s*([A-Za-z][A-Za-z &.()]{2,60}?)(?:\s{2,}|\n|,|;|$)/im, flat),
    report_date: first(/(?:Report date|Date)\s*[:-]\s*([0-9]{1,4}[-/.][0-9]{1,2}[-/.][0-9]{1,4})/i, flat),
    rig: first(/Rig\s*[:-]\s*([A-Za-z0-9][A-Za-z0-9\- ]{1,30}?)(?:\s{2,}|\n|,|;|$)/im, flat),
    lat, lon, total_depth_m: td ? findDepth(td) : null,
    formations: tops.map(([name, top_m]) => ({ name, top_m })), events, lessons,
    summary: `Rule-based extraction found ${events.length} event(s) and ${tops.length} formation top(s).`,
  }
}

export async function fileText(file) {
  const name = file.name.toLowerCase()
  if (name.endsWith('.txt')) return [await file.text(), 'plain-text']
  if (!name.endsWith('.pdf')) throw Object.assign(new Error('The browser demo reads PDF and .txt files. Image OCR needs the full backend.'), { status: 400 })
  const pdfjs = await import('pdfjs-dist')
  const worker = (await import('pdfjs-dist/build/pdf.worker.min.mjs?url')).default
  pdfjs.GlobalWorkerOptions.workerSrc = worker
  const doc = await pdfjs.getDocument({ data: await file.arrayBuffer() }).promise
  let text = ''
  for (let p = 1; p <= doc.numPages; p++) {
    const content = await (await doc.getPage(p)).getTextContent()
    for (const it of content.items) text += it.str + (it.hasEOL ? '\n' : '')
    text += '\n'
  }
  return [text, 'pdf-text']
}
