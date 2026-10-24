import { useEffect, useMemo, useState } from 'react'
import { useSearchParams } from 'react-router-dom'

import FindingsTable from '../components/FindingsTable'
import { apiGet } from '../lib/api'
import { FILTERS } from '../lib/findings'

/**
 * Every finding in your scans, searchable and filterable (FR-083, FR-087).
 *
 * The filters live in the address - /findings?severity=critical,high&q=deploy -
 * so a view can be bookmarked or shared, and the dashboard can link straight
 * into a filtered list. The address is the single source of truth.
 */

const FILTER_KEYS = ['scan', ...Object.keys(FILTERS), 'q']
const SEARCH_DELAY_MS = 300

function optionLabel(options, value) {
  // A link may carry several values ("critical,high"): name each of them.
  return value.split(',').map((v) => options[v] ?? v).join(' + ')
}

function FilterSelect({ name, value, onChange }) {
  const { label, options } = FILTERS[name]
  const custom = value && !(value in options)
  return (
    <label className="flex flex-col gap-1 text-xs font-medium text-slate-500">
      {label}
      <select
        value={value ?? ''}
        onChange={(event) => onChange(name, event.target.value)}
        className="rounded-md border border-slate-300 bg-white px-2 py-1.5 text-sm font-normal text-slate-800"
      >
        <option value="">All</option>
        {custom && <option value={value}>{optionLabel(options, value)}</option>}
        {Object.entries(options).map(([key, text]) => (
          <option key={key} value={key}>{text}</option>
        ))}
      </select>
    </label>
  )
}

function ScanChip({ scanId, onRemove }) {
  const [name, setName] = useState(null)
  useEffect(() => {
    let cancelled = false
    apiGet(`/scans/${encodeURIComponent(scanId)}/`)
      .then((scan) => { if (!cancelled) setName(scan.name) })
      .catch(() => { if (!cancelled) setName('a scan you cannot open') })
    return () => { cancelled = true }
  }, [scanId])
  return (
    <span className="inline-flex items-center gap-2 rounded-full bg-slate-100 px-3 py-1 text-xs text-slate-700">
      Scan: <span className="max-w-xs truncate font-medium">{name ?? '…'}</span>
      <button type="button" onClick={onRemove} className="text-slate-500 hover:text-slate-900" aria-label="Remove scan filter">
        ✕
      </button>
    </span>
  )
}

export default function Findings() {
  const [params, setParams] = useSearchParams()
  const [search, setSearch] = useState(params.get('q') ?? '')

  function setFilter(name, value) {
    setParams((current) => {
      const next = new URLSearchParams(current)
      if (value) next.set(name, value)
      else next.delete(name)
      return next
    })
  }

  // Search follows typing after a short pause, not on every key press.
  useEffect(() => {
    const timer = setTimeout(() => {
      setParams((current) => {
        const next = new URLSearchParams(current)
        const text = search.trim()
        if (text === (current.get('q') ?? '')) return current
        if (text) next.set('q', text)
        else next.delete('q')
        return next
      }, { replace: true })
    }, SEARCH_DELAY_MS)
    return () => clearTimeout(timer)
  }, [search, setParams])

  const filters = useMemo(
    () => FILTER_KEYS.filter((key) => params.get(key))
      .map((key) => `${key}=${encodeURIComponent(params.get(key))}`)
      .join('&'),
    [params],
  )
  const scanId = params.get('scan')

  return (
    <div className="space-y-6">
      <header>
        <h2 className="text-2xl font-semibold text-slate-900">Findings</h2>
        <p className="mt-1 text-sm text-slate-500">
          Everything PrivGuard found in your scans, most serious first. Values are masked: search finds file names,
          kinds of finding and masked values - never the real values, which were never stored.
        </p>
      </header>

      <div className="space-y-3 rounded-lg border border-slate-200 bg-white p-4">
        <div className="flex flex-wrap items-end gap-3">
          <label className="flex min-w-56 flex-1 flex-col gap-1 text-xs font-medium text-slate-500">
            Search
            <input
              type="search"
              value={search}
              maxLength={100}
              onChange={(event) => setSearch(event.target.value)}
              placeholder="File name, kind of finding, masked value…"
              className="rounded-md border border-slate-300 px-3 py-1.5 text-sm font-normal text-slate-800"
            />
          </label>
          {Object.keys(FILTERS).map((name) => (
            <FilterSelect key={name} name={name} value={params.get(name)} onChange={setFilter} />
          ))}
        </div>
        {(filters || scanId) && (
          <div className="flex flex-wrap items-center gap-3">
            {scanId && <ScanChip scanId={scanId} onRemove={() => setFilter('scan', '')} />}
            <button
              type="button"
              onClick={() => { setSearch(''); setParams(new URLSearchParams()) }}
              className="text-xs font-medium text-slate-600 hover:text-slate-900"
            >
              Clear all filters
            </button>
          </div>
        )}
      </div>

      <FindingsTable key={filters} filters={filters} showScan />
    </div>
  )
}
