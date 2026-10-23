/**
 * Display helpers for extraction results (FR-028).
 *
 * The backend sends counts and fixed-wording notes - never extracted text -
 * so everything here is about describing HOW MUCH of a file was read.
 */

export const EXTRACTION_LABELS = {
  succeeded: 'Read',
  partial: 'Partly read',
  failed: 'Not read',
  not_supported: 'Not supported',
}

const ENCODINGS = {
  'utf-8-sig': 'UTF-8 with BOM',
  'utf-16': 'UTF-16',
  'utf-32': 'UTF-32',
  'windows-1252': 'Windows-1252',
}

function count(n, word) {
  return `${Number(n).toLocaleString()} ${word}${n === 1 ? '' : 's'}`
}

/** "3 pages (1 without text) · 116 characters · 0.04 s" */
export function extractionSummary(stats = {}) {
  const parts = []
  if (stats.pages != null) {
    parts.push(count(stats.pages, 'page') + (stats.pages_without_text ? ` (${stats.pages_without_text} without text)` : ''))
  }
  if (stats.slides != null) {
    parts.push(count(stats.slides, 'slide') + (stats.slides_with_notes ? ` (${stats.slides_with_notes} with notes)` : ''))
  }
  if (stats.sheets != null) {
    parts.push(count(stats.sheets, 'sheet') + (stats.hidden_sheets ? ` (${stats.hidden_sheets} hidden)` : ''))
  }
  if (stats.paragraphs != null) parts.push(count(stats.paragraphs, 'paragraph'))
  if (stats.tracked_deletions) parts.push(count(stats.tracked_deletions, 'tracked deletion'))
  if (stats.rows != null) parts.push(count(stats.rows, 'row'))
  if (stats.cells != null) parts.push(count(stats.cells, 'cell'))
  if (stats.lines != null) parts.push(count(stats.lines, 'line'))
  if (stats.characters != null) parts.push(count(stats.characters, 'character'))
  if (stats.encoding && stats.encoding !== 'utf-8') parts.push(ENCODINGS[stats.encoding] ?? stats.encoding)
  if (stats.seconds != null) parts.push(`${stats.seconds} s`)
  return parts.join(' · ')
}
