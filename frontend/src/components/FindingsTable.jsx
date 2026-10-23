import { useEffect, useState } from 'react'

import { apiGet, ApiError } from '../lib/api'
import { describeLocation, formatConfidence } from '../lib/findings'

/**
 * One scan's findings, most confident first (FR-078, FR-085).
 *
 * Every value was masked inside the isolated extraction process: raw values
 * never reached the database, let alone the browser. Previews still contain
 * words from the user's files, so - like file names - they are rendered only
 * as React text nodes, which React escapes.
 */

const CONFIDENCE_HINT = 'A fixed score for the rule that matched: a ranking aid, not a probability.'

function FindingRow({ finding }) {
  const more = finding.other_locations.length
  return (
    <tr className="align-top">
      <td className="px-4 py-2.5">
        <span className="font-medium text-slate-900">{finding.subcategory_display}</span>
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
      </td>
      <td className="px-4 py-2.5">
        <span className="block break-words font-mono text-xs text-slate-700">{finding.context_preview}</span>
        <span className="mt-1 block text-xs text-slate-500">{finding.description}</span>
      </td>
    </tr>
  )
}

export default function FindingsTable({ scanId, totalFindings }) {
  const [page, setPage] = useState(1)
  const [data, setData] = useState(null)
  const [error, setError] = useState(null)

  // totalFindings is a dependency on purpose: while a scan runs, findings
  // arrive file by file, and each new total fetches the page again.
  useEffect(() => {
    if (!totalFindings) return undefined
    let cancelled = false
    apiGet(`/scans/${encodeURIComponent(scanId)}/findings/?page=${page}`)
      .then((fresh) => {
        if (cancelled) return
        setData(fresh)
        setError(null)
      })
      .catch((err) => { if (!cancelled) setError(err) })
    return () => { cancelled = true }
  }, [scanId, page, totalFindings])

  if (!totalFindings) return null // the page explains 0 and "not searched" itself
  if (error) {
    return (
      <p className="text-sm text-red-700">
        Findings could not be loaded: {error instanceof ApiError ? error.message : 'unexpected error.'}
      </p>
    )
  }
  if (!data) return <p className="text-sm text-slate-500">Loading findings…</p>

  return (
    <div className="overflow-hidden rounded-lg border border-slate-200 bg-white">
      <table className="w-full table-fixed text-sm">
        <thead className="bg-slate-50 text-left text-xs font-medium uppercase tracking-wide text-slate-500">
          <tr>
            <th className="w-[17%] px-4 py-2">Type</th>
            <th className="w-[22%] px-4 py-2">Value (masked)</th>
            <th className="w-[25%] px-4 py-2">Where</th>
            <th className="px-4 py-2">Context and reason</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-100">
          {data.results.map((finding) => (
            <FindingRow key={finding.id} finding={finding} />
          ))}
        </tbody>
      </table>

      {(data.next || data.previous) && (
        <div className="flex items-center justify-between border-t border-slate-100 bg-slate-50 px-4 py-2 text-sm">
          <button
            type="button"
            disabled={!data.previous}
            onClick={() => setPage((p) => p - 1)}
            className="text-slate-600 hover:text-slate-900 disabled:opacity-40"
          >
            ← Previous
          </button>
          <span className="text-slate-500">Page {page} · {data.count} findings</span>
          <button
            type="button"
            disabled={!data.next}
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
