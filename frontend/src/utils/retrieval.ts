export function getResultTitle(metadata: Record<string, unknown>): string {
  const filename = metadata.filename || metadata.source_label || '未知来源'
  return String(filename)
}

export function getResultSubtitle(metadata: Record<string, unknown>): string {
  const parts = []
  if (metadata.section_title) parts.push(String(metadata.section_title))
  if (typeof metadata.chunk_index === 'number') parts.push(`chunk ${metadata.chunk_index + 1}`)
  if (!parts.length && metadata.document_id) parts.push(String(metadata.document_id))
  return parts.join(' · ')
}

export function getResultFilename(metadata: Record<string, unknown>): string {
  const value = metadata.filename || metadata.source_label
  return value ? String(value) : ''
}

export function getResultSectionTitle(metadata: Record<string, unknown>): string {
  return metadata.section_title ? String(metadata.section_title) : ''
}

export function getResultChunkLabel(metadata: Record<string, unknown>): string {
  return typeof metadata.chunk_index === 'number' ? `chunk ${metadata.chunk_index + 1}` : ''
}
