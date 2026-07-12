import { computed, ref, type Ref } from 'vue'
import type { AnswerSource, QuestionAnswer, QuestionResponse, RetrievalResult } from '../types'
import { api, extractApiError } from '../utils/api'
import { streamSSE } from '../utils/sse'

export function useQA(selectedKnowledgeBaseId: Ref<string>, indexedCount: Ref<number>) {
  const question = ref('')
  const questionError = ref('')
  const answer = ref<QuestionResponse | null>(null)
  const retrievalResults = ref<RetrievalResult[]>([])
  const questionAnswers = ref<QuestionAnswer[]>([])
  const topK = ref(5)
  const asking = ref(false)
  const streaming = ref(false)
  const streamingAnswer = ref('')
  const retrieving = ref(false)
  const currentAnswerId = ref('')
  const ratingSubmitting = ref(false)
  const loadingHistory = ref(false)
  const busyAnswerId = ref('')
  const qaActiveTab = ref('conversation')

  // Agentic 模式
  const agenticMode = ref(false)
  const agenticStatus = ref('')
  const agenticRounds = ref(0)
  const agenticScore = ref<number | null>(null)
  const agenticSubQueries = ref<string[]>([])
  const enableWebSearch = ref(false)

  const qaPage = ref(1)
  const qaPageSize = 20
  const qaTotal = ref(0)

  const citedVectorIds = computed(() => {
    if (!answer.value) return new Set<string>()
    return new Set(answer.value.sources.map((s) => s.vector_id))
  })

  const currentAnswerRating = computed(() => {
    const item = questionAnswers.value.find((a) => a.id === currentAnswerId.value)
    return item?.rating ?? null
  })

  const retrievalCitationStats = computed(() => {
    const cited = retrievalResults.value.filter((r) => citedVectorIds.value.has(r.vector_id)).length
    return { cited, uncited: retrievalResults.value.length - cited }
  })

  const retrievalQuery = computed(() => question.value.trim())

  const retrievalSummary = computed(() => {
    if (!retrievalQuery.value) return '尚未发起检索'
    const stats = retrievalCitationStats.value
    let extra = `命中 ${retrievalResults.value.length} 条`
    if (answer.value && retrievalResults.value.length > 0) {
      extra += ` · 引用 ${stats.cited} 条 · 未采用 ${stats.uncited} 条`
    }
    return `Query: ${retrievalQuery.value} · top_k: ${topK.value} · ${extra}`
  })

  const loadHistory = async () => {
    if (!selectedKnowledgeBaseId.value) { questionAnswers.value = []; return }
    loadingHistory.value = true
    try {
      const offset = (qaPage.value - 1) * qaPageSize
      const { data } = await api.get<{ items: QuestionAnswer[]; total: number }>(
        `/knowledge-bases/${selectedKnowledgeBaseId.value}/question-answers`,
        { params: { limit: qaPageSize, offset } },
      )
      questionAnswers.value = data.items
      qaTotal.value = data.total
    } finally {
      loadingHistory.value = false
    }
  }

  const retrieveOnly = async () => {
    if (!selectedKnowledgeBaseId.value || !question.value.trim()) return
    if (indexedCount.value === 0) {
      questionError.value = '当前知识库还没有已索引文档。'
      return
    }
    retrieving.value = true
    questionError.value = ''
    answer.value = null
    try {
      const { data } = await api.post<{ results: RetrievalResult[] }>(
        `/knowledge-bases/${selectedKnowledgeBaseId.value}/retrieve`,
        { query: question.value.trim(), top_k: topK.value },
      )
      retrievalResults.value = data.results
    } catch (error) {
      retrievalResults.value = []
      questionError.value = extractApiError(error)
    } finally {
      retrieving.value = false
    }
  }

  const askQuestion = async (conversationHistory?: { role: string; content: string }[], convId?: string) => {
    if (!selectedKnowledgeBaseId.value || !question.value.trim()) return
    if (indexedCount.value === 0) {
      questionError.value = '当前知识库还没有已索引文档。'
      answer.value = null
      retrievalResults.value = []
      return
    }
    asking.value = true
    streaming.value = true
    streamingAnswer.value = ''
    questionError.value = ''
    answer.value = null
    try {
      const token: string | undefined = import.meta.env.VITE_API_TOKEN
      const body: Record<string, unknown> = { question: question.value.trim(), top_k: topK.value }
      if (conversationHistory) body.conversation_history = conversationHistory
      if (convId) body.conversation_id = convId
      for await (const event of streamSSE(
        `/api/knowledge-bases/${selectedKnowledgeBaseId.value}/questions/stream`,
        body,
        token,
      )) {
        if (event.type === 'sources') {
          retrievalResults.value = (event.sources as AnswerSource[]).map((s) => ({
            vector_id: s.vector_id, text: s.text, score: s.score, metadata: s.metadata,
          }))
        } else if (event.type === 'token') {
          streamingAnswer.value += event.content as string
        } else if (event.type === 'done') {
          answer.value = {
            question: question.value.trim(),
            answer: streamingAnswer.value,
            sources: retrievalResults.value.map((r, i) => ({
              citation: i + 1, vector_id: r.vector_id, text: r.text, score: r.score, metadata: r.metadata,
            })),
          }
          currentAnswerId.value = (event.answer_id as string) || ''
          streaming.value = false
          await loadHistory()
        } else if (event.type === 'error') {
          questionError.value = (event.message as string) || 'Stream error'
          streaming.value = false
        }
      }
    } catch (error) {
      retrievalResults.value = []
      streaming.value = false
      questionError.value = error instanceof Error ? error.message : '流式请求失败'
    } finally {
      asking.value = false
      if (streaming.value && !questionError.value) {
        answer.value = {
          question: question.value.trim(),
          answer: streamingAnswer.value || '（回答中断）',
          sources: retrievalResults.value.map((r, i) => ({
            citation: i + 1, vector_id: r.vector_id, text: r.text, score: r.score, metadata: r.metadata,
          })),
        }
        streaming.value = false
        // 异常结束时尝试从 SSE done 事件之外的路径给出 answer id，以便评分按钮可用
        if (!currentAnswerId.value) {
          const match = questionAnswers.value.find(
            (a) => a.question === question.value.trim() && a.answer === streamingAnswer.value,
          )
          currentAnswerId.value = match?.id || ''
        }
      }
    }
  }

  const askAgentic = async (conversationHistory?: { role: string; content: string }[], convId?: string) => {
    if (!selectedKnowledgeBaseId.value || !question.value.trim()) return
    if (indexedCount.value === 0) {
      questionError.value = '当前知识库还没有已索引文档。'
      answer.value = null
      retrievalResults.value = []
      return
    }
    asking.value = true
    streaming.value = true
    streamingAnswer.value = ''
    questionError.value = ''
    answer.value = null
    agenticStatus.value = '正在分析查询...'
    agenticRounds.value = 0
    agenticScore.value = null
    agenticSubQueries.value = []

    try {
      const token: string | undefined = import.meta.env.VITE_API_TOKEN
      const body: Record<string, unknown> = {
        question: question.value.trim(),
        top_k: topK.value,
        max_retrieval_rounds: 3,
        enable_web_search: enableWebSearch.value,
      }
      if (conversationHistory) body.conversation_history = conversationHistory
      if (convId) body.conversation_id = convId
      for await (const event of streamSSE(
        `/api/knowledge-bases/${selectedKnowledgeBaseId.value}/questions/agentic/stream`,
        body,
        token,
      )) {
        if (event.type === 'status') {
          agenticStatus.value =
            `检索完成 · ${event.rounds ?? '?'} 轮 · 上下文评分 ${event.context_score ?? '?'}`
          agenticRounds.value = (event.rounds as number) ?? 0
          agenticScore.value = (event.context_score as number) ?? null
          agenticSubQueries.value = (event.sub_queries as string[]) ?? []
        } else if (event.type === 'sources') {
          retrievalResults.value = (event.sources as AnswerSource[]).map((s) => ({
            vector_id: s.vector_id, text: s.text, score: s.score, metadata: s.metadata,
          }))
        } else if (event.type === 'token') {
          streamingAnswer.value += event.content as string
        } else if (event.type === 'done') {
          answer.value = {
            question: question.value.trim(),
            answer: streamingAnswer.value,
            sources: retrievalResults.value.map((r, i) => ({
              citation: i + 1, vector_id: r.vector_id, text: r.text, score: r.score, metadata: r.metadata,
            })),
          }
          currentAnswerId.value = (event.answer_id as string) || ''
          streaming.value = false
          agenticStatus.value = '完成'
          await loadHistory()
        } else if (event.type === 'error') {
          questionError.value = (event.message as string) || 'Agentic stream error'
          streaming.value = false
          agenticStatus.value = '出错'
        }
      }
    } catch (error) {
      retrievalResults.value = []
      streaming.value = false
      agenticStatus.value = '请求失败'
      questionError.value = error instanceof Error ? error.message : 'Agentic 流式请求失败'
    } finally {
      asking.value = false
      if (streaming.value && !questionError.value) {
        answer.value = {
          question: question.value.trim(),
          answer: streamingAnswer.value || '（回答中断）',
          sources: retrievalResults.value.map((r, i) => ({
            citation: i + 1, vector_id: r.vector_id, text: r.text, score: r.score, metadata: r.metadata,
          })),
        }
        streaming.value = false
        if (!currentAnswerId.value) {
          const match = questionAnswers.value.find(
            (a) => a.question === question.value.trim() && a.answer === streamingAnswer.value,
          )
          currentAnswerId.value = match?.id || ''
        }
      }
    }
  }

  const submitRating = async (answerId: string, rating: number) => {
    if (!answerId) return
    ratingSubmitting.value = true
    try {
      await api.patch(
        `/knowledge-bases/${selectedKnowledgeBaseId.value}/question-answers/${answerId}/rating`,
        { rating },
      )
      const item = questionAnswers.value.find((a) => a.id === answerId)
      if (item) item.rating = rating
    } finally {
      ratingSubmitting.value = false
    }
  }

  const selectHistoryItem = (item: QuestionAnswer) => {
    question.value = item.question
    topK.value = item.top_k
    answer.value = { question: item.question, answer: item.answer, sources: item.sources }
    retrievalResults.value = item.sources.map((s) => ({
      vector_id: s.vector_id, text: s.text, score: s.score, metadata: s.metadata,
    }))
    questionError.value = ''
  }

  const deleteHistoryItem = async (item: QuestionAnswer) => {
    busyAnswerId.value = item.id
    try {
      await api.delete(`/knowledge-bases/${item.knowledge_base_id}/question-answers/${item.id}`)
      questionAnswers.value = questionAnswers.value.filter((a) => a.id !== item.id)
    } finally {
      busyAnswerId.value = ''
    }
  }

  const goQaPage = async (page: number) => {
    qaPage.value = page
    await loadHistory()
  }

  return {
    question, questionError, answer, retrievalResults, questionAnswers, topK,
    asking, streaming, streamingAnswer, retrieving, currentAnswerId, ratingSubmitting,
    loadingHistory, busyAnswerId, qaActiveTab, qaPage, qaPageSize, qaTotal,
    citedVectorIds, currentAnswerRating, retrievalCitationStats,
    retrievalQuery, retrievalSummary,
    agenticMode, agenticStatus, agenticRounds, agenticScore, agenticSubQueries, enableWebSearch,
    loadHistory, retrieveOnly, askQuestion, askAgentic, submitRating,
    selectHistoryItem, deleteHistoryItem, goQaPage,
  }
}
