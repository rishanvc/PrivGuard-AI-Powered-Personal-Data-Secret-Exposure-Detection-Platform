import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'

import ReviewBadge from '../components/ReviewBadge'
import RiskMeter from '../components/RiskMeter'
import SeverityBadge from '../components/SeverityBadge'
import { apiGet, apiPatch, ApiError } from '../lib/api'
import { REVIEW_STATUSES, describeLocation, formatConfidence } from '../lib/findings'
import { formatDateTime } from '../lib/format'

/**
 * Everything about one finding (FR-084), and the place to review it (FR-086, UC-03).
 *
 * The value and the preview were masked inside the isolated extraction process;
 * nothing raw exists to show. Text from the user's files (paths, previews) is
 * rendered only as React text nodes, which React escapes.
 */

// The detection engine keeps at most this many distinct locations per finding
// (FindingCollector's max_locations). Repeats on one line are one location.
const MAX_LOCATIONS = 20

function Field({ label, children }) {
  return (
    <div>
      <dt className="text-xs font-medium uppercase tracking-wide text-slate-500">{label}</dt>
      <dd className="mt-1 text-sm text-slate-800">{children}</dd>
    </div>
  )
}

function ReviewButtons({ current, busy, onReview }) {
  return (
    <div className="flex flex-wrap gap-2" role="group" aria-label="Review status">
      {Object.entries(REVIEW_STATUSES).map(([status, meta]) => {
        const active = status === current
        return (
          <button
            key={status}
            type="button"
            aria-pressed={active}
            title={meta.hint}
            disabled={busy !== null}
            onClick={() => !active && onReview(status)}
            className={`rounded-md border px-3 py-1.5 text-sm font-medium disabled:opacity-60 ${
              active
                ? 'border-slate-900 bg-slate-900 text-white'
                : 'border-slate-300 bg-white text-slate-700 hover:bg-slate-50'
            }`}
          >
            {busy === status ? 'Saving…' : meta.label}
          </button>
        )
      })}
    </div>
  )
}

export default function FindingDetail() {
  const { findingId } = useParams()
  const id = encodeURIComponent(findingId)
  const [finding, setFinding] = useState(null)
  const [loadError, setLoadError] = useState(null)
  const [busy, setBusy] = useState(null)
  const [reviewError, setReviewError] = useState(null)

  useEffect(() => {
    let cancelled = false
    apiGet(`/findings/${id}/`)
      .then((data) => { if (!cancelled) setFinding(data) })
      .catch((err) => { if (!cancelled) setLoadError(err) })
    return () => { cancelled = true }
  }, [id])

  async function review(status) {
    setBusy(status)
    setReviewError(null)
    try {
      setFinding(await apiPatch(`/findings/${id}/`, { review_status: status }))
    } catch (err) {
      setReviewError(err instanceof ApiError ? err.message : 'The review could not be saved.')
    } finally {
      setBusy(null)
    }
  }

  if (loadError) {
    // 404 covers "doesn't exist" and "not yours" alike - deliberately the same.
    return (
      <div className="space-y-4">
        <Link to="/findings" className="text-sm text-slate-500 hover:text-slate-900">← Findings</Link>
        <p role="alert" className="rounded-md border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-800">
          {loadError.status === 404 ? 'Finding not found. Its scan may have been deleted.' : loadError.message}
        </p>
      </div>
    )
  }
  if (!finding) return <p className="text-sm text-slate-500">Loading finding…</p>

  const locations = [finding.source_location, ...finding.other_locations]

  return (
    <div className="space-y-6">
      <header>
        <Link to="/findings" className="text-sm text-slate-500 hover:text-slate-900">← Findings</Link>
        <div className="mt-2 flex flex-wrap items-center gap-3">
          <SeverityBadge severity={finding.severity} reason={finding.severity_reason} />
          <h2 className="text-2xl font-semibold text-slate-900">{finding.subcategory_display}</h2>
          <ReviewBadge status={finding.review_status} />
        </div>
        <p className="mt-2 break-all font-mono text-lg text-slate-900">{finding.masked_value}</p>
        <p className="mt-1 text-sm text-slate-500">
          in <span className="font-mono text-slate-700">{finding.file_path}</span>
          {' · '}
          <Link to={`/scans/${finding.scan_id}`} className="hover:underline">{finding.scan_name}</Link>
        </p>
      </header>

      <section className="space-y-3 rounded-lg border border-slate-200 bg-white p-5">
        <h3 className="text-sm font-semibold text-slate-900">Your review</h3>
        <ReviewButtons current={finding.review_status} busy={busy} onReview={review} />
        <p className="text-xs text-slate-500">
          {REVIEW_STATUSES[finding.review_status]?.hint}
          {finding.reviewed_at && ` Last changed by ${finding.reviewed_by} on ${formatDateTime(finding.reviewed_at)}.`}
        </p>
        {reviewError && <p role="alert" className="text-sm text-red-700">{reviewError}</p>}
      </section>

      <section className="rounded-lg border border-emerald-200 bg-emerald-50 p-5">
        <h3 className="text-sm font-semibold text-emerald-900">What to do</h3>
        <p className="mt-1 text-sm text-emerald-900">{finding.remediation || 'No advice recorded: this finding was found before PrivGuard gave remediation advice.'}</p>
      </section>

      <section className="grid gap-5 rounded-lg border border-slate-200 bg-white p-5 sm:grid-cols-2">
        <Field label="Why it was flagged">{finding.description}</Field>
        <Field label="Severity">{finding.severity_reason || 'Not assessed: found before PrivGuard assessed severity.'}</Field>
        <Field label="Risk">
          <RiskMeter score={finding.risk_score} band={finding.risk_band} />
        </Field>
        <Field label="Detection">
          {finding.detection_method} · confidence {formatConfidence(finding.confidence)}
          <span className="mt-0.5 block text-xs text-slate-500">A fixed score for the rule that matched, not a probability.</span>
        </Field>
        <Field label="Category">{finding.category_display}</Field>
        <Field label="File type">{finding.file_type || '—'}</Field>
      </section>

      <section className="space-y-3 rounded-lg border border-slate-200 bg-white p-5">
        <h3 className="text-sm font-semibold text-slate-900">Context (masked)</h3>
        <p className="wrap-break-word rounded-md bg-slate-50 p-3 font-mono text-xs text-slate-700">{finding.context_preview}</p>
        <h3 className="pt-2 text-sm font-semibold text-slate-900">
          Where ({finding.occurrences} occurrence{finding.occurrences === 1 ? '' : 's'})
        </h3>
        <ul className="list-inside list-disc text-sm text-slate-700">
          {locations.map((location) => (
            <li key={JSON.stringify(location)}>{describeLocation(location) || 'the file'}</li>
          ))}
        </ul>
        {locations.length >= MAX_LOCATIONS && (
          <p className="text-xs text-slate-500">
            Only the first {MAX_LOCATIONS} distinct locations in a file are kept.
          </p>
        )}
      </section>

      <section className="space-y-3 rounded-lg border border-slate-200 bg-white p-5">
        <h3 className="text-sm font-semibold text-slate-900">Review history</h3>
        {finding.history.length === 0 ? (
          <p className="text-sm text-slate-500">Not reviewed yet.</p>
        ) : (
          <ol className="space-y-1 text-sm text-slate-700">
            {finding.history.map((entry, index) => (
              <li key={`${entry.at}-${index}`}>
                {formatDateTime(entry.at)}: <span className="font-medium">{entry.by}</span> changed{' '}
                {REVIEW_STATUSES[entry.from_status]?.label ?? entry.from_status} →{' '}
                {REVIEW_STATUSES[entry.to_status]?.label ?? entry.to_status}
              </li>
            ))}
          </ol>
        )}
      </section>
    </div>
  )
}
