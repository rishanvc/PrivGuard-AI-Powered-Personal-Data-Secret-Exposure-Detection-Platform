import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'

import StatusPill from '../components/StatusPill'
import { apiGet, ApiError, BASE_URL } from '../lib/api'
import { formatDateTime } from '../lib/format'

/**
 * Dashboard (SRS 5.1.2): system health (FR-119), the caller's own totals
 * (FR-081), and recent scans.
 *
 * Numbers the system cannot know yet are shown as "—", never 0. Zero findings
 * would claim "we looked and found nothing"; nothing has looked yet.
 */

const COMPONENT_LABELS = {
  backend: 'Backend',
  database: 'Database',
  ocr: 'OCR engine',
  ai: 'Local AI',
}

function MetricCard({ label, value, hint }) {
  return (
    <div className="rounded-lg border border-slate-200 bg-white p-4">
      <p className="text-xs font-medium uppercase tracking-wide text-slate-500">{label}</p>
      <p className="mt-1 text-2xl font-semibold text-slate-900">{value ?? '—'}</p>
      {hint && <p className="mt-1 text-xs text-slate-400">{hint}</p>}
    </div>
  )
}

/** Fetch once on mount; report data or an error. */
function useApi(path) {
  const [state, setState] = useState({ data: null, error: null, loading: true })
  useEffect(() => {
    let cancelled = false
    apiGet(path)
      .then((data) => { if (!cancelled) setState({ data, error: null, loading: false }) })
      .catch((error) => { if (!cancelled) setState({ data: null, error, loading: false }) })
    return () => { cancelled = true }
  }, [path])
  return state
}

export default function Dashboard() {
  const health = useApi('/health/')
  const summary = useApi('/dashboard/')
  const recent = useApi('/scans/')

  const s = summary.data

  return (
    <div className="space-y-8">
      <header className="flex items-start justify-between gap-4">
        <div>
          <h2 className="text-2xl font-semibold text-slate-900">Dashboard</h2>
          <p className="mt-1 text-sm text-slate-500">System status and scan overview.</p>
        </div>
        <Link to="/scans/new" className="rounded-md bg-slate-900 px-4 py-2 text-sm font-medium text-white hover:bg-slate-800">
          New scan
        </Link>
      </header>

      <section>
        <h3 className="mb-3 text-sm font-semibold text-slate-900">Scan overview</h3>
        {summary.error ? (
          <p role="alert" className="text-sm text-red-700">
            {summary.error instanceof ApiError ? summary.error.message : 'Could not load totals.'}
          </p>
        ) : (
          <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
            <MetricCard label="Total scans" value={s?.total_scans} />
            <MetricCard
              label="Files scanned"
              value={s?.files_scanned}
              hint={s ? `${s.files_accepted} accepted, awaiting processing` : null}
            />
            <MetricCard label="Findings" value={s?.total_findings} hint="Detection arrives in Cycle 5" />
            <MetricCard label="Critical / high" value={s?.critical_high_findings} hint="Severity arrives in Cycle 7" />
          </div>
        )}
      </section>

      <section>
        <div className="mb-3 flex items-center justify-between">
          <h3 className="text-sm font-semibold text-slate-900">Recent scans</h3>
          <Link to="/scans" className="text-sm text-slate-500 hover:text-slate-900">View all</Link>
        </div>
        {recent.loading && <p className="text-sm text-slate-500">Loading…</p>}
        {recent.data?.count === 0 && (
          <p className="rounded-lg border border-dashed border-slate-300 bg-white p-6 text-center text-sm text-slate-500">
            No scans yet.
          </p>
        )}
        {recent.data?.count > 0 && (
          <ul className="divide-y divide-slate-100 overflow-hidden rounded-lg border border-slate-200 bg-white">
            {recent.data.results.slice(0, 5).map((scan) => (
              <li key={scan.id}>
                <Link to={`/scans/${scan.id}`} className="flex items-center justify-between gap-4 px-4 py-3 hover:bg-slate-50">
                  <span className="min-w-0">
                    <span className="block truncate text-sm font-medium text-slate-900">{scan.name}</span>
                    <span className="text-xs text-slate-500">
                      {scan.total_files} files · {formatDateTime(scan.created_at)}
                    </span>
                  </span>
                  <StatusPill status={scan.status}>{scan.status_display}</StatusPill>
                </Link>
              </li>
            ))}
          </ul>
        )}
      </section>

      <section>
        <div className="mb-3 flex items-center justify-between">
          <h3 className="text-sm font-semibold text-slate-900">System status</h3>
          {health.data && <StatusPill status={health.data.status} />}
        </div>

        {health.loading && (
          <div className="rounded-lg border border-slate-200 bg-white p-6 text-sm text-slate-500">Checking backend…</div>
        )}

        {/* Network-level failure: the backend never answered. Distinct from a
            backend that answered "degraded" - different cause, different fix. */}
        {health.error && (
          <div className="rounded-lg border border-red-200 bg-red-50 p-6">
            <p className="text-sm font-medium text-red-800">
              {health.error instanceof ApiError ? health.error.message : 'Unexpected error.'}
            </p>
            <p className="mt-2 text-xs text-red-700">
              Expected the API at <code className="font-mono">{BASE_URL}</code>. Check that the Django server is
              running and that this origin is in CORS_ALLOWED_ORIGINS.
            </p>
          </div>
        )}

        {health.data && (
          <div className="overflow-hidden rounded-lg border border-slate-200 bg-white">
            <table className="w-full text-sm">
              <tbody className="divide-y divide-slate-100">
                {Object.entries(health.data.components).map(([key, component]) => (
                  <tr key={key}>
                    <td className="px-4 py-3 font-medium text-slate-900">{COMPONENT_LABELS[key] ?? key}</td>
                    <td className="px-4 py-3">
                      <StatusPill status={component.status} />
                    </td>
                    <td className="px-4 py-3 text-slate-500">{component.detail}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            <div className="border-t border-slate-100 bg-slate-50 px-4 py-2 text-xs text-slate-500">
              PrivGuard v{health.data.version}
            </div>
          </div>
        )}
      </section>
    </div>
  )
}
