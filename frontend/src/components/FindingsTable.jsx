import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'

import ReviewBadge from './ReviewBadge'
import SeverityBadge from './SeverityBadge'
import { apiGet, ApiError } from '../lib/api'
import { ORDERINGS, describeLocation, formatConfidence } from '../lib/findings'

/**
 * A page of findings, most serious first by default (FR-078, FR-079, FR-083, FR-085, FR-088).
 * Used on a scan's page (filters = "scan=<id>") and on the Findings page (any filters).
 *
 * Every value was masked inside the isolated extraction process: raw values
 * never reached the database, let alone the browser. Previews and file names
 * still contain text from the user's files, so they are rendered only as React
 * text nodes, which React escapes.
 *
 * Give it a `key` that changes with `filters`, so a new filter starts again at page 1.
 */

const CONFIDENCE_HINT = 'A fixed score for the rule that matched: a ranking aid, not a probability.'

function FindingRow({ finding, showScan }) {
  const more = finding.other_locations.length
  return (
    <tr className="align-top hover:bg-slate-50">
      <td className="px-4 py-2.5">
        <SeverityBadge severity={finding.severity} reason={finding.severity_reason} />
      </td>
      <td className="px-4 py-2.5">
        <Link to={`/findings/${finding.id}`} className="font-medium text-slate-900 hover:underline">
          {finding.subcategory_display}
        </Link>
        <span className="mt-0.5 block text-xs text-slate-500" title={CONFIDENCE_HINT}>
          {finding.detection_method} · {formatConfidence(finding.confidence)}
        </span>
      </td>
      <td className="px-4 py-2.5">
        <span className="break-all font-mono text-xs text-slate-800">{finding.masked_value}</span>
        {finding.occurrences > 1 && (
          <span className="mt-0.5 block text-xs text-slate-500">{finding.occurrences} occurrences</span>
        )}
      </td>
      <td className="px-4 py-2.5">
        <span className="block truncate font-mono text-xs text-slate-800" title={finding.file_path}>
          {finding.file_path}
        </span>
        <span className="mt-0.5 block text-xs text-slate-500">
          {describeLocation(finding.source_location)}
          {more > 0 && ` (+${more} more)`}
        </span>
        {showScan && (
          <Link to={`/scans/${finding.scan_id}`} className="mt-0.5 block truncate text-xs text-slate-500 hover:underline">
            in {finding.scan_name}
          </Link>
        )}
      </td>
      <td className="px-4 py-2.5">
        <ReviewBadge status={finding.review_status} />
      </td>
      <td className="px-4 py-2.5">
        <span className="block wrap-break-word font-mono text-xs text-slate-700">{finding.context_preview}</span>
        <span className="mt-1 block text-xs text-slate-500">{finding.description}</span>
      </td>
    </tr>
  )
}

export default function FindingsTable({ filters = '', refreshKey, showScan = false }) {
  const [page, setPage] = useState(1)
  const [ordering, setOrdering] = useState('severity')
  // Each answer remembers which request it answers. "Loading" is then derived -
  // the latest request is not the one on screen - rather than set inside the effect.
  const [answer, setAnswer] = useState({ request: null, data: null, error: null })

  function changeOrdering(next) {
    setOrdering(next)
    setPage(1) // page 3 of one ordering is not page 3 of another
  }

  const query = [filters, `ordering=${ordering}`, `page=${page}`].filter(Boolean).join('&')
  // refreshKey is part of the request on purpose: while a scan runs its findings
  // arrive file by file, and each new total fetches the page again.
  const request = `${query}#${refreshKey ?? ''}`

  useEffect(() => {
    let cancelled = false
    apiGet(`/findings/?${query}`)
      .then((fresh) => { if (!cancelled) setAnswer({ request, data: fresh, error: null }) })
      .catch((err) => { if (!cancelled) setAnswer((previous) => ({ ...previous, request, error: err })) })
    return () => { cancelled = true }
  }, [query, request])

  const { data, error } = answer
  const loading = answer.request !== request

  if (error) {
    return (
      <p role="alert" className="text-sm text-red-700">
        Findings could not be loaded: {error instanceof ApiError ? error.message : 'unexpected error.'}
      </p>
    )
  }
  if (!data) return <p className="text-sm text-slate-500">Loading findings…</p>

  return (
    // While a new page loads, the previous one stays, dimmed - no flash, no jump.
    <div className={`overflow-hidden rounded-lg border border-slate-200 bg-white transition-opacity ${loading ? 'opacity-60' : ''}`}>
      <div className="flex items-center justify-between gap-2 border-b border-slate-100 bg-slate-50 px-4 py-2 text-sm">
        <span className="text-slate-500">{data.count} finding{data.count === 1 ? '' : 's'}</span>
        <span className="flex items-center gap-2">
          <label htmlFor="finding-ordering" className="text-slate-500">Sort by</label>
          <select
            id="finding-ordering"
            value={ordering}
            onChange={(event) => changeOrdering(event.target.value)}
            className="rounded-md border border-slate-300 bg-white px-2 py-1 text-sm text-slate-700"
          >
            {Object.entries(ORDERINGS).map(([value, label]) => (
              <option key={value} value={value}>{label}</option>
            ))}
          </select>
        </span>
      </div>

      {data.count === 0 ? (
        <p className="px-4 py-10 text-center text-sm text-slate-500">No findings match these filters.</p>
      ) : (
        <table className="w-full table-fixed text-sm">
          <thead className="bg-slate-50 text-left text-xs font-medium uppercase tracking-wide text-slate-500">
            <tr>
              <th className="w-[11%] px-4 py-2">Severity</th>
              <th className="w-[15%] px-4 py-2">Type</th>
              <th className="w-[17%] px-4 py-2">Value (masked)</th>
              <th className="w-[20%] px-4 py-2">Where</th>
              <th className="w-[11%] px-4 py-2">Review</th>
              <th className="px-4 py-2">Context</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {data.results.map((finding) => (
              <FindingRow key={finding.id} finding={finding} showScan={showScan} />
            ))}
          </tbody>
        </table>
      )}

      {(data.next || data.previous) && (
        <div className="flex items-center justify-between border-t border-slate-100 bg-slate-50 px-4 py-2 text-sm">
          <button
            type="button"
            disabled={!data.previous || loading}
            onClick={() => setPage((p) => p - 1)}
            className="text-slate-600 hover:text-slate-900 disabled:opacity-40"
          >
            ← Previous
          </button>
          <span className="text-slate-500">Page {page}</span>
          <button
            type="button"
            disabled={!data.next || loading}
            onClick={() => setPage((p) => p + 1)}
            className="text-slate-600 hover:text-slate-900 disabled:opacity-40"
          >
            Next →
          </button>
        </div>
      )}
    </div>
  )
}
