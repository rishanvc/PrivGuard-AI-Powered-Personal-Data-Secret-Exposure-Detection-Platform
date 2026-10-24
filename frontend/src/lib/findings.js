/**
 * Display helpers for findings (FR-078, FR-085).
 *
 * Locations arrive as small objects such as {sheet: "Staff", cell: "C7"} or
 * {part: "comments", field: "author"}; these turn them into plain words.
 */

const PARTS = {
  properties: 'document properties',
  comments: 'comment',
  notes: 'speaker notes',
  footnotes: 'footnote',
  endnotes: 'endnote',
}

const FIELDS = {
  creator: 'author',
  lastModifiedBy: 'last modified by',
  author: 'author',
  Manager: 'manager',
  title: 'title',
}

const KINDS = {
  deleted: 'tracked deletion, not shown in Word',
  'field code': 'field code, not shown in Word',
  ocr: 'read by OCR from an image',
}

/** "sheet Staff, cell C7" · "page 3" · "row 2, column 3" · "comment · author" */
export function describeLocation(location = {}) {
  const parts = []
  if (location.sheet != null) parts.push(`sheet ${location.sheet}${location.cell ? `, cell ${location.cell}` : ''}`)
  if (location.hidden) parts.push('hidden sheet')
  if (location.page != null) parts.push(`page ${location.page}`)
  if (location.slide != null) parts.push(`slide ${location.slide}`)
  if (location.part && location.part !== 'body' && location.part !== 'slide') {
    parts.push(PARTS[location.part] ?? location.part)
  }
  if (location.paragraph != null) parts.push(`paragraph ${location.paragraph}`)
  if (location.row != null) {
    parts.push(`row ${location.row}${location.column != null ? `, column ${location.column}` : ''}`)
  } else if (location.line != null) {
    parts.push(`line ${location.line}`)
  }
  if (location.field) parts.push(FIELDS[location.field] ?? `${location.field} field`)
  if (location.kind) parts.push(KINDS[location.kind] ?? location.kind)
  return parts.join(' · ')
}

/**
 * FR-073's five levels, most serious first - the same order the API sorts by.
 * `mark` is the validated severity colour (index.css) for dots and bars; text
 * stays in neutral ink beside it, so colour never carries the level alone.
 */
export const SEVERITIES = {
  critical: { label: 'Critical', mark: 'bg-sev-critical' },
  high: { label: 'High', mark: 'bg-sev-high' },
  medium: { label: 'Medium', mark: 'bg-sev-medium' },
  low: { label: 'Low', mark: 'bg-sev-low' },
  informational: { label: 'Info', mark: 'bg-sev-info' },
}

/** Found by a scan that ran before severity existed (Cycle 6). Shown honestly, never guessed. */
export const NOT_ASSESSED = {
  label: 'Not assessed',
  mark: 'bg-white ring-1 ring-inset ring-slate-400',
  hint: 'Found before PrivGuard assessed severity. Scan the file again to assess it.',
}

/** FR-086: what a person decided about a finding. */
export const REVIEW_STATUSES = {
  new: { label: 'New', style: 'bg-white text-slate-600 ring-slate-300', hint: 'Not reviewed yet.' },
  confirmed: { label: 'Confirmed', style: 'bg-slate-900 text-white ring-slate-900', hint: 'Real, and still needs fixing.' },
  false_positive: { label: 'False positive', style: 'bg-slate-100 text-slate-500 ring-slate-300', hint: 'Not real. Left out of the risk score.' },
  resolved: { label: 'Resolved', style: 'bg-emerald-50 text-emerald-800 ring-emerald-600/30', hint: 'Fixed. Left out of the risk score.' },
  accepted_risk: { label: 'Accepted risk', style: 'bg-amber-50 text-amber-900 ring-amber-600/30', hint: 'Real, kept on purpose. Still counts towards the risk score.' },
}

/** FR-077: the bands of the 0-100 risk score, with the severity colour each band reads as. */
export const RISK_BANDS = {
  critical: { label: 'Critical', mark: 'bg-sev-critical' },
  high: { label: 'High', mark: 'bg-sev-high' },
  moderate: { label: 'Moderate', mark: 'bg-sev-medium' },
  low: { label: 'Low', mark: 'bg-sev-low' },
}

/** FR-079: the ways the findings list can be sorted (the API's ?ordering=). */
export const ORDERINGS = {
  severity: 'Severity',
  risk: 'Risk',
  confidence: 'Confidence',
  category: 'Category',
  file: 'File',
}

/** FR-087: the filters the API accepts, with their labels. Keys are the API's own values. */
export const FILTERS = {
  severity: {
    label: 'Severity',
    options: { ...Object.fromEntries(Object.entries(SEVERITIES).map(([k, v]) => [k, v.label])), not_assessed: 'Not assessed' },
  },
  category: {
    label: 'Category',
    options: { personal: 'Personal', secret: 'Secret', financial: 'Financial' },
  },
  status: {
    label: 'Review',
    options: Object.fromEntries(Object.entries(REVIEW_STATUSES).map(([k, v]) => [k, v.label])),
  },
  file_type: {
    label: 'File type',
    options: {
      text: 'Text', csv: 'CSV', xlsx: 'Excel', docx: 'Word', pptx: 'PowerPoint', pdf: 'PDF', json: 'JSON',
      yaml: 'YAML', xml: 'XML', env: '.env', config: 'Config', code: 'Code', key: 'Key file',
      png: 'PNG image', jpeg: 'JPEG image',
    },
  },
  method: {
    label: 'Method',
    options: {
      pattern: 'Pattern', 'pattern + validation': 'Pattern + validation', 'pattern + checksum': 'Pattern + checksum',
      context: 'Context', 'entropy heuristic': 'Entropy',
    },
  },
}

/** "Open" findings: those not reviewed away - the dashboard and risk score count only these. */
export const OPEN_STATUSES = 'new,confirmed,accepted_risk'

/** Confidence is a fixed score per rule - shown as a number, never as a percentage that reads like a probability. */
export function formatConfidence(confidence) {
  return Number(confidence).toFixed(2)
}
