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

/** Confidence is a fixed score per rule - shown as a number, never as a percentage that reads like a probability. */
export function formatConfidence(confidence) {
  return Number(confidence).toFixed(2)
}
