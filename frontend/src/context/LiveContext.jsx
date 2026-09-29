import { createContext, useCallback, useContext, useEffect, useRef, useState } from 'react'
import { openLive } from '../api/client'
import { useAuth } from './AuthContext'

// One shared live connection. Keeps the latest driller positions, well depths,
// recent breaches and alerts, and shows toasts for the important ones.
const LiveCtx = createContext(null)

export function LiveProvider({ children }) {
  const { user } = useAuth()
  const [positions, setPositions] = useState({})   // user_id -> position msg
  const [depths, setDepths] = useState({})         // well_id -> depth
  const [breaches, setBreaches] = useState([])
  const [wellAlerts, setWellAlerts] = useState([])
  const [toasts, setToasts] = useState([])
  const [connected, setConnected] = useState(false)
  const listeners = useRef(new Set())
  const sendRef = useRef(null)

  const toast = useCallback((t) => {
    const id = Math.random().toString(36).slice(2)
    setToasts((xs) => [...xs.slice(-3), { id, ...t }])
    setTimeout(() => setToasts((xs) => xs.filter((x) => x.id !== id)), t.ttl || 7000)
  }, [])

  useEffect(() => {
    if (!user) return
    let close = () => {}
    let alive = true
    openLive((msg) => {
      listeners.current.forEach((fn) => fn(msg))
      if (msg.type === 'position') setPositions((p) => ({ ...p, [msg.user_id]: msg }))
      else if (msg.type === 'depth') setDepths((d) => ({ ...d, [msg.well_id]: msg.depth_m }))
      else if (msg.type === 'breach') {
        setBreaches((b) => [msg, ...b].slice(0, 50))
        toast({ tone: msg.is_breach ? 'critical' : (msg.event_type === 'RETURNED_TO_ZONE' ? 'good' : 'serious'),
                 title: `${msg.name}: ${msg.text}`,
                 body: msg.zone_name ? `Zone: ${msg.zone_name}` : `${msg.distance_m} m from site (limit ${msg.radius_m} m)` })
      } else if (msg.type === 'well_alert') {
        setWellAlerts((a) => [msg, ...a].slice(0, 50))
        toast({ tone: msg.severity === 'high' ? 'critical' : 'serious', title: `${msg.well_name}: ${msg.title}`, body: msg.recommendation, ttl: 9000 })
      }
    }).then((c) => { if (alive) { close = c; sendRef.current = c.send; setConnected(true) } else c() })
    return () => { alive = false; close(); setConnected(false) }
  }, [user, toast])

  const subscribe = useCallback((fn) => { listeners.current.add(fn); return () => listeners.current.delete(fn) }, [])
  const send = useCallback((msg) => sendRef.current && sendRef.current(msg), [])

  return (
    <LiveCtx.Provider value={{ positions, depths, breaches, wellAlerts, toasts, toast, connected, subscribe, send }}>
      {children}
    </LiveCtx.Provider>
  )
}

export const useLive = () => useContext(LiveCtx)
