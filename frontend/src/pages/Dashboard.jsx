import { useEffect, useState } from 'react'

import StatusPill from '../components/StatusPill'
import { apiGet, ApiError, BASE_URL } from '../lib/api'

/**
 * Dashboard (SRS 5.1.2).
 *
 * Cycle 1 shows live backend component health (FR-119, FR-120). The scan and
 * finding metrics are deliberately shown as "no data" placeholders rather than
 * invented numbers - they become real in Cycle 7.
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
      <p className="mt-1 text-2xl font-semibold text-slate-900">{value}</p>
      {hint && <p className="mt-1 text-xs text-slate-400">{hint}</p>}
    </div>
  )
}

export default function Dashboard() {
  // Three distinct states - NFR-037 requires clear feedback for each.
  const [health, setHealth] = useState(null)
  const [error, setError] = useState(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    let cancelled = false

    apiGet('/health/')
      .then((data) => { if (!cancelled) { setHealth(data); setError(null) } })
      .catch((err) => { if (!cancelled) { setError(err); setHealth(null) } })
      .finally(() => { if (!cancelled) setLoading(false) })

    return () => { cancelled = true }
  }, [])

  return (
    <div className="space-y-8">
      <header>
        <h2 className="text-2xl font-semibold text-slate-900">Dashboard</h2>
        <p className="mt-1 text-sm text-slate-500">
          System status and scan overview.
        </p>
      </header>

      <section>
        <div className="mb-3 flex items-center justify-between">
          <h3 className="text-sm font-semibold text-slate-900">System status</h3>
          {health && <StatusPill status={health.status} />}
        </div>

        {loading && (
          <div className="rounded-lg border border-slate-200 bg-white p-6 text-sm text-slate-500">
            Checking backend…
          </div>
        )}

        {/* Network-level failure: the backend never answered. Distinct from a
            backend that answered "degraded" - different cause, different fix. */}
        {error && (
          <div className="rounded-lg border border-red-200 bg-red-50 p-6">
            <p className="text-sm font-medium text-red-800">
              {error instanceof ApiError ? error.message : 'Unexpected error.'}
            </p>
            <p className="mt-2 text-xs text-red-700">
              Expected the API at <code className="font-mono">{BASE_URL}</code>. Check that
              the Django server is running and that this origin is in CORS_ALLOWED_ORIGINS.
            </p>
          </div>
        )}

        {health && (
          <div className="overflow-hidden rounded-lg border border-slate-200 bg-white">
            <table className="w-full text-sm">
              <tbody className="divide-y divide-slate-100">
                {Object.entries(health.components).map(([key, component]) => (
                  <tr key={key}>
                    <td className="px-4 py-3 font-medium text-slate-900">
                      {COMPONENT_LABELS[key] ?? key}
                    </td>
                    <td className="px-4 py-3">
                      <StatusPill status={component.status} />
                    </td>
                    <td className="px-4 py-3 text-slate-500">{component.detail}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            <div className="border-t border-slate-100 bg-slate-50 px-4 py-2 text-xs text-slate-500">
              PrivGuard v{health.version}
            </div>
          </div>
        )}
      </section>

      <section>
        <h3 className="mb-3 text-sm font-semibold text-slate-900">Scan overview</h3>
        <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
          <MetricCard label="Total scans"    value="—" hint="Cycle 3" />
          <MetricCard label="Files scanned"  value="—" hint="Cycle 3" />
          <MetricCard label="Findings"       value="—" hint="Cycle 5" />
          <MetricCard label="Critical / high" value="—" hint="Cycle 7" />
        </div>
        <p className="mt-3 text-xs text-slate-400">
          Placeholders, not zeroes — these become real once scanning is implemented.
        </p>
      </section>
    </div>
  )
}
