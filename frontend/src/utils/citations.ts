export function renderAnswerWithCitations(answerText: string): string {
  return answerText.replace(
    /\[(\d+)\]/g,
    '<sup><a href="#" class="citation-link" data-citation="$1">[$1]</a></sup>',
  )
}

export function handleCitationClick(event: Event): void {
  const target = event.target as HTMLElement
  if (!target.classList.contains('citation-link')) return
  event.preventDefault()
  const citation = target.dataset.citation
  const sourceEl = document.querySelector(`[data-source-citation="${citation}"]`)
  if (sourceEl) {
    sourceEl.scrollIntoView({ behavior: 'smooth', block: 'center' })
    sourceEl.classList.add('source-flash')
    setTimeout(() => sourceEl.classList.remove('source-flash'), 2000)
  }
}

export function highlightSourceCitation(event: Event): void {
  const el = event.currentTarget as HTMLElement
  const citation = el.dataset.sourceCitation
  if (!citation) return
  document.querySelectorAll(`.citation-link[data-citation="${citation}"]`).forEach((link) => {
    link.classList.add('citation-highlight')
  })
}

export function clearSourceCitation(event: Event): void {
  const el = event.currentTarget as HTMLElement
  const citation = el.dataset.sourceCitation
  if (!citation) return
  document.querySelectorAll(`.citation-link[data-citation="${citation}"]`).forEach((link) => {
    link.classList.remove('citation-highlight')
  })
}

export function highlightText(text: string, query: string): string {
  const cleanQuery = query.trim()
  if (!cleanQuery) return escapeHtml(text)

  const terms = Array.from(
    new Set(
      cleanQuery
        .split(/\s+/)
        .filter(Boolean)
        .slice(0, 6),
    ),
  )
  if (!terms.length) return escapeHtml(text)

  const pattern = new RegExp(`(${terms.map((term) => escapeRegExp(term)).join('|')})`, 'gi')
  return escapeHtml(text).replace(pattern, '<mark>$1</mark>')
}

function escapeHtml(value: string): string {
  return value
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#39;')
}

function escapeRegExp(value: string): string {
  return value.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
}

export function scoreColor(score: number): string {
  if (score >= 0.7) return '#2f6f5e'
  if (score >= 0.4) return '#c28b1c'
  return '#8a968f'
}

export function scoreBarWidth(score: number): string {
  return `${Math.round(score * 100)}%`
}
