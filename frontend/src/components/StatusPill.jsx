/**
 * Small coloured status indicator (NFR-035: consistent visual indicators).
 *
 * One vocabulary across the app:
 *   health   ok | degraded | disabled | error
 *   scans    draft | queued | processing | completed | partially_completed | failed | cancelled
 *   files    pending | completed | skipped | rejected | unsupported (+ processing, failed)
 *   reading  succeeded | partial | not_supported (+ failed)    - how completely a file was read
 *
 * Pass the human-readable label as children; the raw status picks the colour.
 */

const GREEN = 'bg-emerald-100 text-emerald-800 ring-emerald-600/20'
const AMBER = 'bg-amber-100 text-amber-900 ring-amber-600/20'
const RED = 'bg-red-100 text-red-800 ring-red-600/20'
const BLUE = 'bg-sky-100 text-sky-800 ring-sky-600/20'
const INDIGO = 'bg-indigo-100 text-indigo-800 ring-indigo-600/20'
const GREY = 'bg-slate-100 text-slate-600 ring-slate-500/20'

const STYLES = {
  // health
  ok: GREEN,
  degraded: AMBER,
  disabled: GREY,
  error: RED,
  // scans
  draft: GREY,
  queued: BLUE,
  processing: INDIGO,
  completed: GREEN,
  partially_completed: AMBER,
  failed: RED,
  cancelled: GREY,
  // files
  pending: BLUE,
  skipped: GREY,
  rejected: RED,
  unsupported: AMBER,
  // extraction
  succeeded: GREEN,
  partial: AMBER,
  not_supported: AMBER,
}

export default function StatusPill({ status, children }) {
  const style = STYLES[status] ?? GREY
  return (
    <span
      className={`inline-flex items-center whitespace-nowrap rounded-full px-2.5 py-0.5 text-xs
                  font-medium uppercase tracking-wide ring-1 ring-inset ${style}`}
    >
      {children ?? status}
    </span>
  )
}
