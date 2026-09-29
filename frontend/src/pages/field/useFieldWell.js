import { useEffect, useMemo, useState } from 'react'
import { useAuth } from '../../context/AuthContext'
import { useLive } from '../../context/LiveContext'
import { useApi } from '../../lib/util'

const haversine = (a, b, c, d) => {
  const R = 6371000, r = Math.PI / 180
  const x = Math.sin(((c - a) * r) / 2) ** 2 + Math.cos(a * r) * Math.cos(c * r) * Math.sin(((d - b) * r) / 2) ** 2
  return 2 * R * Math.atan2(Math.sqrt(x), Math.sqrt(1 - x))
}

/** The well the field user is looking at: chosen by the user, or the nearest active well to a driller's site. */
export function useFieldWell() {
  const { user } = useAuth()
  const { depths } = useLive()
  const active = useApi('/api/wells', { active: true })
  const me = useApi(user.role === 'driller' ? '/api/driller/me' : null)
  const [chosen, setChosen] = useState(() => { try { return Number(localStorage.getItem('nwis-field-well')) || null } catch { return null } })

  const wellId = useMemo(() => {
    if (!active.data?.length) return null
    if (chosen && active.data.some((w) => w.id === chosen)) return chosen
    if (me.data?.site_lat) {
      return [...active.data].sort((a, b) => haversine(me.data.site_lat, me.data.site_lon, a.lat, a.lon) - haversine(me.data.site_lat, me.data.site_lon, b.lat, b.lon))[0].id
    }
    return active.data[0].id
  }, [active.data, chosen, me.data])

  const choose = (id) => { setChosen(id); try { localStorage.setItem('nwis-field-well', id) } catch { /* ignore */ } }
  const well = active.data?.find((w) => w.id === wellId)
  const analysis = useApi(wellId ? `/api/wells/${wellId}/offsets` : null, { radius_km: 10 })
  const depth = depths[wellId] ?? well?.current_depth_m
  const bucket = depth ? Math.floor(depth / 25) : null
  useEffect(() => { if (bucket !== null) analysis.reload() }, [bucket]) // eslint-disable-line
  return { active: active.data, well, wellId, choose, analysis: analysis.data, depth, me: me.data, reloadMe: me.reload, loading: active.loading }
}
