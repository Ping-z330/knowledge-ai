import { nextTick, ref, watch, type Ref } from 'vue'
import type { Conversation, ConversationMessage } from '../types'
import { api } from '../utils/api'
import { useQA } from './useQA'

let convIdCounter = 0
function nextConvId() { convIdCounter++; return `conv-${Date.now()}-${convIdCounter}` }

export function useConversation(
  selectedKnowledgeBaseId: Ref<string>,
  indexedCount: Ref<number>,
  topK: Ref<number>,
  agenticMode: Ref<boolean>,
  enableWebSearch: Ref<boolean>,
) {
  const qa = useQA(selectedKnowledgeBaseId, indexedCount)

  watch(topK, (v) => { qa.topK.value = v }, { immediate: true })
  watch(agenticMode, (v) => { qa.agenticMode.value = v }, { immediate: true })
  watch(enableWebSearch, (v) => { qa.enableWebSearch.value = v }, { immediate: true })

  const conversation = ref<ConversationMessage[]>([])
  const input = ref('')
  const messagesRef = ref<HTMLElement | null>(null)
  const conversationId = ref('')
  const conversations = ref<Conversation[]>([])
  const loadingConversations = ref(false)

  function scrollToBottom() {
    nextTick(() => {
      const el = messagesRef.value
      if (el) el.scrollTop = el.scrollHeight
    })
  }

  watch([conversation, qa.streamingAnswer], () => scrollToBottom(), { deep: true })

  function buildHistory(): { role: string; content: string }[] {
    return conversation.value.slice(-10).map((m) => ({ role: m.role, content: m.content }))
  }

  const loadConversations = async () => {
    const kbId = selectedKnowledgeBaseId.value
    if (!kbId) return
    loadingConversations.value = true
    try {
      const { data } = await api.get<Conversation[]>(
        `/knowledge-bases/${kbId}/conversations`,
      )
      conversations.value = data
    } catch {
      conversations.value = []
    } finally {
      loadingConversations.value = false
    }
  }

  const loadConversation = async (convId: string) => {
    const kbId = selectedKnowledgeBaseId.value
    if (!kbId || !convId) return
    try {
      const { data } = await api.get<Conversation>(
        `/knowledge-bases/${kbId}/conversations/${convId}`,
      )
      conversationId.value = convId
      // Interleave Q&A pairs into conversation messages
      const interleaved: ConversationMessage[] = []
      for (const qaItem of data.messages || []) {
        interleaved.push({
          id: qaItem.id + '_q',
          role: 'user',
          content: qaItem.question,
          sources: [],
          rating: null,
          answerId: '',
          created_at: qaItem.created_at,
        })
        interleaved.push({
          id: qaItem.id,
          role: 'assistant',
          content: qaItem.answer,
          sources: qaItem.sources,
          rating: qaItem.rating,
          answerId: qaItem.id,
          created_at: qaItem.created_at,
        })
      }
      conversation.value = interleaved
    } catch {
      // conversation not found — start fresh
    }
  }

  // KB 切换时自动恢复最近对话（必须在 loadConversations/loadConversation 定义之后）
  watch(selectedKnowledgeBaseId, async (kbId) => {
    if (!kbId) return
    await loadConversations()
    const latest = conversations.value[0]
    if (latest) {
      await loadConversation(latest.id)
    }
  }, { immediate: true })

  const ensureConversation = async () => {
    if (conversationId.value) return
    const kbId = selectedKnowledgeBaseId.value
    if (!kbId) return
    try {
      const { data } = await api.post<Conversation>(
        `/knowledge-bases/${kbId}/conversations`,
      )
      conversationId.value = data.id
    } catch {
    }
  }

  const ask = async () => {
    const question = input.value.trim()
    if (!selectedKnowledgeBaseId.value || !question) return
    if (indexedCount.value === 0) return

    await ensureConversation()

    const userMsg: ConversationMessage = {
      id: nextConvId(), role: 'user', content: question,
      sources: [], rating: null, answerId: '', created_at: new Date().toISOString(),
    }
    conversation.value = [...conversation.value, userMsg]
    input.value = ''

    qa.question.value = question
    const history = buildHistory()
    const convId = conversationId.value
    if (agenticMode.value) {
      await qa.askAgentic(history, convId)
    } else {
      await qa.askQuestion(history, convId)
    }

    // 更新当前对话的标题（用第一个问题）
    const answerText = qa.streamingAnswer.value || qa.answer.value?.answer || ''
    const sources = qa.answer.value?.sources || qa.retrievalResults.value.map((r, i) => ({
      citation: i + 1, vector_id: r.vector_id, text: r.text, score: r.score, metadata: r.metadata,
    }))

    if (answerText) {
      const assistantMsg: ConversationMessage = {
        id: nextConvId(), role: 'assistant', content: answerText,
        sources, answerId: qa.currentAnswerId.value, rating: null,
        created_at: new Date().toISOString(),
      }
      conversation.value = [...conversation.value, assistantMsg]
    }

    // 首次问答后设置对话标题，刷新列表
    if (conversationId.value) {
      const kbId = selectedKnowledgeBaseId.value
      try {
        await api.patch(`/knowledge-bases/${kbId}/conversations/${conversationId.value}`, {
          title: question.slice(0, 40),
        })
      } catch { /* ignore */ }
      await loadConversations()
    }
  }

  const clear = () => {
    conversation.value = []
    conversationId.value = ''
    qa.questionError.value = ''
    loadConversations()
  }

  const updateLocalRating = (answerId: string, rating: number) => {
    const msg = conversation.value.find((m) => m.answerId === answerId)
    if (msg) msg.rating = rating
  }

  return {
    conversation, input, messagesRef,
    asking: qa.asking, streaming: qa.streaming, streamingAnswer: qa.streamingAnswer,
    agenticStatus: qa.agenticStatus, agenticRounds: qa.agenticRounds,
    agenticScore: qa.agenticScore, agenticSubQueries: qa.agenticSubQueries,
    conversationId, conversations, loadingConversations,
    loadConversations, loadConversation,
    ask, clear, updateLocalRating,
  }
}
