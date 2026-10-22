/**
 * Small coloured status indicator.
 *
 * Status vocabulary matches the backend health contract (apps/core/health.py):
 * ok | degraded | disabled | error | unknown
 */

const STYLES = {
  ok:       'bg-emerald-100 text-emerald-800 ring-emerald-600/20',
  degraded: 'bg-amber-100 text-amber-900 ring-amber-600/20',
  disabled: 'bg-slate-100 text-slate-600 ring-slate-500/20',
  error:    'bg-red-100 text-red-800 ring-red-600/20',
  unknown:  'bg-slate-100 text-slate-600 ring-slate-500/20',
}

export default function StatusPill({ status, children }) {
  const style = STYLES[status] ?? STYLES.unknown
  return (
    <span
      className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs
                  font-medium uppercase tracking-wide ring-1 ring-inset ${style}`}
    >
      {children ?? status}
    </span>
  )
}
