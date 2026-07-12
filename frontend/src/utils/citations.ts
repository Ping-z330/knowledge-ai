/** Extract citation numbers actually used in answer text, e.g. [1][4] → {1,4} */
export function extractCitedIds(answerText: string): Set<number> {
  const ids = new Set<number>()
  for (const m of answerText.matchAll(/\[(\d+)\]/g)) {
    ids.add(Number(m[1]))
  }
  return ids
}

export function renderAnswerWithCitations(answerText: string): string {
  return answerText.replace(
    /\[(\d+)\]/g,
    '<sup><a href="#" class="citation-link" data-citation="$1">[$1]</a></sup>',
  )
}

// 处理点击引用的事件，滚动到对应的来源元素并高亮显示
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

// 处理鼠标悬停在来源元素上的事件，高亮显示对应的引用链接
export function highlightSourceCitation(event: Event): void {
  const el = event.currentTarget as HTMLElement
  const citation = el.dataset.sourceCitation
  if (!citation) return
  document.querySelectorAll(`.citation-link[data-citation="${citation}"]`).forEach((link) => {
    link.classList.add('citation-highlight')
  })
}

// 处理鼠标离开来源元素的事件，取消高亮显示对应的引用链接
export function clearSourceCitation(event: Event): void {
  const el = event.currentTarget as HTMLElement
  const citation = el.dataset.sourceCitation
  if (!citation) return
  document.querySelectorAll(`.citation-link[data-citation="${citation}"]`).forEach((link) => {
    link.classList.remove('citation-highlight')
  })
}

// 高亮显示答案文本中与查询相关的部分，首先清理查询字符串，提取出不重复的关键词（最多 6 个），
// 然后构建一个正则表达式匹配这些关键词，在答案文本中用 <mark> 标签包裹匹配到的部分，同时对答案文本进行 HTML 转义以防止 XSS 攻击
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

// 对文本进行 HTML 转义，替换 &, <, >, ", ' 等特殊字符为对应的 HTML 实体，以防止 XSS 攻击
function escapeHtml(value: string): string {
  return value
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#39;')
}

// 对正则表达式中的特殊字符进行转义，确保它们被当作普通字符处理，而不是正则表达式的元字符
function escapeRegExp(value: string): string {
  return value.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
}

// 根据相似度分数返回对应的颜色，分数 >= 0.7 返回绿色，分数 >= 0.4 返回橙色，否则返回灰色
export function scoreColor(score: number): string {
  if (score >= 0.7) return '#2f6f5e'
  if (score >= 0.4) return '#c28b1c'
  return '#8a968f'
}

// 根据相似度分数计算对应的进度条宽度，分数乘以 100 并四舍五入后返回百分比字符串
export function scoreBarWidth(score: number): string {
  return `${Math.round(score * 100)}%`
}
