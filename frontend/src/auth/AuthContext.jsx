import { useCallback, useEffect, useMemo, useState } from 'react'

import { apiGet, apiPost, setCsrfToken, setSessionCheck } from '../lib/api'
import { AuthContext } from './useAuth'

/**
 * Who is logged in, and how to change that.
 *
 * The browser never holds a credential we can read - the session lives in an
 * HttpOnly cookie. So "am I logged in?" is answered by asking the server
 * (GET /auth/me/), not by checking local storage.
 *
 * status: 'loading'       - asking the server
 *         'authenticated' - user is set
 *         'anonymous'     - not logged in (or the backend is unreachable)
 */

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null)
  const [status, setStatus] = useState('loading')

  useEffect(() => {
    let cancelled = false
    apiGet('/auth/me/')
      .then((me) => {
        if (cancelled) return
        setUser(me)
        setStatus('authenticated')
      })
      .catch(() => {
        // 403 means "not logged in". A network failure also lands here; the
        // login form reports "Cannot reach the backend" when the user tries.
        if (cancelled) return
        setUser(null)
        setStatus('anonymous')
      })
    return () => {
      cancelled = true
    }
  }, [])

  // Session expiry while the tab is open (deferred from Cycle 2). When any API
  // call is refused with 401/403, ask the server whether we're still logged
  // in. Only a 401/403 from /auth/me/ itself logs the UI out - a network blip
  // must not, and an ordinary "not allowed" leaves /auth/me/ answering 200.
  useEffect(() => {
    setSessionCheck(() => {
      apiGet('/auth/me/')
        .then((me) => setUser(me))
        .catch((err) => {
          if (err?.status === 401 || err?.status === 403) {
            setUser(null)
            setStatus('anonymous') // RequireAuth now redirects to /login
          }
        })
    })
    return () => setSessionCheck(null)
  }, [])

  const login = useCallback(async (identifier, password) => {
    const data = await apiPost('/auth/login/', { identifier, password })
    // Django's login() rotated the CSRF token; the old one is now invalid.
    setCsrfToken(data.csrfToken)
    setUser(data.user)
    setStatus('authenticated')
    return data.user
  }, [])

  const logout = useCallback(async () => {
    // State is cleared only AFTER the server confirms. If the request failed
    // and we cleared it anyway, the UI would claim "logged out" while a valid
    // session cookie still existed - misleading on a shared computer.
    await apiPost('/auth/logout/')
    setUser(null)
    setStatus('anonymous')
  }, [])

  const value = useMemo(() => ({ user, status, login, logout }), [user, status, login, logout])
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}
