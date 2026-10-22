import { useState } from 'react'
import { NavLink, Outlet } from 'react-router-dom'

import { useAuth } from '../auth/useAuth'

/**
 * Application shell: sidebar navigation + content area.
 * Screens follow SRS 5.1. Most are placeholders until their cycle arrives.
 */

const NAV = [
  { to: '/',         label: 'Dashboard', end: true },
  { to: '/scans',    label: 'Scans' },
  { to: '/findings', label: 'Findings' },
  { to: '/reports',  label: 'Reports' },
  { to: '/settings', label: 'Settings' },
]

function linkClass({ isActive }) {
  return [
    'block rounded-md px-3 py-2 text-sm font-medium transition-colors',
    isActive
      ? 'bg-slate-900 text-white'
      : 'text-slate-600 hover:bg-slate-100 hover:text-slate-900',
  ].join(' ')
}

function UserPanel() {
  const { user, logout } = useAuth()
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)

  async function handleLogout() {
    setBusy(true)
    setError(null)
    try {
      await logout() // on success, RequireAuth redirects to /login
    } catch {
      // The session may still be valid server-side, so say so plainly.
      setError('Logout failed. You may still be signed in.')
      setBusy(false)
    }
  }

  return (
    <div className="mt-auto border-t border-slate-200 pt-4">
      <div className="px-3">
        <p className="truncate text-sm font-medium text-slate-900">{user?.username}</p>
        <p className="text-xs text-slate-500">{user?.role_display}</p>
      </div>
      <button
        type="button"
        onClick={handleLogout}
        disabled={busy}
        className="mt-3 w-full rounded-md px-3 py-2 text-left text-sm font-medium text-slate-600
                   hover:bg-slate-100 hover:text-slate-900 disabled:opacity-50"
      >
        {busy ? 'Signing out…' : 'Log out'}
      </button>
      {error && <p role="alert" className="mt-1 px-3 text-xs text-red-700">{error}</p>}
    </div>
  )
}

export default function Layout() {
  return (
    <div className="flex h-full bg-slate-50">
      <aside className="flex w-60 shrink-0 flex-col border-r border-slate-200 bg-white p-4">
        <div className="mb-6 px-3">
          <h1 className="text-lg font-semibold text-slate-900">PrivGuard</h1>
          <p className="text-xs text-slate-500">Exposure detection</p>
        </div>
        <nav className="space-y-1">
          {NAV.map(({ to, label, end }) => (
            <NavLink key={to} to={to} end={end} className={linkClass}>
              {label}
            </NavLink>
          ))}
        </nav>
        <UserPanel />
      </aside>

      <main className="flex-1 overflow-y-auto">
        <div className="mx-auto max-w-5xl px-8 py-8">
          <Outlet />
        </div>
      </main>
    </div>
  )
}
