import { useEffect, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'

import StatusPill from '../components/StatusPill'
import { apiDelete, apiGet, apiPost, ApiError } from '../lib/api'
import { formatBytes, formatDateTime } from '../lib/format'

/**
 * One scan: its status, what happened to each file, and the actions its
 * current state allows (FR-015, FR-082, FR-089, FR-090).
 *
 * File names, paths and reasons come from uploads, so they are
 * attacker-controlled text. They are only ever rendered as React text nodes,
 * which React escapes - never via dangerouslySetInnerHTML.
 */

const COUNT_CARDS = [
  { key: 'pending', label: 'Accepted', hint: 'Waiting to be processed' },
  { key: 'rejected', label: 'Rejected', hint: 'Failed validation' },
  { key: 'unsupported', label: 'Unsupported', hint: 'Cannot be processed yet' },
  { key: 'skipped', label: 'Skipped', hint: 'Empty or duplicate' },
]

function message(err) {
  return err instanceof ApiError ? err.message : 'Unexpected error.'
}

export default function ScanDetail() {
  const { scanId } = useParams()
  const navigate = useNavigate()
  const id = encodeURIComponent(scanId)

  const [scan, setScan] = useState(null)
  const [loadError, setLoadError] = useState(null)
  const [files, setFiles] = useState(null)
  const [filePage, setFilePage] = useState(1)
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
    const stored = scan.file_counts.pending
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
        <div role="alert" className="rounded-md border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-800">
          {loadError.status === 404 ? 'Scan not found. It may have been deleted.' : message(loadError)}
        </div>
      </div>
    )
  }

  if (!scan) return <p className="text-sm text-slate-500">Loading scan…</p>

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

      {actionError && (
        <div role="alert" className="rounded-md border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-800">
          {actionError}
        </div>
      )}

      {scan.status === 'queued' && (
        <div className="rounded-md border border-sky-200 bg-sky-50 px-4 py-3 text-sm text-sky-900">
          Queued. Text extraction and detection are not built yet (Cycles 4–5), so this scan will stay queued
          until then. No findings are produced at this stage.
        </div>
      )}

      {scan.status === 'draft' && !scan.actions.start && (
        <div className="rounded-md border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-900">
          None of these files can be processed, so there is nothing to start. See the reasons below.
        </div>
      )}

      <section className="grid grid-cols-2 gap-4 sm:grid-cols-4">
        {COUNT_CARDS.map(({ key, label, hint }) => (
          <div key={key} className="rounded-lg border border-slate-200 bg-white p-4">
            <p className="text-xs font-medium uppercase tracking-wide text-slate-500">{label}</p>
            <p className="mt-1 text-2xl font-semibold text-slate-900">{scan.file_counts[key]}</p>
            <p className="mt-1 text-xs text-slate-400">{hint}</p>
          </div>
        ))}
      </section>

      <section>
        <h3 className="mb-3 text-sm font-semibold text-slate-900">File inventory</h3>
        {!files ? (
          <p className="text-sm text-slate-500">Loading files…</p>
        ) : (
          <div className="overflow-hidden rounded-lg border border-slate-200 bg-white">
            <table className="w-full table-fixed text-sm">
              <thead className="bg-slate-50 text-left text-xs font-medium uppercase tracking-wide text-slate-500">
                <tr>
                  <th className="w-[38%] px-4 py-2">File</th>
                  <th className="w-[10%] px-4 py-2">Type</th>
                  <th className="w-[10%] px-4 py-2 text-right">Size</th>
                  <th className="w-[13%] px-4 py-2">Status</th>
                  <th className="px-4 py-2">Reason</th>
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
                      <StatusPill status={file.status}>{file.status_display}</StatusPill>
                    </td>
                    <td className="px-4 py-2.5 text-slate-600">
                      {file.reason || '—'}
                      {file.duplicate_of_path && (
                        <span className="mt-0.5 block truncate font-mono text-xs text-slate-400" title={file.duplicate_of_path}>
                          same as {file.duplicate_of_path}
                        </span>
                      )}
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
