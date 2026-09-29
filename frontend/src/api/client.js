// Thin API client. In the hosted demo build (__DEMO__) every call is answered by
// the in-browser demo backend in src/demo instead of the FastAPI server.
const API_BASE = import.meta.env.VITE_API_BASE || ''
export const IS_DEMO = typeof __DEMO__ !== 'undefined' && __DEMO__

let demoServer = null
async function demo() {
  if (!demoServer) demoServer = (await import('../demo/server.js')).default
  return demoServer
}

export function getToken() {
  try { return localStorage.getItem('nwis-token') } catch { return null }
}
export function setToken(t) {
  try { t ? localStorage.setItem('nwis-token', t) : localStorage.removeItem('nwis-token') } catch { /* private mode */ }
}

export class ApiError extends Error {
  constructor(status, message) { super(message); this.status = status }
}

export async function api(path, { method = 'GET', body, form, params } = {}) {
  let url = path
  if (params) {
    const q = new URLSearchParams()
    Object.entries(params).forEach(([k, v]) => { if (v !== undefined && v !== null && v !== '') q.set(k, v) })
    const s = q.toString()
    if (s) url += (url.includes('?') ? '&' : '?') + s
  }
  if (IS_DEMO) {
    const srv = await demo()
    try {
      return await srv.handle(method, url, body ?? form, getToken())
    } catch (e) {
      throw new ApiError(e.status || 500, e.message || 'Something went wrong')
    }
  }
  const headers = {}
  const token = getToken()
  if (token) headers.Authorization = `Bearer ${token}`
  let payload
  if (form) payload = form
  else if (body !== undefined) { headers['Content-Type'] = 'application/json'; payload = JSON.stringify(body) }
  const res = await fetch(API_BASE + url, { method, headers, body: payload })
  if (!res.ok) {
    let msg = res.statusText
    try {
      const j = await res.json()
      msg = typeof j.detail === 'string' ? j.detail : (j.detail?.[0]?.msg || msg)
    } catch { /* not json */ }
    if (res.status === 401 && token) { setToken(null); window.dispatchEvent(new Event('nwis-logout')) }
    throw new ApiError(res.status, msg)
  }
  const type = res.headers.get('content-type') || ''
  return type.includes('application/json') ? res.json() : res.blob()
}

// Live feed: websocket to FastAPI, or the demo event bus.
export async function openLive(onMessage) {
  if (IS_DEMO) {
    const srv = await demo()
    return srv.subscribe(onMessage)
  }
  const token = getToken()
  if (!token) return () => {}
  let ws, closed = false, retry
  const connect = () => {
    const base = API_BASE || window.location.origin
    const url = base.replace(/^http/, 'ws') + `/ws/live?token=${encodeURIComponent(token)}`
    ws = new WebSocket(url)
    ws.onmessage = (ev) => { try { onMessage(JSON.parse(ev.data)) } catch { /* ignore */ } }
    ws.onclose = () => { if (!closed) retry = setTimeout(connect, 2500) }
  }
  connect()
  const close = () => { closed = true; clearTimeout(retry); ws && ws.close() }
  close.send = (msg) => { if (ws && ws.readyState === 1) ws.send(JSON.stringify(msg)) }
  return close
}
