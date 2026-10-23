import { useEffect, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'

import FindingsTable from '../components/FindingsTable'
import StatusPill from '../components/StatusPill'
import { apiDelete, apiGet, apiPost, ApiError } from '../lib/api'
import { EXTRACTION_LABELS, extractionSummary } from '../lib/extraction'
import { formatBytes, formatDateTime } from '../lib/format'

/**
 * One scan: its status, live progress, what happened to each file, and the
 * actions its state allows (FR-015, FR-028, FR-082, FR-089, NFR-002).
 *
 * File names, paths, reasons and notes are rendered only as React text nodes,
 * which React escapes - never via dangerouslySetInnerHTML. Names come from
 * uploads, so they are attacker-controlled.
 */

const ACTIVE = new Set(['queued', 'processing'])
const FINISHED = new Set(['completed', 'partially_completed', 'failed'])
const PROCESSED = new Set(['completed', 'failed'])
const POLL_MS = 2000

function message(err) {
  return err instanceof ApiError ? err.message : 'Unexpected error.'
}

function Card({ label, value, hint }) {
  return (
    <div className="rounded-lg border border-slate-200 bg-white p-4">
      <p className="text-xs font-medium uppercase tracking-wide text-slate-500">{label}</p>
      <p className="mt-1 text-2xl font-semibold text-slate-900">{value}</p>
      <p className="mt-1 text-xs text-slate-400">{hint}</p>
    </div>
  )
}

function Banner({ tone, children }) {
  const tones = {
    info: 'border-sky-200 bg-sky-50 text-sky-900',
    warn: 'border-amber-200 bg-amber-50 text-amber-900',
    error: 'border-red-200 bg-red-50 text-red-800',
    neutral: 'border-slate-200 bg-slate-50 text-slate-700',
  }
  return <div className={`rounded-md border px-4 py-3 text-sm ${tones[tone]}`}>{children}</div>
}

function FileStatus({ file }) {
  // Once the worker is done with a file, what matters is how much of it was READ.
  if (PROCESSED.has(file.status) && file.extraction_status !== 'not_started') {
    return (
      <StatusPill status={file.extraction_status}>
        {EXTRACTION_LABELS[file.extraction_status] ?? file.extraction_status_display}
      </StatusPill>
    )
  }
  return <StatusPill status={file.status}>{file.status_display}</StatusPill>
}

function FileDetails({ file }) {
  if (file.reason) {
    // Decided at intake: rejected, unsupported, empty or duplicate.
    return (
      <>
        {file.reason}
        {file.duplicate_of_path && (
          <span className="mt-0.5 block truncate font-mono text-xs text-slate-400" title={file.duplicate_of_path}>
            same as {file.duplicate_of_path}
          </span>
        )}
      </>
    )
  }
  if (file.status === 'processing') return <span className="text-indigo-700">Reading…</span>
  if (!PROCESSED.has(file.status)) return '—'

  const summary = extractionSummary(file.extraction_stats)
  const found = file.detection_stats?.findings
  return (
    <>
      {summary && <span className="block text-xs text-slate-500">{summary}</span>}
      {found != null && (
        <span className="mt-0.5 block text-xs text-slate-700">
          {found === 0 ? 'Searched: nothing found' : `${found} finding${found === 1 ? '' : 's'}`}
        </span>
      )}
      {file.detection_stats?.truncated && (
        <span className="mt-0.5 block text-xs text-amber-800">
          Too many findings: only the first {found.toLocaleString()} distinct values were kept.
        </span>
      )}
      {file.extraction_detail && (
        <span className={`mt-0.5 block ${file.extraction_status === 'failed' ? 'text-red-700' : 'text-amber-800'}`}>
          {file.extraction_detail}
        </span>
      )}
      {file.extraction_notes?.map((note) => (
        <span key={note} className="mt-0.5 block text-xs text-slate-500">{note}</span>
      ))}
    </>
  )
}

export default function ScanDetail() {
  const { scanId } = useParams()
  const navigate = useNavigate()
  const id = encodeURIComponent(scanId)

  const [scan, setScan] = useState(null)
  const [loadError, setLoadError] = useState(null)
  const [files, setFiles] = useState(null)
  const [filePage, setFilePage] = useState(1)
  const [workerRunning, setWorkerRunning] = useState(null) // null = unknown
  const [busy, setBusy] = useState(null) // 'start' | 'cancel' | 'delete' | null
  const [actionError, setActionError] = useState(null)

  useEffect(() => {
    let cancelled = false
    apiGet(`/scans/${id}/`)
      .then((data) => { if (!cancelled) setScan(data) })
      .catch((err) => { if (!cancelled) setLoadError(err) })
    return () => { cancelled = true }
  }, [id])

  useEffect(() => {
    let cancelled = false
    apiGet(`/scans/${id}/files/?page=${filePage}`)
      .then((data) => { if (!cancelled) setFiles(data) })
      .catch((err) => { if (!cancelled) setLoadError(err) })
    return () => { cancelled = true }
  }, [id, filePage])

  // Live progress (NFR-002). A chain of timeouts, not an interval: after each
  // attempt the tick advances, which schedules the next poll - but only while
  // the scan is still queued or processing. Polling therefore stops by itself
  // when the scan finishes, and the cleanup cancels the pending timer when you
  // leave the page.
  const status = scan?.status
  const [tick, setTick] = useState(0)
  useEffect(() => {
    if (!ACTIVE.has(status)) return undefined
    let cancelled = false
    const timer = setTimeout(async () => {
      try {
        const [fresh, freshFiles, health] = await Promise.all([
          apiGet(`/scans/${id}/`),
          apiGet(`/scans/${id}/files/?page=${filePage}`),
          status === 'queued' ? apiGet('/health/') : Promise.resolve(null),
        ])
        if (cancelled) return // the page was left while the request was in flight
        setScan(fresh)
        setFiles(freshFiles)
        if (health) setWorkerRunning(health.components?.worker?.status === 'ok')
      } catch {
        // A missed poll is not worth an error message; the next tick retries.
      } finally {
        if (!cancelled) setTick((t) => t + 1)
      }
    }, POLL_MS)
    return () => {
      cancelled = true
      clearTimeout(timer)
    }
  }, [status, tick, id, filePage])

  async function runAction(action) {
    setBusy(action)
    setActionError(null)
    try {
      setScan(await apiPost(`/scans/${id}/${action}/`))
    } catch (err) {
      setActionError(message(err))
    } finally {
      setBusy(null)
    }
  }

  async function handleDelete() {
    const stored = scan.progress.total
    const confirmed = window.confirm(
      `Delete "${scan.name}"?\n\nThis permanently removes the scan and its ${stored} stored ` +
        `file${stored === 1 ? '' : 's'} from disk. It cannot be undone.`,
    )
    if (!confirmed) return
    setBusy('delete')
    setActionError(null)
    try {
      await apiDelete(`/scans/${id}/`)
      navigate('/scans', { replace: true })
    } catch (err) {
      setActionError(message(err))
      setBusy(null)
    }
  }

  if (loadError) {
    // 404 covers "doesn't exist" and "not yours" alike - deliberately the same.
    return (
      <div className="space-y-4">
        <Link to="/scans" className="text-sm text-slate-500 hover:text-slate-900">← Scans</Link>
        <Banner tone="error">
          {loadError.status === 404 ? 'Scan not found. It may have been deleted.' : message(loadError)}
        </Banner>
      </div>
    )
  }

  if (!scan) return <p className="text-sm text-slate-500">Loading scan…</p>

  const { done, total } = scan.progress
  const percent = total ? Math.round((done / total) * 100) : 0
  const reading = scan.extraction_counts
  const notRead = (reading.failed ?? 0) + (reading.not_supported ?? 0)
  const anyProcessed = done > 0

  return (
    <div className="space-y-6">
      <header>
        <Link to="/scans" className="text-sm text-slate-500 hover:text-slate-900">← Scans</Link>
        <div className="mt-2 flex flex-wrap items-start justify-between gap-4">
          <div className="min-w-0">
            <div className="flex items-center gap-3">
              <h2 className="truncate text-2xl font-semibold text-slate-900" title={scan.name}>{scan.name}</h2>
              <StatusPill status={scan.status}>{scan.status_display}</StatusPill>
            </div>
            <p className="mt-1 text-sm text-slate-500">
              {scan.total_files} file{scan.total_files === 1 ? '' : 's'} · created {formatDateTime(scan.created_at)}
              {scan.completed_at && ` · finished ${formatDateTime(scan.completed_at)}`}
            </p>
          </div>

          <div className="flex gap-2">
            {scan.actions.start && (
              <button
                type="button"
                disabled={busy !== null}
                onClick={() => runAction('start')}
                className="rounded-md bg-slate-900 px-4 py-2 text-sm font-medium text-white hover:bg-slate-800 disabled:opacity-50"
              >
                {busy === 'start' ? 'Starting…' : 'Start scan'}
              </button>
            )}
            {scan.actions.cancel && (
              <button
                type="button"
                disabled={busy !== null}
                onClick={() => runAction('cancel')}
                className="rounded-md border border-slate-300 px-4 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50 disabled:opacity-50"
              >
                {busy === 'cancel' ? 'Cancelling…' : 'Cancel scan'}
              </button>
            )}
            {scan.actions.delete && (
              <button
                type="button"
                disabled={busy !== null}
                onClick={handleDelete}
                className="rounded-md border border-red-300 px-4 py-2 text-sm font-medium text-red-700 hover:bg-red-50 disabled:opacity-50"
              >
                {busy === 'delete' ? 'Deleting…' : 'Delete'}
              </button>
            )}
          </div>
        </div>
      </header>

      {actionError && <Banner tone="error">{actionError}</Banner>}

      {scan.status === 'queued' && workerRunning === false && (
        <Banner tone="warn">
          <strong>No scan worker is running</strong>, so this scan will wait. Start one in a terminal:{' '}
          <code className="font-mono">python manage.py run_worker</code>
        </Banner>
      )}
      {scan.status === 'queued' && workerRunning !== false && (
        <Banner tone="info">Queued. The worker will pick this scan up shortly.</Banner>
      )}

      {ACTIVE.has(scan.status) && total > 0 && (
        <div className="rounded-lg border border-slate-200 bg-white p-5">
          <div className="flex items-center justify-between text-sm">
            <span className="font-medium text-slate-900">
              {scan.status === 'processing' ? 'Reading files…' : 'Waiting to start…'}
            </span>
            <span className="text-slate-500">{done} of {total}</span>
          </div>
          <div className="mt-3 h-2 overflow-hidden rounded-full bg-slate-100">
            <div className="h-full bg-indigo-600 transition-all duration-500" style={{ width: `${percent}%` }} />
          </div>
        </div>
      )}

      {FINISHED.has(scan.status) && scan.total_findings === null && (
        <Banner tone="neutral">
          No file could be read, so <strong>nothing was searched</strong>. Findings show “—”, not 0: zero
          would claim the files were checked and found clean.
        </Banner>
      )}
      {FINISHED.has(scan.status) && scan.error_summary && (
        <Banner tone={scan.status === 'failed' ? 'error' : 'warn'}>{scan.error_summary}</Banner>
      )}
      {scan.status === 'cancelled' && (
        <Banner tone="neutral">Cancelled. Files that had not been read yet were left unprocessed.</Banner>
      )}

      {scan.status === 'draft' && !scan.actions.start && (
        <Banner tone="warn">None of these files can be processed, so there is nothing to start. See the reasons below.</Banner>
      )}

      <section className="space-y-3">
        <h3 className="text-sm font-semibold text-slate-900">Intake</h3>
        <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
          <Card label="Accepted" value={total} hint="Passed validation" />
          <Card label="Rejected" value={scan.file_counts.rejected} hint="Failed validation" />
          <Card label="Unsupported" value={scan.file_counts.unsupported} hint="Cannot be processed yet" />
          <Card label="Skipped" value={scan.file_counts.skipped} hint="Empty or duplicate" />
        </div>
      </section>

      {anyProcessed && (
        <section className="space-y-3">
          <h3 className="text-sm font-semibold text-slate-900">Extraction</h3>
          <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
            <Card label="Fully read" value={reading.succeeded ?? 0} hint="All text extracted" />
            <Card label="Partly read" value={reading.partial ?? 0} hint="Some content unreadable" />
            <Card label="Not read" value={notRead} hint="Failed or not supported" />
            <Card
              label="Findings"
              value={scan.total_findings ?? '—'}
              hint={scan.total_findings === null ? 'Not searched yet' : 'Personal data, masked'}
            />
          </div>
        </section>
      )}

      {scan.total_findings !== null && (
        <section className="space-y-3">
          <div className="flex flex-wrap items-baseline justify-between gap-2">
            <h3 className="text-sm font-semibold text-slate-900">Findings</h3>
            <p className="text-xs text-slate-500">
              Values are masked. Only the masked form was ever stored.
            </p>
          </div>
          {scan.finding_counts.length > 0 && (
            <div className="flex flex-wrap gap-2">
              {scan.finding_counts.map((row) => (
                <span key={row.type} className="rounded-full bg-slate-100 px-3 py-1 text-xs text-slate-700">
                  {row.label} <span className="font-semibold text-slate-900">{row.count}</span>
                </span>
              ))}
            </div>
          )}
          {scan.total_findings === 0 ? (
            <Banner tone="neutral">
              No personal data was found in the files that could be read.
              {ACTIVE.has(scan.status) && ' The scan is still running.'}
            </Banner>
          ) : (
            <FindingsTable scanId={scanId} totalFindings={scan.total_findings} />
          )}
        </section>
      )}

      <section>
        <h3 className="mb-3 text-sm font-semibold text-slate-900">Files</h3>
        {!files ? (
          <p className="text-sm text-slate-500">Loading files…</p>
        ) : (
          <div className="overflow-hidden rounded-lg border border-slate-200 bg-white">
            <table className="w-full table-fixed text-sm">
              <thead className="bg-slate-50 text-left text-xs font-medium uppercase tracking-wide text-slate-500">
                <tr>
                  <th className="w-[34%] px-4 py-2">File</th>
                  <th className="w-[9%] px-4 py-2">Type</th>
                  <th className="w-[10%] px-4 py-2 text-right">Size</th>
                  <th className="w-[14%] px-4 py-2">Status</th>
                  <th className="px-4 py-2">Details</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {files.results.map((file) => (
                  <tr key={file.id} className="align-top">
                    <td className="truncate px-4 py-2.5 font-mono text-xs text-slate-800" title={file.relative_path}>
                      {file.relative_path}
                    </td>
                    <td className="px-4 py-2.5 text-slate-600">{file.file_type || '—'}</td>
                    <td className="whitespace-nowrap px-4 py-2.5 text-right text-slate-600">{formatBytes(file.file_size)}</td>
                    <td className="px-4 py-2.5">
                      <FileStatus file={file} />
                    </td>
                    <td className="px-4 py-2.5 text-slate-600">
                      <FileDetails file={file} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>

            {(files.next || files.previous) && (
              <div className="flex items-center justify-between border-t border-slate-100 bg-slate-50 px-4 py-2 text-sm">
                <button
                  type="button"
                  disabled={!files.previous}
                  onClick={() => setFilePage((p) => p - 1)}
                  className="text-slate-600 hover:text-slate-900 disabled:opacity-40"
                >
                  ← Previous
                </button>
                <span className="text-slate-500">Page {filePage} · {files.count} files</span>
                <button
                  type="button"
                  disabled={!files.next}
                  onClick={() => setFilePage((p) => p + 1)}
                  className="text-slate-600 hover:text-slate-900 disabled:opacity-40"
                >
                  Next →
                </button>
              </div>
            )}
          </div>
        )}
      </section>
    </div>
  )
}
