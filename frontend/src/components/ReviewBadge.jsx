import { REVIEW_STATUSES } from '../lib/findings'

/** What a person decided about a finding (FR-086). Hovering explains what the status means. */
export default function ReviewBadge({ status }) {
  const meta = REVIEW_STATUSES[status] ?? REVIEW_STATUSES.new
  return (
    <span
      title={meta.hint}
      className={`inline-flex items-center whitespace-nowrap rounded-full px-2.5 py-0.5 text-xs font-medium
                  ring-1 ring-inset ${meta.style}`}
    >
      {meta.label}
    </span>
  )
}
