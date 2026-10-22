import { useEffect, useMemo, useRef, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'

import { apiGet, apiUpload, ApiError, BASE_URL } from '../lib/api'
import { formatBytes } from '../lib/format'

/**
 * New Scan screen (SRS 5.1.3): pick files or a folder, check them against the
 * server's limits, upload with progress.
 *
 * The checks here are for the USER's benefit - so nobody waits through a
 * 200 MB upload only to be refused. They are not security: the server
 * re-checks size, count, type and paths on every upload.
 */

const MB = 1024 * 1024
const PREVIEW_ROWS = 100

// Folders that usually hold thousands of generated files. Exclusion rules
// arrive in Cycle 8; until then we only warn.
const HEAVY_FOLDERS = ['node_modules', '.git', '.venv', 'venv', '__pycache__', 'dist', 'build']

// Lets the browser pick a whole folder. Spread as props because these are
// non-standard attributes React doesn't know by name.
const FOLDER_PICKER = { webkitdirectory: '', directory: '' }

function summarise(selected, limits, mode) {
  const totalBytes = selected.reduce((sum, item) => sum + item.file.size, 0)
  const oversized = limits ? selected.filter((item) => item.file.size > limits.max_file_mb * MB) : []

  const heavy = {}
  if (mode === 'folder') {
    for (const item of selected) {
      const folders = item.path.split('/').slice(0, -1)
      const hit = folders.find((part) => HEAVY_FOLDERS.includes(part))
      if (hit) {
        heavy[hit] ??= { count: 0, bytes: 0 }
        heavy[hit].count += 1
        heavy[hit].bytes += item.file.size
      }
    }
  }

  const blockers = []
  if (limits && selected.length > limits.max_files) {
    blockers.push(`${selected.length} files selected; one scan can hold at most ${limits.max_files}.`)
  }
  if (limits && totalBytes > limits.max_total_mb * MB) {
    blockers.push(`${formatBytes(totalBytes)} selected; one scan can hold at most ${limits.max_total_mb} MB.`)
  }
  return { totalBytes, oversized, heavy, blockers }
}

export default function NewScan() {
  const navigate = useNavigate()
  const filesInput = useRef(null)
  const folderInput = useRef(null)
  const abortRef = useRef(null)

  const [limits, setLimits] = useState(null)
  const [limitsError, setLimitsError] = useState(null)
  const [mode, setMode] = useState('files') // 'files' | 'folder'
  const [selected, setSelected] = useState([]) // [{ file, path }]
  const [name, setName] = useState('')
  const [progress, setProgress] = useState(null) // null when idle, else 0..1
  const [error, setError] = useState(null)

  useEffect(() => {
    let cancelled = false
    apiGet('/scans/limits/')
      .then((data) => { if (!cancelled) setLimits(data) })
      .catch((err) => { if (!cancelled) setLimitsError(err instanceof ApiError ? err.message : 'Unexpected error.') })
    return () => { cancelled = true }
  }, [])

  const summary = useMemo(() => summarise(selected, limits, mode), [selected, limits, mode])
  const uploading = progress !== null
  const serverHost = new URL(BASE_URL).host

  function handlePick(event, kind) {
    const files = Array.from(event.target.files ?? [])
    event.target.value = '' // so choosing the same files again still fires onChange
    if (!files.length) return
    setError(null)
    setMode(kind)
    setSelected(files.map((file) => ({ file, path: kind === 'folder' ? file.webkitRelativePath : file.name })))
  }

  async function handleSubmit(event) {
    event.preventDefault()
    if (!selected.length || summary.blockers.length || uploading) return

    const form = new FormData()
    form.append('scan_type', mode)
    form.append('name', name.trim())
    for (const { file, path } of selected) {
      form.append('files', file, file.name)
      // Django keeps only the base name of an uploaded file, so folder paths
      // travel separately - one per file, in the same order.
      if (mode === 'folder') form.append('paths', path)
    }

    const controller = new AbortController()
    abortRef.current = controller
    setError(null)
    setProgress(0)
    try {
      const scan = await apiUpload('/scans/', form, { onProgress: setProgress, signal: controller.signal })
      navigate(`/scans/${scan.id}`)
    } catch (err) {
      if (!err?.aborted) setError(err instanceof ApiError ? err.message : 'Unexpected error.')
      setProgress(null)
    } finally {
      abortRef.current = null
    }
  }

  const defaultName =
    mode === 'folder' && selected.length
      ? selected[0].path.split('/')[0]
      : `Upload of ${selected.length} file${selected.length === 1 ? '' : 's'}`

  return (
    <div className="space-y-6">
      <header>
        <Link to="/scans" className="text-sm text-slate-500 hover:text-slate-900">← Scans</Link>
        <h2 className="mt-2 text-2xl font-semibold text-slate-900">New scan</h2>
        <p className="mt-1 text-sm text-slate-500">
          Files are sent only to this PrivGuard server (<code className="font-mono">{serverHost}</code>).
        </p>
      </header>

      {limitsError && (
        <div role="alert" className="rounded-md border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-800">
          Could not load upload limits: {limitsError}
        </div>
      )}

      <form onSubmit={handleSubmit} className="space-y-6">
        <section className="rounded-lg border border-slate-200 bg-white p-6">
          <h3 className="text-sm font-semibold text-slate-900">1. Choose what to scan</h3>
          {limits && (
            <p className="mt-1 text-xs text-slate-500">
              Up to {limits.max_files} files and {limits.max_total_mb} MB per scan; {limits.max_file_mb} MB per file.
            </p>
          )}

          <div className="mt-4 flex flex-wrap gap-3">
            <button
              type="button"
              disabled={uploading}
              onClick={() => filesInput.current?.click()}
              className="rounded-md border border-slate-300 px-4 py-2 text-sm font-medium text-slate-700
                         hover:bg-slate-50 disabled:opacity-50"
            >
              Choose files…
            </button>
            <button
              type="button"
              disabled={uploading}
              onClick={() => folderInput.current?.click()}
              className="rounded-md border border-slate-300 px-4 py-2 text-sm font-medium text-slate-700
                         hover:bg-slate-50 disabled:opacity-50"
            >
              Choose a folder…
            </button>
          </div>

          <input ref={filesInput} type="file" multiple hidden onChange={(e) => handlePick(e, 'files')} />
          <input ref={folderInput} type="file" multiple hidden {...FOLDER_PICKER} onChange={(e) => handlePick(e, 'folder')} />

          {selected.length > 0 && (
            <div className="mt-5 space-y-3">
              <p className="text-sm text-slate-700">
                <span className="font-medium">{selected.length}</span> {mode === 'folder' ? 'files in folder' : 'files'} ·{' '}
                {formatBytes(summary.totalBytes)}
              </p>

              {summary.blockers.map((message) => (
                <p key={message} role="alert" className="rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-800">
                  {message} Remove some files or choose a smaller folder.
                </p>
              ))}

              {Object.entries(summary.heavy).map(([folder, info]) => (
                <p key={folder} className="rounded-md border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-900">
                  {info.count} files ({formatBytes(info.bytes)}) are inside <code className="font-mono">{folder}/</code>,
                  which usually holds generated files. Excluding folders arrives in Cycle 8 — for now, consider choosing a
                  subfolder instead.
                </p>
              ))}

              {summary.oversized.length > 0 && (
                <p className="rounded-md border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-900">
                  {summary.oversized.length} file{summary.oversized.length === 1 ? ' is' : 's are'} over the{' '}
                  {limits.max_file_mb} MB per-file limit and will be listed as rejected. The rest are unaffected.
                </p>
              )}

              <div className="max-h-64 overflow-y-auto rounded-md border border-slate-200">
                <table className="w-full text-sm">
                  <tbody className="divide-y divide-slate-100">
                    {selected.slice(0, PREVIEW_ROWS).map(({ file, path }) => (
                      <tr key={path}>
                        <td className="max-w-0 truncate px-3 py-1.5 text-slate-700" title={path}>{path}</td>
                        <td className="whitespace-nowrap px-3 py-1.5 text-right text-slate-500">{formatBytes(file.size)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
                {selected.length > PREVIEW_ROWS && (
                  <p className="border-t border-slate-100 px-3 py-1.5 text-xs text-slate-500">
                    …and {selected.length - PREVIEW_ROWS} more
                  </p>
                )}
              </div>
            </div>
          )}
        </section>

        <section className="rounded-lg border border-slate-200 bg-white p-6">
          <label htmlFor="scan-name" className="text-sm font-semibold text-slate-900">
            2. Name <span className="font-normal text-slate-500">(optional)</span>
          </label>
          <input
            id="scan-name"
            type="text"
            maxLength={120}
            value={name}
            disabled={uploading}
            onChange={(e) => setName(e.target.value)}
            placeholder={selected.length ? defaultName : 'e.g. Q3 customer exports'}
            className="mt-2 block w-full rounded-md border border-slate-300 px-3 py-2 text-sm
                       focus:border-slate-900 focus:ring-1 focus:ring-slate-900 focus:outline-none"
          />
        </section>

        {error && (
          <div role="alert" className="rounded-md border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-800">
            {error}
          </div>
        )}

        {uploading ? (
          <div className="rounded-lg border border-slate-200 bg-white p-6">
            <div className="flex items-center justify-between text-sm">
              <span className="font-medium text-slate-900">
                {progress < 1 ? `Uploading… ${Math.round(progress * 100)}%` : 'Upload complete. Checking files on the server…'}
              </span>
              {progress < 1 && (
                <button type="button" onClick={() => abortRef.current?.abort()} className="text-slate-500 hover:text-slate-900">
                  Cancel upload
                </button>
              )}
            </div>
            <div className="mt-3 h-2 overflow-hidden rounded-full bg-slate-100">
              <div className="h-full bg-slate-900 transition-all" style={{ width: `${Math.round(progress * 100)}%` }} />
            </div>
          </div>
        ) : (
          <button
            type="submit"
            disabled={!selected.length || summary.blockers.length > 0 || !limits}
            className="rounded-md bg-slate-900 px-4 py-2 text-sm font-medium text-white
                       hover:bg-slate-800 disabled:cursor-not-allowed disabled:opacity-50"
          >
            Create scan
          </button>
        )}
      </form>
    </div>
  )
}
