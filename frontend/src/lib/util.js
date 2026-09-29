import { useCallback, useEffect, useState } from 'react'
import { api } from '../api/client'

// Event types keep a fixed categorical slot (never re-assigned by rank or filter).
export const EVENT_META = {
  MUD_LOSS: { label: 'Mud loss', color: 'var(--s1)' },
  STUCK_PIPE: { label: 'Stuck pipe', color: 'var(--s2)' },
  TORQUE_SPIKE: { label: 'Torque spike', color: 'var(--s3)' },
  KICK: { label: 'Kick / overpressure', color: 'var(--s4)' },
  CEMENTING: { label: 'Cementing problem', color: 'var(--s5)' },
  FISHING: { label: 'Fishing job', color: 'var(--s6)' },
  NPT: { label: 'Non-productive time', color: 'var(--s7)' },
}
export const EVENT_TYPES = Object.keys(EVENT_META)

export const SEVERITY = {
  high: { label: 'High', cls: 'critical' },
  medium: { label: 'Medium', cls: 'serious' },
  low: { label: 'Low', cls: 'warn' },
}
export const LEVEL_CLS = { High: 'critical', Medium: 'serious', Low: 'good' }

export const TRACK_STATUS = {
  INSIDE: { label: 'Inside zone', cls: 'good' },
  NEAR_EDGE: { label: 'Near edge', cls: 'warn' },
  OUTSIDE: { label: 'Outside zone', cls: 'critical' },
  ILLEGAL_ZONE: { label: 'In illegal zone', cls: 'critical' },
  NO_ZONE: { label: 'No zone', cls: '' },
}

export const fmt = {
  n: (v, d = 0) => (v === null || v === undefined || Number.isNaN(v) ? '–' : Number(v).toLocaleString('en-IN', { maximumFractionDigits: d, minimumFractionDigits: d })),
  m: (v) => (v === null || v === undefined ? '–' : `${Math.round(v).toLocaleString('en-IN')} m`),
  km: (m) => (m === null || m === undefined ? '–' : `${(m / 1000).toFixed(m < 10000 ? 2 : 1)} km`),
  bbl: (v) => {
    if (v === null || v === undefined) return '–'
    if (v >= 1e6) return `${(v / 1e6).toFixed(2)} million bbl`
    if (v >= 1e3) return `${Math.round(v / 1e3).toLocaleString('en-IN')}k bbl`
    return `${Math.round(v)} bbl`
  },
  ago: (iso) => {
    if (!iso) return '–'
    const s = (Date.now() - new Date(iso).getTime()) / 1000
    if (s < 60) return 'just now'
    if (s < 3600) return `${Math.round(s / 60)} min ago`
    if (s < 86400) return `${Math.round(s / 3600)} h ago`
    return `${Math.round(s / 86400)} d ago`
  },
  time: (iso) => (iso ? new Date(iso).toLocaleString('en-IN', { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' }) : '–'),
  coord: (lat, lon) => (lat === null || lat === undefined ? '–' : `${lat.toFixed(4)}° N, ${lon.toFixed(4)}° E`),
  title: (s) => (s ? s.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase()) : ''),
}

// Small data-fetching hook: const { data, error, loading, reload } = useApi('/api/x', params)
export function useApi(path, params, deps = []) {
  const [state, setState] = useState({ data: null, error: null, loading: !!path })
  const key = JSON.stringify(params || {})
  const load = useCallback(async () => {
    if (!path) return
    setState((s) => ({ ...s, loading: true, error: null }))
    try {
      const data = await api(path, { params })
      setState({ data, error: null, loading: false })
    } catch (e) {
      setState({ data: null, error: e.message, loading: false })
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [path, key, ...deps])
  useEffect(() => { load() }, [load])
  return { ...state, reload: load, setData: (d) => setState((s) => ({ ...s, data: typeof d === 'function' ? d(s.data) : d })) }
}
