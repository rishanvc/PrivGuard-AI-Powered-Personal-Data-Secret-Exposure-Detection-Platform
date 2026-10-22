import { createContext, useContext } from 'react'

/**
 * The auth context object and its hook.
 *
 * Kept apart from AuthProvider (AuthContext.jsx) so that file exports only a
 * component - Vite's fast refresh can then hot-swap it without a full reload.
 */
export const AuthContext = createContext(null)

export function useAuth() {
  const context = useContext(AuthContext)
  if (!context) throw new Error('useAuth() must be used inside <AuthProvider>.')
  return context
}
