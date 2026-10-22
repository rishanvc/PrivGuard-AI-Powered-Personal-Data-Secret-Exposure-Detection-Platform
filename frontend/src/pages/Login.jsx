import { useState } from 'react'
import { Navigate, useLocation } from 'react-router-dom'

import { useAuth } from '../auth/useAuth'
import { ApiError } from '../lib/api'

/**
 * Login screen (SRS 5.1.1): username-or-email, password, clear errors.
 *
 * After login the user returns to the page they originally asked for. That
 * target comes only from router state set by RequireAuth - never from a
 * ?next= query parameter, which is how open-redirect phishing works.
 */
export default function Login() {
  const { status, login } = useAuth()
  const location = useLocation()

  const [identifier, setIdentifier] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState(null)
  const [submitting, setSubmitting] = useState(false)

  const destination = location.state?.from?.pathname ?? '/'

  if (status === 'authenticated') {
    return <Navigate to={destination} replace />
  }

  async function handleSubmit(event) {
    event.preventDefault()
    setError(null)
    setSubmitting(true)
    try {
      await login(identifier.trim(), password)
      // No navigate() needed: status becomes 'authenticated' and the
      // <Navigate> above takes over on the next render.
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Unexpected error. Please try again.')
      setPassword('') // don't leave a failed password sitting in the field
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="flex min-h-full items-center justify-center bg-slate-50 px-4 py-12">
      <div className="w-full max-w-sm">
        <div className="mb-8 text-center">
          <h1 className="text-2xl font-semibold text-slate-900">PrivGuard</h1>
          <p className="mt-1 text-sm text-slate-500">Sign in to continue</p>
        </div>

        <form
          onSubmit={handleSubmit}
          className="space-y-5 rounded-lg border border-slate-200 bg-white p-6 shadow-sm"
          noValidate
        >
          {error && (
            <div role="alert" className="rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-800">
              {error}
            </div>
          )}

          <div>
            <label htmlFor="identifier" className="block text-sm font-medium text-slate-700">
              Username or email
            </label>
            <input
              id="identifier"
              name="identifier"
              type="text"
              autoComplete="username"
              autoFocus
              required
              value={identifier}
              onChange={(e) => setIdentifier(e.target.value)}
              className="mt-1 block w-full rounded-md border border-slate-300 px-3 py-2 text-sm
                         focus:border-slate-900 focus:ring-1 focus:ring-slate-900 focus:outline-none"
            />
          </div>

          <div>
            <label htmlFor="password" className="block text-sm font-medium text-slate-700">
              Password
            </label>
            <input
              id="password"
              name="password"
              type="password"
              autoComplete="current-password"
              required
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="mt-1 block w-full rounded-md border border-slate-300 px-3 py-2 text-sm
                         focus:border-slate-900 focus:ring-1 focus:ring-slate-900 focus:outline-none"
            />
          </div>

          <button
            type="submit"
            disabled={submitting || !identifier.trim() || !password}
            className="w-full rounded-md bg-slate-900 px-3 py-2 text-sm font-medium text-white
                       hover:bg-slate-800 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {submitting ? 'Signing in…' : 'Sign in'}
          </button>
        </form>
      </div>
    </div>
  )
}
