import { RISK_BANDS } from '../lib/findings'

/**
 * A 0-100 risk score as a meter (FR-075, FR-077): the fill in its band's
 * colour on a pale track, with the number and the band's NAME always written
 * beside it - colour never carries the band alone. "No score" is shown as
 * such, never as an empty meter that would read as 0.
 */
export default function RiskMeter({ score, band, size = 'md' }) {
  if (score === null || score === undefined) {
    return <span className="text-sm text-slate-400" title="Not scored: nothing searched, or found before risk existed">—</span>
  }
  const meta = RISK_BANDS[band] ?? RISK_BANDS.low
  const large = size === 'lg'
  return (
    <div className={`flex items-center ${large ? 'gap-4' : 'gap-2'}`}>
      <div
        role="meter"
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={score}
        aria-label={`Risk ${score} of 100, ${meta.label}`}
        className={`overflow-hidden rounded-full bg-slate-100 ${large ? 'h-3 w-48' : 'h-2 w-20'}`}
      >
        <div className={`h-full rounded-full ${meta.mark}`} style={{ width: `${score}%` }} />
      </div>
      <span className={`whitespace-nowrap ${large ? 'text-2xl font-semibold text-slate-900' : 'text-sm text-slate-800'}`}>
        {score}
        <span className={`ml-1.5 font-medium text-slate-500 ${large ? 'text-sm' : 'text-xs'}`}>{meta.label}</span>
      </span>
    </div>
  )
}
