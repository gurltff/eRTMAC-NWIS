import { createContext, useContext, useEffect, useState } from 'react'

const ThemeCtx = createContext(null)
const systemDark = () => window.matchMedia?.('(prefers-color-scheme: dark)').matches

export function ThemeProvider({ children }) {
  const [pref, setPref] = useState(() => { try { return localStorage.getItem('nwis-theme') || 'system' } catch { return 'system' } })
  const [sys, setSys] = useState(systemDark())

  useEffect(() => {
    const mq = window.matchMedia?.('(prefers-color-scheme: dark)')
    const on = (e) => setSys(e.matches)
    mq?.addEventListener?.('change', on)
    return () => mq?.removeEventListener?.('change', on)
  }, [])

  useEffect(() => {
    const root = document.documentElement
    if (pref === 'system') root.removeAttribute('data-theme'); else root.setAttribute('data-theme', pref)
    try { localStorage.setItem('nwis-theme', pref) } catch { /* ignore */ }
  }, [pref])

  const resolved = pref === 'system' ? (sys ? 'dark' : 'light') : pref
  const toggle = () => setPref(resolved === 'dark' ? 'light' : 'dark')
  return <ThemeCtx.Provider value={{ pref, setPref, resolved, toggle }}>{children}</ThemeCtx.Provider>
}

export const useTheme = () => useContext(ThemeCtx)
