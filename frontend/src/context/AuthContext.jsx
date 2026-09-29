import { createContext, useCallback, useContext, useEffect, useState } from 'react'
import { api, getToken, setToken } from '../api/client'

const AuthCtx = createContext(null)

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null)
  const [loading, setLoading] = useState(true)

  const refresh = useCallback(async () => {
    if (!getToken()) { setUser(null); setLoading(false); return }
    try { setUser(await api('/api/auth/me')) } catch { setToken(null); setUser(null) }
    setLoading(false)
  }, [])

  useEffect(() => {
    refresh()
    const onLogout = () => setUser(null)
    window.addEventListener('nwis-logout', onLogout)
    return () => window.removeEventListener('nwis-logout', onLogout)
  }, [refresh])

  const login = async (email, password) => {
    const r = await api('/api/auth/login', { method: 'POST', body: { email, password } })
    setToken(r.token); setUser(r.user); return r.user
  }
  const register = async (full_name, email, password) => {
    const r = await api('/api/auth/register', { method: 'POST', body: { full_name, email, password } })
    setToken(r.token); setUser(r.user); return r.user
  }
  const logout = () => { setToken(null); setUser(null) }

  return <AuthCtx.Provider value={{ user, loading, login, register, logout, refresh }}>{children}</AuthCtx.Provider>
}

export const useAuth = () => useContext(AuthCtx)
