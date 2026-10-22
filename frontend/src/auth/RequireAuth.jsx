import { Navigate, useLocation } from 'react-router-dom'

import { useAuth } from './useAuth'

/**
 * Route guard: renders children only for a logged-in user.
 *
 * This is a UX convenience, NOT a security boundary. Anyone can edit the
 * JavaScript in their own browser. What actually protects data is the
 * backend's IsAuthenticated + ownership checks on every API request.
 */
export default function RequireAuth({ children }) {
  const { status } = useAuth()
  const location = useLocation()

  if (status === 'loading') {
    return (
      <div className="flex h-full items-center justify-center bg-slate-50 text-sm text-slate-500">
        Checking your session…
      </div>
    )
  }

  if (status === 'anonymous') {
    // Remember where they were going, in router state (not a URL parameter).
    return <Navigate to="/login" replace state={{ from: location }} />
  }

  return children
}
