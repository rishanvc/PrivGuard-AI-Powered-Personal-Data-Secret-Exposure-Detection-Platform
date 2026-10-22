import { NavLink, Outlet } from 'react-router-dom'

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

export default function Layout() {
  return (
    <div className="flex h-full bg-slate-50">
      <aside className="w-60 shrink-0 border-r border-slate-200 bg-white p-4">
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
      </aside>

      <main className="flex-1 overflow-y-auto">
        <div className="mx-auto max-w-5xl px-8 py-8">
          <Outlet />
        </div>
      </main>
    </div>
  )
}
