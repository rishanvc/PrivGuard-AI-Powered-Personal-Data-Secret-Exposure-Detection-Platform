/**
 * Stand-in for screens whose cycle has not arrived yet.
 * Honest empty state rather than a broken-looking page (NFR-037).
 */
export default function Placeholder({ title, cycle, description }) {
  return (
    <div className="space-y-6">
      <header>
        <h2 className="text-2xl font-semibold text-slate-900">{title}</h2>
        <p className="mt-1 text-sm text-slate-500">{description}</p>
      </header>
      <div className="rounded-lg border border-dashed border-slate-300 bg-white p-10 text-center">
        <p className="text-sm font-medium text-slate-700">Not implemented yet</p>
        <p className="mt-1 text-sm text-slate-500">Planned for Cycle {cycle}.</p>
      </div>
    </div>
  )
}
