import { NOT_ASSESSED, SEVERITIES } from '../lib/findings'

/**
 * A finding's severity (FR-073, NFR-035): a dot in the validated severity
 * colour, and the level written out in neutral ink beside it. Colour helps,
 * but never carries the meaning alone - and text never wears the colour,
 * which a pale amber would make hard to read. Hovering shows the reason (FR-076).
 */
export default function SeverityBadge({ severity, reason }) {
  const meta = SEVERITIES[severity] ?? NOT_ASSESSED
  return (
    <span
      title={reason || meta.hint}
      className="inline-flex items-center gap-1.5 whitespace-nowrap rounded-full bg-white px-2.5 py-0.5 text-xs
                 font-medium text-slate-800 ring-1 ring-inset ring-slate-200"
    >
      <span aria-hidden="true" className={`h-2 w-2 rounded-full ${meta.mark}`} />
      {meta.label}
    </span>
  )
}
