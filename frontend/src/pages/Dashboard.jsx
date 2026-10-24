import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'

import RiskMeter from '../components/RiskMeter'
import StatusPill from '../components/StatusPill'
import { apiGet, ApiError, BASE_URL } from '../lib/api'
import { NOT_ASSESSED, OPEN_STATUSES, REVIEW_STATUSES, SEVERITIES } from '../lib/findings'
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
  worker: 'Scan worker',
  ocr: 'OCR engine',
  ai: 'Local AI',
}

function MetricCard({ label, value, hint, to }) {
  const body = (
    <>
      <p className="text-xs font-medium uppercase tracking-wide text-slate-500">{label}</p>
      <p className="mt-1 text-2xl font-semibold text-slate-900">{value ?? '—'}</p>
      {hint && <p className="mt-1 text-xs text-slate-400">{hint}</p>}
    </>
  )
  // A number with nothing behind it (still "—") is not a link.
  return to && value ? (
    <Link to={to} className="block rounded-lg border border-slate-200 bg-white p-4 hover:border-slate-400">{body}</Link>
  ) : (
    <div className="rounded-lg border border-slate-200 bg-white p-4">{body}</div>
  )
}

/**
 * Open findings per severity (FR-081): one bar per level, value at the tip,
 * label beside it - colour is never the only way to read a bar. Each row
 * opens the Findings page filtered to that level.
 */
function SeverityBars({ counts }) {
  const levels = [...Object.keys(SEVERITIES), ...(counts.not_assessed ? ['not_assessed'] : [])]
  const max = Math.max(1, ...levels.map((level) => counts[level]))
  return (
    <ul className="space-y-1">
      {levels.map((level) => {
        const meta = SEVERITIES[level] ?? NOT_ASSESSED
        const n = counts[level]
        return (
          <li key={level}>
            <Link
              to={`/findings?severity=${level}&status=${OPEN_STATUSES}`}
              title={`${meta.label}: ${n} open finding${n === 1 ? '' : 's'}. Open the list.`}
              className="group grid grid-cols-[7rem_1fr] items-center gap-3 rounded-md px-2 py-1 hover:bg-slate-50"
            >
              <span className="text-sm text-slate-700">{meta.label}</span>
              <span className="flex items-center border-l border-slate-300">
                <span
                  className={`h-4 rounded-r ${meta.mark} group-hover:opacity-80`}
                  style={{ width: `calc((100% - 3rem) * ${n / max})` }}
                />
                <span className="ml-2 text-sm tabular-nums text-slate-800">{n}</span>
              </span>
            </Link>
          </li>
        )
      })}
    </ul>
  )
}

/** How many findings a person has looked at (FR-086): a meter, blue on a pale-blue track. */
function ReviewProgress({ counts }) {
  const total = Object.values(counts).reduce((sum, n) => sum + n, 0)
  const reviewed = total - counts.new
  return (
    <div className="space-y-2">
      <div
        role="meter"
        aria-valuemin={0}
        aria-valuemax={total}
        aria-valuenow={reviewed}
        aria-label={`${reviewed} of ${total} findings reviewed`}
        className="h-3 overflow-hidden rounded-full bg-[#cde2fb]"
      >
        <div className="h-full rounded-full bg-[#2a78d6]" style={{ width: `${total ? (reviewed / total) * 100 : 0}%` }} />
      </div>
      <p className="text-sm text-slate-700">
        <span className="font-semibold text-slate-900">{reviewed}</span> of {total} reviewed
        {counts.new > 0 && (
          <> · <Link to="/findings?status=new" className="text-slate-500 underline hover:text-slate-900">{counts.new} still new</Link></>
        )}
      </p>
      <p className="text-xs text-slate-500">
        {Object.entries(REVIEW_STATUSES).filter(([status]) => status !== 'new' && counts[status])
          .map(([status, meta]) => `${counts[status]} ${meta.label.toLowerCase()}`).join(' · ')}
      </p>
    </div>
  )
}

const CATEGORY_TILES = [
  ['personal', 'Personal data'],
  ['secret', 'Secrets'],
  ['financial', 'Financial data'],
]

function FindingsOverview({ summary }) {
  if (summary.total_findings === null) {
    return (
      <p className="rounded-lg border border-dashed border-slate-300 bg-white p-6 text-center text-sm text-slate-500">
        No scan has been searched yet, so there is nothing to chart.
      </p>
    )
  }
  if (summary.total_findings === 0) {
    return (
      <p className="rounded-lg border border-dashed border-slate-300 bg-white p-6 text-center text-sm text-slate-500">
        No findings in the files that could be read. That is not proof the files are safe - only that no rule matched.
      </p>
    )
  }
  return (
    <div className="space-y-4">
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
        {CATEGORY_TILES.map(([category, label]) => (
          <MetricCard
            key={category}
            label={label}
            value={summary.category_counts[category]}
            hint="Open findings"
            to={`/findings?category=${category}&status=${OPEN_STATUSES}`}
          />
        ))}
      </div>
      <div className="grid gap-4 lg:grid-cols-2">
        <div className="rounded-lg border border-slate-200 bg-white p-4">
          <h4 className="text-sm font-semibold text-slate-900">Open findings by severity</h4>
          <p className="mb-3 text-xs text-slate-500">Not counting those reviewed as false positive or resolved.</p>
          <SeverityBars counts={summary.severity_counts} />
        </div>
        <div className="space-y-4">
          <div className="rounded-lg border border-slate-200 bg-white p-4">
            <h4 className="mb-3 text-sm font-semibold text-slate-900">Review progress</h4>
            <ReviewProgress counts={summary.review_counts} />
          </div>
          <div className="rounded-lg border border-slate-200 bg-white p-4">
            <h4 className="mb-3 text-sm font-semibold text-slate-900">Riskiest scans</h4>
            <ul className="divide-y divide-slate-100">
              {summary.riskiest_scans.map((scan) => (
                <li key={scan.id} className="flex items-center justify-between gap-4 py-2">
                  <Link to={`/scans/${scan.id}`} className="min-w-0 truncate text-sm font-medium text-slate-900 hover:underline">
                    {scan.name}
                  </Link>
                  <RiskMeter score={scan.risk_score} band={scan.risk_band} />
                </li>
              ))}
            </ul>
          </div>
        </div>
      </div>
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
  const workerDown = health.data?.components?.worker?.status === 'error'

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

      {workerDown && (
        <div role="alert" className="rounded-md border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-900">
          <strong>The scan worker isn&apos;t running</strong>, so started scans will wait in the queue. Start it in a
          terminal: <code className="font-mono">python manage.py run_worker</code>
        </div>
      )}

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
              label="Files processed"
              value={s?.files_processed}
              hint={s ? `of ${s.files_accepted} accepted` : null}
            />
            <MetricCard
              label="Findings"
              value={s?.total_findings}
              hint={s && s.total_findings === null ? 'No scan searched yet' : 'In scans that were searched'}
            />
            <MetricCard
              label="Critical / high"
              value={s?.critical_high_findings}
              hint={s && s.critical_high_findings === null ? 'No scan searched yet' : 'Open - fix these first'}
              to={`/findings?severity=critical,high&status=${OPEN_STATUSES}`}
            />
          </div>
        )}
      </section>

      {s && (
        <section>
          <h3 className="mb-3 text-sm font-semibold text-slate-900">Findings overview</h3>
          <FindingsOverview summary={s} />
        </section>
      )}

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
