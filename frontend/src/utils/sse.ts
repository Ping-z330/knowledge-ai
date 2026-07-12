/** SSE 流式请求公用模块。封装 fetch → ReadableStream → 逐行解析，
 *  调用方只需 `for await` 迭代事件，无需关心底层流处理细节。
 */

export interface SSEEvent {
  type: string
  [key: string]: unknown
}

export async function* streamSSE(
  url: string,
  body: Record<string, unknown>,
  token?: string,
): AsyncGenerator<SSEEvent> {
  const response = await fetch(url, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: JSON.stringify(body),
  })

  if (!response.ok) {
    const errorBody = await response.json().catch(() => null)
    throw new Error(errorBody?.detail || `HTTP ${response.status}`)
  }

  const reader = response.body?.getReader()
  if (!reader) throw new Error('Stream not supported')

  const decoder = new TextDecoder()
  let buffer = ''

  while (true) {
    const { done, value } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })
    const lines = buffer.split('\n')
    buffer = lines.pop() || ''
    for (const line of lines) {
      if (!line.startsWith('data: ')) continue
      try {
        yield JSON.parse(line.slice(6))
      } catch {
        /* skip malformed SSE frame */
      }
    }
  }
}
