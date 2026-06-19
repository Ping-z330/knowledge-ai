import { nextTick, ref, watch, type Ref } from 'vue'
import type { AnswerSource, ConversationMessage } from '../types'

let convIdCounter = 0
function nextConvId() { convIdCounter++; return `conv-${Date.now()}-${convIdCounter}` }

export function useConversation(selectedKnowledgeBaseId: Ref<string>, indexedCount: Ref<number>) {
  const conversation = ref<ConversationMessage[]>([])
  const input = ref('')
  const asking = ref(false)
  const streaming = ref(false)
  const streamingAnswer = ref('')
  const messagesRef = ref<HTMLElement | null>(null)

  function scrollToBottom() {
    nextTick(() => {
      const el = messagesRef.value
      if (el) el.scrollTop = el.scrollHeight
    })
  }

  watch([conversation, streamingAnswer], () => scrollToBottom(), { deep: true })

  function buildHistory(): { role: string; content: string }[] {
    return conversation.value.slice(-10).map((m) => ({ role: m.role, content: m.content }))
  }

  const ask = async () => {
    const question = input.value.trim()
    if (!selectedKnowledgeBaseId.value || !question) return
    if (indexedCount.value === 0) return

    asking.value = true
    streaming.value = true
    streamingAnswer.value = ''

    const userMsg: ConversationMessage = {
      id: nextConvId(), role: 'user', content: question,
      sources: [], rating: null, answerId: '', created_at: new Date().toISOString(),
    }
    conversation.value = [...conversation.value, userMsg]
    input.value = ''

    const assistantMsg: ConversationMessage = {
      id: nextConvId(), role: 'assistant', content: '',
      sources: [], rating: null, answerId: '', created_at: new Date().toISOString(),
    }

    try {
      const token = import.meta.env.VITE_API_TOKEN
      const response = await fetch(
        `/api/knowledge-bases/${selectedKnowledgeBaseId.value}/questions/stream`,
        {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            ...(token ? { Authorization: `Bearer ${token}` } : {}),
          },
          body: JSON.stringify({ question, top_k: 5, conversation_history: buildHistory() }),
        },
      )
      if (!response.ok) throw new Error((await response.json().catch(() => ({}))).detail || `HTTP ${response.status}`)
      const reader = response.body?.getReader()
      if (!reader) throw new Error('Stream not supported')

      const decoder = new TextDecoder()
      let buffer = ''
      let sources: AnswerSource[] = []

      while (true) {
        const { done, value } = await reader.read()
        if (done) break
        buffer += decoder.decode(value, { stream: true })
        const lines = buffer.split('\n')
        buffer = lines.pop() || ''
        for (const line of lines) {
          if (!line.startsWith('data: ')) continue
          try {
            const event = JSON.parse(line.slice(6))
            if (event.type === 'sources') {
              sources = event.sources.map((s: AnswerSource) => ({
                citation: s.citation ?? 0, vector_id: s.vector_id,
                text: s.text, score: s.score, metadata: s.metadata,
              }))
            } else if (event.type === 'token') {
              streamingAnswer.value += event.content
            } else if (event.type === 'done') {
              assistantMsg.content = streamingAnswer.value
              assistantMsg.sources = sources
              assistantMsg.answerId = event.answer_id || ''
              conversation.value = [...conversation.value, assistantMsg]
              streaming.value = false
              streamingAnswer.value = ''
            } else if (event.type === 'error') {
              streaming.value = false
            }
          } catch { /* skip */ }
        }
      }
    } catch {
      streaming.value = false
    } finally {
      asking.value = false
      if (streaming.value && streamingAnswer.value) {
        assistantMsg.content = streamingAnswer.value
        conversation.value = [...conversation.value, assistantMsg]
        streaming.value = false
        streamingAnswer.value = ''
      }
      if (!streaming.value && !assistantMsg.content && conversation.value.at(-1)?.id === assistantMsg.id) {
        conversation.value = conversation.value.slice(0, -1)
      }
    }
  }

  const clear = () => {
    conversation.value = []
    streaming.value = false
    streamingAnswer.value = ''
  }

  const updateLocalRating = (answerId: string, rating: number) => {
    const msg = conversation.value.find((m) => m.answerId === answerId)
    if (msg) msg.rating = rating
  }

  return { conversation, input, asking, streaming, streamingAnswer, messagesRef, ask, clear, updateLocalRating }
}
