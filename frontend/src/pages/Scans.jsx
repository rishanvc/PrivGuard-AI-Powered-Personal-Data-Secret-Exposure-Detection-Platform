import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'

import StatusPill from '../components/StatusPill'
import { apiGet, ApiError } from '../lib/api'
import { formatDateTime } from '../lib/format'

/** Scan list: the caller's own scans, newest first, paginated (FR-088). */

const TYPE_LABELS = { files: 'Files', folder: 'Folder', repository: 'Repository' }

function NewScanButton() {
  return (
    <Link
      to="/scans/new"
      className="rounded-md bg-slate-900 px-4 py-2 text-sm font-medium text-white hover:bg-slate-800"
    >
      New scan
    </Link>
  )
}

export default function Scans() {
  const [page, setPage] = useState(1)
  const [data, setData] = useState(null)
  const [error, setError] = useState(null)

  useEffect(() => {
    let cancelled = false
    apiGet(`/scans/?page=${page}`)
      .then((result) => {
        if (cancelled) return
        setData(result)
        setError(null)
      })
      .catch((err) => {
        if (!cancelled) setError(err instanceof ApiError ? err.message : 'Unexpected error.')
      })
    return () => { cancelled = true }
  }, [page])

  return (
    <div className="space-y-6">
      <header className="flex items-start justify-between gap-4">
        <div>
          <h2 className="text-2xl font-semibold text-slate-900">Scans</h2>
          <p className="mt-1 text-sm text-slate-500">Your scans, newest first.</p>
        </div>
        <NewScanButton />
      </header>

      {error && (
        <div role="alert" className="rounded-md border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-800">
          {error}
        </div>
      )}

      {!data && !error && <p className="text-sm text-slate-500">Loading scans…</p>}

      {data?.count === 0 && (
        <div className="rounded-lg border border-dashed border-slate-300 bg-white p-10 text-center">
          <p className="text-sm font-medium text-slate-700">No scans yet</p>
          <p className="mt-1 text-sm text-slate-500">Upload files or a folder to build your first inventory.</p>
          <div className="mt-4">
            <NewScanButton />
          </div>
        </div>
      )}

      {data?.count > 0 && (
        <div className="overflow-hidden rounded-lg border border-slate-200 bg-white">
          <table className="w-full text-sm">
            <thead className="bg-slate-50 text-left text-xs font-medium uppercase tracking-wide text-slate-500">
              <tr>
                <th className="px-4 py-2">Name</th>
                <th className="px-4 py-2">Type</th>
                <th className="px-4 py-2 text-right">Files</th>
                <th className="px-4 py-2">Status</th>
                <th className="px-4 py-2">Created</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {data.results.map((scan) => (
                <tr key={scan.id} className="hover:bg-slate-50">
                  <td className="max-w-xs truncate px-4 py-3">
                    <Link to={`/scans/${scan.id}`} className="font-medium text-slate-900 hover:underline" title={scan.name}>
                      {scan.name}
                    </Link>
                  </td>
                  <td className="px-4 py-3 text-slate-600">{TYPE_LABELS[scan.scan_type] ?? scan.scan_type}</td>
                  <td className="px-4 py-3 text-right text-slate-600">{scan.total_files}</td>
                  <td className="px-4 py-3">
                    <StatusPill status={scan.status}>{scan.status_display}</StatusPill>
                  </td>
                  <td className="whitespace-nowrap px-4 py-3 text-slate-500">{formatDateTime(scan.created_at)}</td>
                </tr>
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
                ← Newer
              </button>
              <span className="text-slate-500">Page {page}</span>
              <button
                type="button"
                disabled={!data.next}
                onClick={() => setPage((p) => p + 1)}
                className="text-slate-600 hover:text-slate-900 disabled:opacity-40"
              >
                Older →
              </button>
            </div>
          )}
        </div>
      )}
    </div>
  )
}
